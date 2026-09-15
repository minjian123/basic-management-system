"""core 层插件化中间层：`BasePluggable` + 插件注册表（「实现可替换」机制唯一落点）。

- `BasePluggable`：能力域契约的插件化中间层（继承 `BaseCapability` + `BaseAsyncResource`）——
  插件键 `plugin_key` / 实现名 `plugin_name` / 契约版本 `contract_version`；生命周期 `setup()` /
  `aclose()`（默认空实现，`aclose` 经 `ResourceManager` 逆序回收）；`describe()` 元信息。
- `PluginRegistry`：进程内两级映射 `plugin_key → {plugin_name → 实现}`，启动期构建、运行期只读；
  双轨登记（`__init_subclass__` 自动收集 + `register` 显式登记）汇入同一注册表；
  `(plugin_key, plugin_name)` 重名 / 契约版本格式非法等构建期即拒（`PluginError`，明细聚合）。
- 注册项为实现类或零参工厂（`PluginImpl`）；延迟导入由工厂承担（工厂内导入具体实现模块），
  组合路径（虚拟子类 / `Protocol` 结构化）以工厂承载。
- `resolve` / `resolve_plugin`：按配置解析实现（缺省回退 `null`）、同 provider 复用唯一实例
  （实例缓存，`build` 重建清缓存）、未注册即拒、契约版本主版本兼容校验（显式期望版本）。

解析后的装配与生命周期调用（`setup()` / `aclose`）见后续任务（02）；配置驱动装配见 02。
"""

import inspect
import re
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

from app.core.base import BaseObject
from app.core.capability import (
    BaseAsyncResource,
    BaseCapability,
    BaseNullObject,
    BasePlaceholder,
)
from app.core.exceptions import PluginError
from app.core.logging import get_logger

__all__ = [
    "DEFAULT_CONTRACT_VERSION",
    "NULL_PLUGIN_NAME",
    "BasePluggable",
    "PluginImpl",
    "PluginRegistry",
    "build_plugin_registry",
    "plugin_registry_snapshot",
    "register_plugin",
    "resolve_plugin",
]

NULL_PLUGIN_NAME = "null"
"""缺省实现名（`NullXxx` 未显式声明 `plugin_name` 时登记为 `null`）。"""

DEFAULT_CONTRACT_VERSION = "0.1.0"
"""契约版本默认值（自 `0.1.0` 起）。"""

_CONTRACT_VERSION_RE = re.compile(r"\d+\.\d+\.\d+")

_LOGGER = get_logger("bms")
"""插件机制日志（契约版本不兼容等告警）。"""

type PluginImpl = type[BasePluggable] | Callable[[], object]
"""注册项：实现类（继承轨同款）或零参工厂（组合路径 / 延迟导入）。"""


def _contract_major(version: str) -> int | None:
    """取契约版本主版本号。

    Args:
        version: 契约版本字符串。

    Returns:
        int | None: 主版本号；非 `X.Y.Z` 返回 None。
    """
    if not _CONTRACT_VERSION_RE.fullmatch(version):
        return None
    return int(version.split(".", 1)[0])


def _ensure_contract_compatible(
    plugin_key: str,
    name: str,
    instance: object,
    expected_version: str,
) -> None:
    """校验实现与期望契约版本主版本一致（不匹配告警并拒）。

    Args:
        plugin_key: 能力域键。
        name: 实现名。
        instance: 实现实例。
        expected_version: 期望契约版本（端口 `contract_version`）。

    Raises:
        PluginError: 期望 / 实现版本格式非法、实现缺失版本属性或主版本不匹配。
    """
    expected_major = _contract_major(expected_version)
    if expected_major is None:
        raise PluginError(f"期望契约版本格式非法：{plugin_key}:{name} → {expected_version!r}（应为 X.Y.Z）")
    actual = getattr(instance, "contract_version", None)
    if not isinstance(actual, str):
        raise PluginError(f"实现缺少 contract_version，无法校验契约版本：{plugin_key}:{name}")
    actual_major = _contract_major(actual)
    if actual_major is None:
        raise PluginError(f"实现契约版本格式非法：{plugin_key}:{name} → {actual!r}（应为 X.Y.Z）")
    if actual_major != expected_major:
        _LOGGER.error(
            "插件契约版本不兼容",
            plugin_key=plugin_key,
            plugin_name=name,
            expected=expected_version,
            actual=actual,
        )
        raise PluginError(
            f"插件契约版本不兼容：{plugin_key}:{name} 期望 {expected_version}（主版本 {expected_major}），"
            f"实现 {actual}（主版本 {actual_major}）"
        )


def _registration_key(impl_cls: type[BasePluggable]) -> str:
    """登记键：`plugin_key` 未显式声明时回退 `key`。

    Args:
        impl_cls: `BasePluggable` 子类。

    Returns:
        str: 登记键。
    """
    return impl_cls.plugin_key or impl_cls.key


