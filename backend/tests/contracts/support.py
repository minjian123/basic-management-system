"""契约套件公共支撑：装配快照构建与域注册表 / 注册项测试替身（测试专用，不入 app/）。"""

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, cast

from app.core.assembly import register_platform_plugins
from app.core.base import BaseObject
from app.core.config import Settings
from app.core.plugin import PluginImpl, build_plugin_registry
from app.dashboard.base import BaseDashboardCardProvider, BaseDashboardCardRegistry
from app.dashboard.null import NullDashboardCardRegistry
from app.fieldtype.base import BaseFieldType, BaseFieldTypeRegistry
from app.fieldtype.null import NullFieldTypeRegistry
from app.health.base import BaseHealthCheck, HealthCheckResult
from app.health.registry import HealthCheckRegistry
from app.main import create_app
from app.query.base import BaseQueryProvider, BaseQueryProviderRegistry, QueryResult
from app.query.null import NullQueryProviderRegistry


@dataclass(frozen=True)
class RegistryContract(BaseObject):
    """域注册表契约声明（`uniqueness` 随 03-3 收敛后翻转开启）。"""

    suite_name: str
    """域名（`fieldtype` / `query` / `dashboard` / `health`）。"""

    registry_factory: Callable[[], object]
    """注册表变体（`Null`）实例工厂。"""


REGISTRY_CONTRACTS: tuple[RegistryContract, ...] = (
    RegistryContract("fieldtype", NullFieldTypeRegistry),
    RegistryContract("query", NullQueryProviderRegistry),
    RegistryContract("dashboard", NullDashboardCardRegistry),
    RegistryContract("health", HealthCheckRegistry),
)

UNIQUENESS_REGISTRIES: tuple[tuple[str, Callable[[], object]], ...] = (
    ("fieldtype", NullFieldTypeRegistry),
    ("query", NullQueryProviderRegistry),
    ("dashboard", NullDashboardCardRegistry),
    ("health", HealthCheckRegistry),
)
"""唯一性断言独立清单（4 域；03-3 收敛后 3 域 Null 登记改真实拒重）。"""


class EmptyRegistryProbe(Protocol):
    """注册表变体公共探测面（空集断言用）。"""

    def keys(self) -> tuple[str, ...]:
        """已登记键。"""
        ...

    def get(self, key: str) -> object | None:
        """按键取提供者。"""
        ...


def build_snapshot() -> Mapping[str, Mapping[str, PluginImpl]]:
    """构建离线全量装配快照（应用工厂 → 平台实现登记 → 注册表构建；不进入 lifespan）。

    Returns:
        Mapping[str, Mapping[str, PluginImpl]]: 两级映射快照。
    """
    app = create_app()
    settings = cast("Settings", app.state.settings)
    register_platform_plugins(settings, app, app.state.resources)
    return build_plugin_registry()


class TextFieldType(BaseFieldType):
    """测试用字段类型（`text`）。"""

    @property
    def key(self) -> str:
        """字段类型标识。"""
        return "text"

    def describe(self) -> str:
        """元信息描述。

        Returns:
            str: 字段类型说明。
        """
        return f"字段类型 {self.key}"

    def validate(self, value: object, *, options: Mapping[str, object] | None = None) -> tuple[str, ...]:
        """恒定通过。

        Args:
            value: 字段值（忽略）。
            options: 字段选项（忽略）。

        Returns:
            tuple[str, ...]: 空违规元组。
        """
        del value, options
        return ()

    def render_metadata(self) -> Mapping[str, object]:
        """渲染元数据。

        Returns:
            Mapping[str, object]: 固定元数据。
        """
        return {"input": "text"}

    def column_type(self, dialect: str) -> str:
        """固定列类型。

        Args:
            dialect: 方言（忽略）。

        Returns:
            str: `TEXT`。
        """
        del dialect
        return "TEXT"


class DictQueryProvider(BaseQueryProvider):
    """测试用查询提供者（`dict:user`）。"""

    @property
    def key(self) -> str:
        """提供者标识。"""
        return "dict:user"

    def describe(self) -> str:
        """元信息描述。

        Returns:
            str: 查询提供者说明。
        """
        return f"查询提供者 {self.key}"

    async def query(self, params: Mapping[str, object]) -> QueryResult:
        """返回空结果。

        Args:
            params: 查询参数（忽略）。

        Returns:
            QueryResult: 空结果。
        """
        del params
        return QueryResult(rows=(), total=0)


class TodoCardProvider(BaseDashboardCardProvider):
    """测试用卡片提供者（`todo`）。"""

    @property
    def key(self) -> str:
        """卡片标识。"""
        return "todo"

    def describe(self) -> str:
        """元信息描述。

        Returns:
            str: 卡片提供者说明。
        """
        return f"卡片提供者 {self.key}"

    def metadata(self) -> Mapping[str, object]:
        """卡片元数据。

        Returns:
            Mapping[str, object]: 固定元数据。
        """
        return {"title": "待办"}

    async def fetch(self, params: Mapping[str, object]) -> Mapping[str, object]:
        """卡片取数。

        Args:
            params: 取数参数（忽略）。

        Returns:
            Mapping[str, object]: 空数据。
        """
        del params
        return {}


class MemoryFieldTypeRegistry(BaseFieldTypeRegistry):
    """测试用字段类型注册表替身（登记 / 解析继承公共实现）。"""

    @classmethod
    def _provider_key(cls, provider: BaseFieldType) -> str:
        """注册项键。

        Args:
            provider: 字段类型提供者。

        Returns:
            str: 字段类型标识。
        """
        return provider.key


class MemoryQueryProviderRegistry(BaseQueryProviderRegistry):
    """测试用查询提供者注册表替身（登记 / 解析继承公共实现）。"""

    @classmethod
    def _provider_key(cls, provider: BaseQueryProvider) -> str:
        """注册项键。

        Args:
            provider: 查询提供者。

        Returns:
            str: 提供者标识。
        """
        return provider.key


class MemoryDashboardCardRegistry(BaseDashboardCardRegistry):
    """测试用仪表盘卡片注册表替身（登记 / 解析继承公共实现）。"""

    @classmethod
    def _provider_key(cls, provider: BaseDashboardCardProvider) -> str:
        """注册项键。

        Args:
            provider: 卡片提供者。

        Returns:
            str: 卡片标识。
        """
        return provider.key


class NamedCheck(BaseHealthCheck):
    """测试用健康检查项（可通过 / 失败 / 延迟）。"""

    def __init__(
        self,
        name: str,
        *,
        ok: bool = True,
        error: str | None = None,
        delay: float = 0.0,
    ) -> None:
        """初始化。

        Args:
            name: 检查项名称。
            ok: 结果是否就绪（False 时抛 `error` 指定异常）。
            error: `ok=False` 时的异常类名（默认 `ConnectionError`）。
            delay: 检查耗时（秒，用于超时语义）。
        """
        self._name = name
        self._ok = ok
        self._error = error or "ConnectionError"
        self._delay = delay

    @property
    def key(self) -> str:
        """检查项键。"""
        return self._name

    def describe(self) -> str:
        """元信息描述。

        Returns:
            str: 检查项说明。
        """
        return f"健康检查项 {self._name}"

    async def check(self) -> HealthCheckResult:
        """执行检查（延迟 / 抛错 / 通过）。

        Returns:
            HealthCheckResult: 单项结果。

        Raises:
            Exception: `ok=False` 时按 `error` 名称抛出。
        """
        if self._delay:
            await asyncio.sleep(self._delay)
        if not self._ok:
            raise ConnectionError(self._error)
        return HealthCheckResult(name=self._name, ok=True)
