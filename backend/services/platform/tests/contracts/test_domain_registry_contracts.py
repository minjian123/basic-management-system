"""域注册表契约套件（Kiwi 568 + 655）：变体与聚合模板 / 唯一性口径 / 注册项自动纳入。"""

from collections.abc import Callable
from typing import cast

import pytest

from bms_core.core.exceptions import ConflictError, NotFoundError
from bms_core.core.plugin import resolve_plugin
from bms_core.core.provider import BaseProvider, BaseProviderRegistry
from bms_core.dashboard.null import NullDashboardCardRegistry
from bms_core.fieldtype.base import NULL_COLUMN_TYPE
from bms_core.fieldtype.null import NullFieldTypeRegistry
from bms_core.health.null import NullHealthCheckRegistry
from bms_core.health.registry import HealthCheckRegistry
from bms_core.query.null import NullQueryProviderRegistry
from tests.contracts.support import (
    REGISTRY_CONTRACTS,
    UNIQUENESS_REGISTRIES,
    DictQueryProvider,
    EmptyRegistryProbe,
    MemoryDashboardCardRegistry,
    MemoryFieldTypeRegistry,
    MemoryQueryProviderRegistry,
    NamedCheck,
    RegistryContract,
    TextFieldType,
    TodoCardProvider,
)

pytestmark = pytest.mark.kiwi_id(568)

_UNIQUENESS_PROVIDERS: dict[str, Callable[[], BaseProvider]] = {
    "fieldtype": TextFieldType,
    "query": DictQueryProvider,
    "dashboard": TodoCardProvider,
    "health": lambda: NamedCheck("duplicated"),
}


@pytest.mark.parametrize("contract", REGISTRY_CONTRACTS, ids=lambda item: item.suite_name)
def test_null_registry_variants_empty(contract: RegistryContract) -> None:
    """4 域 Null 注册表变体：空键集 + 显式未命中为 None。"""
    registry = cast("EmptyRegistryProbe", contract.registry_factory())
    assert registry.keys() == ()
    assert registry.get("missing") is None


@pytest.mark.kiwi_id(655)
@pytest.mark.parametrize(
    ("suite_name", "registry_factory"),
    UNIQUENESS_REGISTRIES,
    ids=[name for name, _ in UNIQUENESS_REGISTRIES],
)
def test_uniqueness_registries_reject_duplicates(suite_name: str, registry_factory: Callable[[], object]) -> None:
    """唯一性口径对齐（4 域）：同键二次登记 → ConflictError（与插件注册表一致）。"""
    registry = cast("BaseProviderRegistry[BaseProvider]", registry_factory())
    provider_factory = _UNIQUENESS_PROVIDERS[suite_name]
    registry.register(provider_factory())
    with pytest.raises(ConflictError, match="重复登记"):
        registry.register(provider_factory())


@pytest.mark.kiwi_id(655)
def test_null_registry_registers_really() -> None:
    """3 域 Null 注册表登记改真实：登记后枚举可见；聚合模板语义不变。"""
    fieldtypes = NullFieldTypeRegistry()
    fieldtypes.register(TextFieldType())
    assert fieldtypes.keys() == ("text",)
    assert isinstance(fieldtypes.get("text"), TextFieldType)
    assert fieldtypes.validate("text", "value") == ()
    assert fieldtypes.column_type("text", "mysql") == NULL_COLUMN_TYPE

    queries = NullQueryProviderRegistry()
    queries.register(DictQueryProvider())
    assert queries.keys() == ("dict:user",)
    assert isinstance(queries.get("dict:user"), DictQueryProvider)

    cards = NullDashboardCardRegistry()
    cards.register(TodoCardProvider())
    assert cards.keys() == ("todo",)
    assert isinstance(cards.get("todo"), TodoCardProvider)
    assert cards.metadata("todo") == {}


def test_null_fieldtype_semantics() -> None:
    """Null 字段类型聚合：校验恒过、列类型恒占位。"""
    registry = NullFieldTypeRegistry()
    assert registry.validate("missing", "value") == ()
    assert registry.column_type("missing", "mysql") == NULL_COLUMN_TYPE


async def test_null_query_semantics() -> None:
    """Null 查询聚合：恒空结果。"""
    registry = NullQueryProviderRegistry()
    result = await registry.query("missing", {})
    assert result.rows == ()
    assert result.total == 0


def test_null_dashboard_metadata_semantics() -> None:
    """Null 卡片元数据聚合：恒空映射。"""
    registry = NullDashboardCardRegistry()
    assert registry.metadata("missing") == {}


