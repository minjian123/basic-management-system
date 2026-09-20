"""core 层工厂基类：一切工厂类之根（对齐前端 `BaseFactory`）。

- `BaseFactory[OptionsT, ProductT]`：继承 `BasePluggable`——创建入口标识（`key` / `plugin_name` /
  契约版本）+ 参数校验（`validate` 默认空实现）+ 抽象创建（`create`）+ 产出物释放登记（随
  `ResourceManager` 逆序回收）；只负责创建与装配，不承载业务判定。
- 各域工厂基类：应用域 `BaseApplicationFactory`、数据访问域 `BaseDbFactory`、ID 域
  `BaseIdFactory`、插件实现域 `BasePluginFactory`（延迟导入 + 依赖注入；`__call__` 兼容
  `PluginImpl` 零参可调口径）。
- 层级：`BaseFactory` → 各域工厂基类 → 具体工厂类；公共创建逻辑只在工厂基类维护。
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from app.core.exceptions import PluginError
from app.core.plugin import BasePluggable

__all__ = [
    "BaseApplicationFactory",
    "BaseDbFactory",
    "BaseFactory",
    "BaseIdFactory",
    "BasePluginFactory",
    "register_factory",
    "resolve_factory",
]


class BaseFactory[OptionsT, ProductT](BasePluggable, ABC):
    """工厂基类：一切工厂类之根（创建前校验 + 抽象创建）。"""

    key: str = "factory"

    def validate(self, options: OptionsT) -> None:
        """创建前参数校验（默认空实现；子类按需覆写，违规抛业务异常）。

        Args:
            options: 创建参数。
        """

    @abstractmethod
    def create(self, options: OptionsT) -> ProductT:
        """创建产出物（子类实现；创建前应由子类自行调用 `validate`）。

        Args:
            options: 创建参数。

        Returns:
            ProductT: 产出物。
        """


class BaseApplicationFactory(BaseFactory[None, Any]):
    """应用域工厂基类（应用构造编排）。"""

    key: str = "application_factory"


class BaseDbFactory[OptionsT, ProductT](BaseFactory[OptionsT, ProductT]):
    """数据访问域工厂基类（连接配置解析与资源释放约定）。"""

    key: str = "db_factory"


class BaseIdFactory[OptionsT, ProductT](BaseFactory[OptionsT, ProductT]):
    """ID 域工厂基类（WorkerId 装配与生成器重置约定）。"""

    key: str = "id_factory"


class BasePluginFactory[ProductT](BaseFactory[None, ProductT]):
    """插件实现工厂基类：延迟导入 + 依赖注入，产出插件实现实例。

    `__call__` 使工厂实例可直接作为 `PluginImpl`（零参可调用）登记。
    """

    key: str = "plugin_factory"

    def __call__(self) -> ProductT:
        """零参调用（转调 `create(None)`；兼容插件注册表 `PluginImpl` 口径）。

        Returns:
            ProductT: 产出物。
        """
        return self.create(None)


_FACTORY_IMPLS: dict[tuple[str, str], Callable[[], object]] = {}
"""工厂专用注册表：`(工厂键, 实现名) → 零参构造器`（与能力注册表分离，按次新建、不缓存实例）。"""


def register_factory(plugin_key: str, plugin_name: str, impl: Callable[[], object]) -> None:
    """登记工厂实现（工厂专用注册表；同键重名即拒）。

    Args:
        plugin_key: 工厂键（如 `engine_factory`）。
        plugin_name: 实现名（缺省实现用 `default`）。
        impl: 零参构造器（具体工厂类或返回工厂实例的可调用）。

    Raises:
        PluginError: 重名登记。
    """
    key = (plugin_key, plugin_name)
    existing = _FACTORY_IMPLS.get(key)
    if existing is not None and existing is not impl:
        raise PluginError(f"工厂重复登记：{plugin_key}:{plugin_name}")
    _FACTORY_IMPLS[key] = impl


def resolve_factory(plugin_key: str, provider: str | None = None) -> object:
    """解析工厂实例（按次新建，不复用实例；工厂为无状态生产者或应用级资源持有者）。

    Args:
        plugin_key: 工厂键。
        provider: 配置选定的实现名；缺省 / 空串回退 `default`。

    Returns:
        object: 工厂实例（新实例）。

    Raises:
        PluginError: 未登记实现。
    """
    name = provider or "default"
    impl = _FACTORY_IMPLS.get((plugin_key, name))
    if impl is None:
        registered = "、".join(sorted(n for k, n in _FACTORY_IMPLS if k == plugin_key)) or "无"
        raise PluginError(f"未登记的工厂实现：{plugin_key} → {name}（已登记：{registered}）")
    return impl()