def _registration_name(impl_cls: type[BasePluggable]) -> str:
    """登记名：显式 `plugin_name` 优先；`BaseNullObject` 子类未显式时取 `null`；其余为空（不登记）。

    Args:
        impl_cls: `BasePluggable` 子类。

    Returns:
        str: 登记名；空串表示非插件实现（实工具类）。
    """
    if impl_cls.plugin_name:
        return impl_cls.plugin_name
    if issubclass(impl_cls, BaseNullObject):
        return NULL_PLUGIN_NAME
    return ""


def _impl_label(impl: PluginImpl) -> str:
    """实现标签（类全限定名 / 工厂描述），用于错误明细。

    Args:
        impl: 实现类或零参工厂。

    Returns:
        str: 可读标签。
    """
    if isinstance(impl, type):
        return f"{impl.__module__}.{impl.__qualname__}"
    return repr(impl)


def _add_entry(
    registry: dict[str, dict[str, PluginImpl]],
    errors: list[str],
    key: str,
    name: str,
    impl: PluginImpl,
) -> None:
    """登记一项（重名即记错误，不静默覆盖）。

    Args:
        registry: 两级映射构建中。
        errors: 错误明细累加器。
        key: 登记键。
        name: 登记名。
        impl: 实现类或零参工厂。
    """
    bucket = registry.setdefault(key, {})
    if name in bucket:
        errors.append(f"({key}, {name}) 重名：{_impl_label(bucket[name])} / {_impl_label(impl)}")
        return
    bucket[name] = impl


class BasePluggable(BaseCapability, BaseAsyncResource):
    """插件化中间层：实现可替换的装配语义（插件键 / 实现名 / 契约版本 / 生命周期 / 元信息）。"""

    plugin_key: str = ""
    """能力域键（如 `object_storage`）；未显式声明时回退 `key`。"""

    plugin_name: str = ""
    """实现名（如 `local` / `minio`）；`NullXxx` 未显式声明时登记为 `null`。"""

    contract_version: str = DEFAULT_CONTRACT_VERSION
    """契约版本（`X.Y.Z`；装配期按主版本兼容校验）。"""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """子类创建钩子：把子类收集进默认插件注册表候选（抽象判定与校验统一在构建期）。

        Args:
            **kwargs: 透传父类的类关键字参数。
        """
        super().__init_subclass__(**kwargs)
        _DEFAULT_REGISTRY.collect(cls)

    async def setup(self) -> None:
        """生命周期钩子（默认空实现；装配期由装配入口统一调用）。"""

    async def aclose(self) -> None:
        """释放钩子（默认空实现，幂等；由 `ResourceManager` 逆序统一回收）。"""

    def describe(self) -> str:
        """插件元信息：插件标识（`plugin_key:plugin_name@contract_version`）+ 占位后缀。

        Returns:
            str: 插件标识；占位实现（`BasePlaceholder` 子类）追加占位说明。
        """
        impl_cls = type(self)
        key = _registration_key(impl_cls)
        name = _registration_name(impl_cls)
        identity = f"{key}:{name}@{self.contract_version}"
        if isinstance(self, BasePlaceholder):
            return f"{identity}（占位实现，待回补真实实现）"
        return identity