async def test_null_dashboard_fetch_semantics() -> None:
    """Null 卡片取数聚合：恒空映射。"""
    registry = NullDashboardCardRegistry()
    assert await registry.fetch("missing", {}) == {}


async def test_null_health_semantics() -> None:
    """Null 健康注册表：登记真实可枚举、聚合空集就绪（不探依赖）。"""
    registry = NullHealthCheckRegistry()
    check = NamedCheck("dependency")
    registry.register(check)
    assert registry.keys() == ("dependency",)
    assert registry.get("dependency") is check
    assert registry.checks() == ()
    report = await registry.aggregate()
    assert report.ok is True
    assert report.checks == ()


def test_memory_fieldtype_aggregation_not_found() -> None:
    """内存字段类型注册表：命中委托、未命中转 NotFoundError。"""
    registry = MemoryFieldTypeRegistry()
    registry.register(TextFieldType())
    assert registry.keys() == ("text",)
    assert registry.validate("text", "value") == ()
    with pytest.raises(NotFoundError, match="字段类型不存在"):
        registry.validate("missing", "value")
    with pytest.raises(NotFoundError, match="字段类型不存在"):
        registry.column_type("missing", "mysql")


async def test_memory_query_aggregation_not_found() -> None:
    """内存查询注册表：命中委托、未命中转 NotFoundError。"""
    registry = MemoryQueryProviderRegistry()
    registry.register(DictQueryProvider())
    result = await registry.query("dict:user", {})
    assert result.total == 0
    with pytest.raises(NotFoundError, match="查询提供者不存在"):
        await registry.query("missing", {})


def test_memory_dashboard_aggregation_not_found() -> None:
    """内存卡片注册表：命中委托、未命中转 NotFoundError。"""
    registry = MemoryDashboardCardRegistry()
    registry.register(TodoCardProvider())
    assert registry.metadata("todo") == {"title": "待办"}
    with pytest.raises(NotFoundError, match="工作台卡片不存在"):
        registry.metadata("missing")


async def test_memory_dashboard_fetch_not_found() -> None:
    """内存卡片注册表取数未命中：转 NotFoundError。"""
    registry = MemoryDashboardCardRegistry()
    registry.register(TodoCardProvider())
    with pytest.raises(NotFoundError, match="工作台卡片不存在"):
        await registry.fetch("missing", {})


async def test_health_aggregation_templates() -> None:
    """健康聚合模板：保序收集 + 单项异常兜底（异常类名）。"""
    registry = HealthCheckRegistry()
    registry.register(NamedCheck("ready"))
    registry.register(NamedCheck("down", ok=False))
    report = await registry.aggregate()
    assert report.ok is False
    assert [item.name for item in report.checks] == ["ready", "down"]
    assert report.checks[0].ok is True
    assert report.checks[0].error is None
    assert report.checks[1].ok is False
    assert report.checks[1].error == "ConnectionError"


async def test_health_aggregation_timeout() -> None:
    """健康聚合模板：单项超时兜底（TimeoutError）。"""
    registry = HealthCheckRegistry(check_timeout_ms=10)
    registry.register(NamedCheck("slow", delay=0.2))
    report = await registry.aggregate()
    assert report.ok is False
    assert report.checks[0].error == "TimeoutError"


def test_registered_items_auto_enumerated() -> None:
    """注册项自动纳入：登记后即出现在枚举与解析（3 域注册表替身）。"""
    fieldtypes = MemoryFieldTypeRegistry()
    assert fieldtypes.keys() == ()
    fieldtypes.register(TextFieldType())
    assert fieldtypes.keys() == ("text",)
    assert fieldtypes.get("text") is not None

    queries = MemoryQueryProviderRegistry()
    assert queries.keys() == ()
    queries.register(DictQueryProvider())
    assert queries.keys() == ("dict:user",)
    assert queries.get("dict:user") is not None

    cards = MemoryDashboardCardRegistry()
    assert cards.keys() == ()
    cards.register(TodoCardProvider())
    assert cards.keys() == ("todo",)
    assert cards.get("todo") is not None


def test_health_local_registration_enumerated() -> None:
    """健康本地注册表：平台装配登记项枚举（redis / database / catalog）。"""
    registry = cast("HealthCheckRegistry", resolve_plugin("health_check_registry", "local"))
    assert registry.keys() == ("redis", "database", "catalog")
