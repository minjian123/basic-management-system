"""选项集能力域：固定值域（运行期不可变）的全局注册、解析与校验契约。

- 标识：`OPTION_SET_KEY_SEPARATOR`（`.`）/ `OPTION_SET_KEY_PATTERN`（点分小写、至少两段）/
  `PLATFORM_NAMESPACE`（`bms`，基座专属命名空间）。
- 数据契约：`OptionItem`（选项项：`value` / `label` / `label_key` / `color` / `disabled` / `sort`）与
  `OptionSetInfo`（解析结果：标识 / 条目清单 / 名称 / 命名空间 / 内容版本）——均为 frozen 值对象。
- `BaseOptionSet`（注册项，组合轨）：抽象 `key` + `describe()`；同步 `items()` / `get(value)` /
  `validate_value(value)`；具体属性 `namespace` / `name` / `version` 与 `info()` 供解析侧统一取信息。
- `BaseOptionSetRegistry`（`key = plugin_key = "option_set_registry"`）：登记 / 清单继承公共实现，
  覆写 `register` 做**装载期冲突校验**（同 value 同 label 合并；同 value 异义 / 同 label 异值 /
  同标识异义 / 产品覆盖基座一律 `PluginError` 40002）+ `resolve` 解析（未命中 `NotFoundError` 10002）+
  `validate` 聚合模板 + `check_references` / `unused_sets` 双向引用校验。
- 校验函数：`validate_option_set_key`（格式与命名空间）、`check_registered_references` /
  `unused_option_sets`（注册表方法的薄封装，供装载器按契约名调用）。
- 提供者 `get_option_set_registry`：按 `[option_set_registry].provider` 经 `resolve_plugin` 取应用级单例。

口径：选项集随代码 / 配置**装载时注册**，运行期**只读**——不落库、不提供写接口；同一 `value` 只允许
一个 `label`、同一 `label` 只允许一个 `value`；产品的 `value` 不得覆盖基座已登记项。运行期可维护的值域
走字典（`dict` / `dict_multi`），与本域二选一。真实装载顺序（基座 → 产品 → 引用校验）与表单元数据下发
随表单定制阶段回补。
"""

import re
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import cast

from fastapi import Request

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.config import Settings
from bms_core.core.exceptions import NotFoundError, PluginError
from bms_core.core.objects import BaseValueObject
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, resolve_plugin
from bms_core.core.provider import BaseProvider, BaseProviderRegistry

__all__ = [
    "OPTION_SET_KEY_PATTERN",
    "OPTION_SET_KEY_SEPARATOR",
    "OPTION_SET_ORIGIN_PLATFORM",
    "OPTION_SET_ORIGIN_PRODUCT",
    "PLATFORM_NAMESPACE",
    "BaseOptionSet",
    "BaseOptionSetRegistry",
    "OptionItem",
    "OptionSetInfo",
    "check_registered_references",
    "get_option_set_registry",
    "unused_option_sets",
    "validate_option_set_key",
]

OPTION_SET_KEY_SEPARATOR = "."
"""选项集标识分隔符（`{命名空间}.{域}.{对象}` 点分小写）。"""

OPTION_SET_KEY_PATTERN = r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
"""选项集标识格式：点分小写、每段字母开头、至少两段（命名空间 + 对象）。"""

PLATFORM_NAMESPACE = "bms"
"""基座专属命名空间（产品不得占用）。"""

OPTION_SET_ORIGIN_PLATFORM = "platform"
"""登记来源：基座内建。"""

OPTION_SET_ORIGIN_PRODUCT = "product"
"""登记来源：产品 / 项目装载注入。"""

_OPTION_SET_KEY_RE = re.compile(OPTION_SET_KEY_PATTERN)
"""标识格式正则（预编译）。"""