class PluginRegistry(BaseObject):
    """插件注册表：两级映射 `plugin_key → {plugin_name → 实现}`（启动期构建、运行期只读）。"""

    def __init__(self) -> None:
        """初始化空注册表（未构建）。"""
        self._candidates: list[type[BasePluggable]] = []
        self._explicit: list[tuple[str, str, PluginImpl]] = []
        self._plugins: Mapping[str, Mapping[str, PluginImpl]] | None = None
        self._instances: dict[tuple[str, str], object] = {}

    def collect(self, impl_cls: type[BasePluggable]) -> None:
        """收集自动登记候选（`__init_subclass__` 调用；构建后再收集不影响已冻结快照）。

        Args:
            impl_cls: `BasePluggable` 子类。
        """
        self._candidates.append(impl_cls)

    def register(self, plugin_key: str, plugin_name: str, impl: PluginImpl) -> None:
        """显式登记实现（组合路径 / 延迟导入工厂）；运行期只读，构建后拒。

        Args:
            plugin_key: 能力域键。
            plugin_name: 实现名。
            impl: 实现类或零参工厂。

        Raises:
            PluginError: 注册表已构建（运行期只读）。
        """
        if self._plugins is not None:
            raise PluginError("插件注册表已构建，运行期只读，禁止再登记")
        self._explicit.append((plugin_key, plugin_name, impl))

    def build(self) -> Mapping[str, Mapping[str, PluginImpl]]:
        """构建并冻结注册表：合并双轨 → 校验（抽象剔除 / 无名跳过 / 唯一性 / 版本格式）→ 只读快照。

        Returns:
            Mapping[str, Mapping[str, PluginImpl]]: 两级映射（按 `plugin_key`、`plugin_name` 排序）。

        Raises:
            PluginError: 校验失败（全部明细聚合于消息）。
        """
        registry: dict[str, dict[str, PluginImpl]] = {}
        errors: list[str] = []
        for impl_cls in self._candidates:
            if inspect.isabstract(impl_cls):
                continue
            name = _registration_name(impl_cls)
            if not name:
                continue
            key = _registration_key(impl_cls)
            if not key:
                errors.append(f"候选缺少 plugin_key：{_impl_label(impl_cls)}")
                continue
            if not _CONTRACT_VERSION_RE.fullmatch(impl_cls.contract_version):
                errors.append(
                    f"契约版本格式非法：{_impl_label(impl_cls)} → {impl_cls.contract_version!r}（应为 X.Y.Z）"
                )
                continue
            _add_entry(registry, errors, key, name, impl_cls)
        for key, name, impl in self._explicit:
            if not key or not name:
                errors.append(f"显式登记缺少 plugin_key / plugin_name：{key!r} / {name!r}")
                continue
            if isinstance(impl, type) and inspect.isabstract(impl):
                errors.append(f"显式登记实现不可实例化（抽象类）：{key}:{name} → {_impl_label(impl)}")
                continue
            if not callable(impl):
                errors.append(f"显式登记实现不可调用（须实现类或零参工厂）：{key}:{name}")
                continue
            _add_entry(registry, errors, key, name, impl)
        if errors:
            raise PluginError("插件注册表构建失败：" + "；".join(errors))
        self._plugins = MappingProxyType(
            {
                key: MappingProxyType({name: registry[key][name] for name in sorted(registry[key])})
                for key in sorted(registry)
            }
        )
        self._instances.clear()
        return self._plugins

    def resolve(
        self,
        plugin_key: str,
        provider: str | None = None,
        *,
        expected_version: str | None = None,
    ) -> object:
        """按配置解析实现（同 provider 复用唯一实例；不调用生命周期钩子）。

        Args:
            plugin_key: 能力域键。
            provider: 配置选定的实现名；缺省（`None` / 空串）回退 `null`。
            expected_version: 期望契约版本（端口 `contract_version`）；传入时校验主版本兼容。

        Returns:
            object: 已缓存的实现实例（组合路径结构化实现不继承 `BasePluggable`）。

        Raises:
            PluginError: 未注册实现 / 契约版本不兼容 / 版本格式非法。
        """
        name = provider or NULL_PLUGIN_NAME
        plugins = self.snapshot()
        bucket = plugins.get(plugin_key)
        if bucket is None or name not in bucket:
            registered = "、".join(sorted(bucket)) if bucket else "无"
            raise PluginError(f"未注册的 {plugin_key} 实现：{name}（已注册：{registered}）")
        cache_key = (plugin_key, name)
        instance = self._instances.get(cache_key)
        fresh = instance is None
        if instance is None:
            instance = bucket[name]()
        if expected_version is not None:
            _ensure_contract_compatible(plugin_key, name, instance, expected_version)
        if fresh:
            self._instances[cache_key] = instance
        return instance

    def snapshot(self) -> Mapping[str, Mapping[str, PluginImpl]]:
        """只读快照（未构建则先构建）。

        Returns:
            Mapping[str, Mapping[str, PluginImpl]]: 两级映射只读视图。
        """
        if self._plugins is None:
            return self.build()
        return self._plugins


_DEFAULT_REGISTRY = PluginRegistry()
"""进程级默认插件注册表（`BasePluggable.__init_subclass__` 候选汇入）。"""


def register_plugin(plugin_key: str, plugin_name: str, impl: PluginImpl) -> None:
    """显式登记实现到默认注册表（组合路径 / 延迟导入工厂入口）。

    Args:
        plugin_key: 能力域键。
        plugin_name: 实现名。
        impl: 实现类或零参工厂。

    Raises:
        PluginError: 注册表已构建（运行期只读）。
    """
    _DEFAULT_REGISTRY.register(plugin_key, plugin_name, impl)


def build_plugin_registry() -> Mapping[str, Mapping[str, PluginImpl]]:
    """构建默认注册表并返回只读快照（启动装配入口）。

    Returns:
        Mapping[str, Mapping[str, PluginImpl]]: 两级映射只读视图。

    Raises:
        PluginError: 校验失败（明细聚合）。
    """
    return _DEFAULT_REGISTRY.build()


def plugin_registry_snapshot() -> Mapping[str, Mapping[str, PluginImpl]]:
    """取默认注册表只读快照（未构建则先构建）。

    Returns:
        Mapping[str, Mapping[str, PluginImpl]]: 两级映射只读视图。
    """
    return _DEFAULT_REGISTRY.snapshot()


def resolve_plugin(
    plugin_key: str,
    provider: str | None = None,
    *,
    expected_version: str | None = None,
) -> object:
    """按配置解析默认注册表中的实现（同 provider 复用唯一实例）。

    Args:
        plugin_key: 能力域键。
        provider: 配置选定的实现名；缺省（`None` / 空串）回退 `null`。
        expected_version: 期望契约版本（端口 `contract_version`）。

    Returns:
        object: 已缓存的实现实例。

    Raises:
        PluginError: 未注册实现 / 契约版本不兼容 / 版本格式非法。
    """
    return _DEFAULT_REGISTRY.resolve(plugin_key, provider, expected_version=expected_version)
