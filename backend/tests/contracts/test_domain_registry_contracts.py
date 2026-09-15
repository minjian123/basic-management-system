"""域注册表契约套件（Kiwi 568）：变体与聚合模板 / Null 无副作用 / 注册项自动纳入。"""

from typing import cast

import pytest

from app.core.exceptions import ConflictError, NotFoundError
from app.core.plugin import resolve_plugin
from app.dashboard.null import NullDashboardCardRegistry
from app.fieldtype.base import NULL_COLUMN_TYPE
from app.fieldtype.null import NullFieldTypeRegistry
from app.health.base import BaseHealthCheckRegistry
from app.health.null import NullHealthCheckRegistry
from app.health.registry import HealthCheckRegistry
from app.query.null import NullQueryProviderRegistry
from tests.contracts.support import (
    REGISTRY_CONTRACTS,
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


@pytest.mark.parametrize("contract", REGISTRY_CONTRACTS, ids=lambda item: item.suite_name)
def test_null_registry_variants_empty(contract: RegistryContract) -> None:
    """4 域 Null 注册表变体：空键集 + 显式未命中为 None。"""
    registry = cast("EmptyRegistryProbe", contract.registry_factory())
    assert registry.keys() == ()
    assert registry.get("missing") is None


def test_registry_contract_uniqueness() -> None:
    """唯一性契约：已收敛域重复登记拒重（3 域开关随 03-3 翻转后自动纳入）。"""
    checked = 0
    for contract in REGISTRY_CONTRACTS:
        if not contract.uniqueness:
            continue
        registry = cast("BaseHealthCheckRegistry", contract.registry_factory())
        registry.register(NamedCheck("duplicated"))
        with pytest.raises(ConflictError, match="重复登记"):
            registry.register(NamedCheck("duplicated"))
        checked += 1
    assert checked == 1


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
    """Null 健康注册表：登记空操作、聚合空集就绪（不探依赖）。"""
    registry = NullHealthCheckRegistry()
    registry.register(NamedCheck("dependency"))
    assert registry.keys() == ()
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
    """健康本地注册表：平台装配登记项枚举（redis / database）。"""
    registry = cast("HealthCheckRegistry", resolve_plugin("health_check_registry", "local"))
    assert registry.keys() == ("redis", "database")