def validate_option_set_key(option_set_key: str, *, namespaces: Iterable[str] | None = None) -> None:
    """校验选项集标识格式与命名空间归属。

    Args:
        option_set_key: 选项集标识（如 `bms.user.status`）。
        namespaces: 允许的命名空间集合（可选；`None` 只校验格式）。

    Raises:
        PluginError: 格式非法或命名空间未登记（40002，装载期致命）。
    """
    if not _OPTION_SET_KEY_RE.fullmatch(option_set_key):
        raise PluginError(f"选项集标识格式非法：{option_set_key!r}（须 {OPTION_SET_KEY_PATTERN}）")
    if namespaces is None:
        return
    namespace = option_set_key.split(OPTION_SET_KEY_SEPARATOR, 1)[0]
    if namespace not in namespaces:
        raise PluginError(f"选项集标识命名空间未登记：{option_set_key!r}（命名空间 {namespace!r}）")


@dataclass(frozen=True)
class OptionItem(BaseValueObject):
    """选项项（契约级最小结构；`value` 是唯一真值来源）。

    Attributes:
        value: 选项值（常量字符串，被业务数据引用后冻结）。
        label: 展示文本（当前 locale；与 `label_key` 至少一项非空）。
        label_key: i18n key（缺翻译回退 `label`）。
        color: 语义色（只读标签用，缺省回退默认色）。
        disabled: 是否不可新增选择（存量值仍可回显）。
        sort: 展示顺序（升序；相同按声明顺序）。
    """

    value: str
    label: str = ""
    label_key: str | None = None
    color: str | None = None
    disabled: bool = False
    sort: int = 0


@dataclass(frozen=True)
class OptionSetInfo(BaseValueObject):
    """选项集解析结果（只读快照）。

    Attributes:
        option_set_key: 选项集标识（`optionSetKey`）。
        items: 条目清单（按 `sort` 升序、同 `value` 去重）。
        name: 名称（占位实现为空串）。
        namespace: 命名空间（标识首段）。
        version: 内容版本（缺省 `1`；占位实现为 `0` 表示未登记）。
    """

    option_set_key: str
    items: ConcurrentStableFrozenList[OptionItem] = field(
        default_factory=lambda: ConcurrentStableFrozenList[OptionItem]()
    )
    name: str = ""
    namespace: str = ""
    version: int = 1


class BaseOptionSet(BaseProvider, ABC):
    """选项集提供者契约：条目清单 / 单项解析 / 值域判定。"""

    @abstractmethod
    def items(self) -> ConcurrentStableList[OptionItem]:
        """选项项清单（声明顺序；解析侧按 `sort` 升序归一）。

        Returns:
            ConcurrentStableList[OptionItem]: 选项项清单。
        """

    @abstractmethod
    def get(self, value: str) -> OptionItem | None:
        """按选项值取单项。

        Args:
            value: 选项值（常量字符串）。

        Returns:
            OptionItem | None: 命中项；不在值域内为 None。
        """

    @abstractmethod
    def validate_value(self, value: str) -> ConcurrentStableList[str]:
        """判定值是否在值域内。

        Args:
            value: 选项值。

        Returns:
            ConcurrentStableList[str]: 违规原因元组（空元组通过）。
        """

    @property
    def namespace(self) -> str:
        """命名空间（标识首段，供基座 / 产品归属判定）。

        Returns:
            str: 命名空间。
        """
        return self.key.split(OPTION_SET_KEY_SEPARATOR, 1)[0]

    @property
    def name(self) -> str:
        """名称（缺省取标识，实现可覆写为中文名称）。

        Returns:
            str: 名称。
        """
        return self.key

    @property
    def version(self) -> int:
        """内容版本（缺省 `1`；条目变更按破坏性变更递增）。

        Returns:
            int: 内容版本。
        """
        return 1

    def info(self) -> OptionSetInfo:
        """汇总为解析结果（按 `sort` 升序 → 同 `value` 去重保留首个 → 只读快照）。

        Returns:
            OptionSetInfo: 选项集解析结果。
        """
        ordered: ConcurrentStableList[OptionItem] = ConcurrentStableList(
            sorted(self.items(), key=lambda item: item.sort)
        )
        deduped: ConcurrentStableDict[str, OptionItem] = ConcurrentStableDict()
        for item in ordered:
            if item.value not in deduped:
                deduped.set(item.value, item)
        return OptionSetInfo(
            option_set_key=self.key,
            items=ConcurrentStableFrozenList(deduped.values()),
            name=self.name,
            namespace=self.namespace,
            version=self.version,
        )


def _fingerprint(item: OptionItem) -> tuple[str, str, str | None, str | None, bool]:
    """条目冲突指纹（`sort` 不参与判定，合并时保留首个）。

    Args:
        item: 选项项。

    Returns:
        tuple: `(value, label, label_key, color, disabled)`。
    """
    return (item.value, item.label, item.label_key, item.color, item.disabled)


def _normalize_items(items: ConcurrentStableList[OptionItem]) -> ConcurrentStableDict[str, OptionItem]:
    """按 `value` 归一并对单次声明做冲突校验。

    Args:
        items: 选项项清单（声明顺序）。

    Returns:
        ConcurrentStableDict[str, OptionItem]: `value` → 条目（保留首个）。

    Raises:
        PluginError: 空 `value` / 缺展示文本 / 同 value 异义 / 同 label 异值（40002）。
    """
    normalized: ConcurrentStableDict[str, OptionItem] = ConcurrentStableDict()
    label_owner: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for item in items:
        if not item.value:
            raise PluginError("选项集条目缺少 value")
        if not item.label and not item.label_key:
            raise PluginError(f"选项集条目缺少展示文本：{item.value!r}（label 与 label_key 须至少一项）")
        existing = normalized.get(item.value)
        if existing is not None:
            if _fingerprint(existing) != _fingerprint(item):
                raise PluginError(f"选项集同 value 异义：{item.value!r}")
            continue
        if item.label:
            owner = label_owner.get(item.label)
            if owner is not None and owner != item.value:
                raise PluginError(f"选项集同 label 异值：{item.label!r}（{owner!r} / {item.value!r}）")
            label_owner.set(item.label, item.value)
        normalized.set(item.value, item)
    return normalized


def _same_items(left: ConcurrentStableDict[str, OptionItem], right: ConcurrentStableDict[str, OptionItem]) -> bool:
    """判定两次声明的条目内容是否完全一致（用于「同标识合并 / 异义拒绝」）。

    Args:
        left: 已登记声明的归一结果。
        right: 新声明归一结果。

    Returns:
        bool: 完全一致为 True。
    """
    if len(left) != len(right):
        return False
    for value, item in left.items():
        other = right.get(value)
        if other is None or _fingerprint(other) != _fingerprint(item):
            return False
    return True


class BaseOptionSetRegistry(BaseProviderRegistry[BaseOptionSet], ABC):
    """选项集注册表契约：登记（装载期冲突校验）/ 解析 / 清单 / 双向引用校验。"""

    key: str = "option_set_registry"
    plugin_key: str = "option_set_registry"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    def __init__(self) -> None:
        """初始化空注册表（登记保序）与来源标记表。"""
        super().__init__()
        self._origins: ConcurrentStableDict[str, str] = ConcurrentStableDict()

    @classmethod
    @abstractmethod
    def _provider_key(cls, provider: BaseOptionSet) -> str:
        """注册项键：选项集标识 `key`（各实现声明）。

        Args:
            provider: 选项集提供者。

        Returns:
            str: 选项集标识。
        """

    def register(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, provider: BaseOptionSet, *, origin: str = OPTION_SET_ORIGIN_PLATFORM
    ) -> None:
        """登记选项集（装载期校验；同一标识内容一致时合并）。

        Args:
            provider: 选项集提供者。
            origin: 登记来源（`platform` 基座 / `product` 产品）。

        Raises:
            PluginError: 标识非法、来源非法、产品占用基座命名空间、条目冲突、同标识异义、
                产品改写基座项（40002，装载期致命）。
        """
        option_set_key = self._provider_key(provider)
        validate_option_set_key(option_set_key)
        if origin not in (OPTION_SET_ORIGIN_PLATFORM, OPTION_SET_ORIGIN_PRODUCT):
            raise PluginError(f"选项集登记来源非法：{option_set_key!r} → {origin!r}")
        if origin == OPTION_SET_ORIGIN_PRODUCT and provider.namespace == PLATFORM_NAMESPACE:
            raise PluginError(f"产品不得登记基座命名空间：{option_set_key!r}")
        normalized = _normalize_items(provider.items())
        existing = self.get(option_set_key)
        if existing is not None:
            registered_origin = self._origins.get(option_set_key)
            if registered_origin == OPTION_SET_ORIGIN_PLATFORM and origin == OPTION_SET_ORIGIN_PRODUCT:
                raise PluginError(f"禁止产品覆盖基座已登记选项集：{option_set_key!r}")
            if not _same_items(_normalize_items(existing.items()), normalized):
                raise PluginError(f"选项集同标识异义：{option_set_key!r}")
            return
        super().register(provider)
        self._origins.set(option_set_key, origin)

    def origin_of(self, option_set_key: str) -> str | None:
        """取登记来源（供装载器 / 测试判定基座与产品归属）。

        Args:
            option_set_key: 选项集标识。

        Returns:
            str | None: `platform` / `product`；未登记为 None。
        """
        return self._origins.get(option_set_key)

    def resolve(self, option_set_key: str) -> OptionSetInfo:
        """解析选项集（模板方法：查登记项 → 取解析结果）。

        Args:
            option_set_key: 选项集标识。

        Returns:
            OptionSetInfo: 选项集解析结果。

        Raises:
            NotFoundError: 选项集未登记（10002 / 404）。
        """
        provider = self.get(option_set_key)
        if provider is None:
            raise NotFoundError(f"选项集不存在：{option_set_key}")
        return provider.info()

    def validate(self, value: str, *, option_set_key: str) -> ConcurrentStableList[str]:
        """聚合值域校验（模板方法：解析选项集 → 委托提供者）。

        Args:
            value: 选项值。
            option_set_key: 选项集标识。

        Returns:
            ConcurrentStableList[str]: 违规原因元组（空元组通过）。

        Raises:
            NotFoundError: 选项集未登记（10002）。
        """
        provider = self.get(option_set_key)
        if provider is None:
            raise NotFoundError(f"选项集不存在：{option_set_key}")
        return provider.validate_value(value)

    def check_references(self, used_keys: ConcurrentStableList[str]) -> None:
        """校验代码引用（引用未登记标识即失败）。

        Args:
            used_keys: 代码侧引用的选项集标识清单。

        Raises:
            PluginError: 存在未登记引用（40002）。
        """
        seen: ConcurrentStableSet[str] = ConcurrentStableSet()
        missing: ConcurrentStableList[str] = ConcurrentStableList()
        for key in used_keys:
            if key in seen:
                continue
            seen.add(key)
            if self.get(key) is None:
                missing.add(key)
        if missing:
            raise PluginError("选项集引用未登记：" + "、".join(missing))

    def unused_sets(self, used_keys: ConcurrentStableList[str]) -> ConcurrentStableList[str]:
        """已登记但从未被引用的选项集标识（告警用，不抛错）。

        Args:
            used_keys: 代码侧引用的选项集标识清单。

        Returns:
            ConcurrentStableList[str]: 死项清单（登记顺序）。
        """
        used: ConcurrentStableSet[str] = ConcurrentStableSet(used_keys)
        return ConcurrentStableList(key for key in self.keys() if key not in used)


def check_registered_references(registry: BaseOptionSetRegistry, used_keys: ConcurrentStableList[str]) -> None:
    """校验代码引用的选项集均已登记（``registry.check_references`` 的契约名薄封装）。

    Args:
        registry: 选项集注册表。
        used_keys: 代码侧引用的选项集标识清单。

    Raises:
        PluginError: 存在未登记引用（40002）。
    """
    registry.check_references(used_keys)


def unused_option_sets(
    registry: BaseOptionSetRegistry, used_keys: ConcurrentStableList[str]
) -> ConcurrentStableList[str]:
    """取已登记但未被引用的选项集标识（``registry.unused_sets`` 的契约名薄封装）。

    Args:
        registry: 选项集注册表。
        used_keys: 代码侧引用的选项集标识清单。

    Returns:
        ConcurrentStableList[str]: 死项清单。
    """
    return registry.unused_sets(used_keys)


def get_option_set_registry(request: Request) -> BaseOptionSetRegistry:
    """取应用级选项集注册表（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseOptionSetRegistry: 应用装配的注册表实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseOptionSetRegistry",
        resolve_plugin(
            "option_set_registry",
            settings.option_set_registry.provider,
            expected_version=BaseOptionSetRegistry.contract_version,
        ),
    )
