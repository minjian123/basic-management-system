"""收口后遗留处理核验（Kiwi 675 / 677 / 678）：过渡物清理、4 能力接线与 health 口径。"""

import importlib

import pytest

from app.audit.null import NullAuditCapturer
from app.cache.null import NullCacheRegion
from app.core.config import MinioSettings
from app.core.plugin import resolve_plugin
from app.events.base import EventEnvelope
from app.events.null import NullEventPublisher
from app.health.null import NullHealthCheckRegistry
from app.tasks.null import NullTask
from tests.contracts.support import NamedCheck, build_snapshot


@pytest.mark.kiwi_id(675)
def test_transitional_cleanup() -> None:
    """过渡物清理：`app.core.registry` 模块已删除；`MinioSettings` 无 bucket 字段。"""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.core.registry")
    assert "bucket" not in MinioSettings.model_fields
    assert MinioSettings().secret_key == ""


@pytest.mark.kiwi_id(677)
def test_new_capabilities_wired_and_null() -> None:
    """4 能力接线：装配快照含 4 键（null 条目），Null 语义齐备（不连外部服务）。"""
    snapshot = build_snapshot()
    for plugin_key in ("audit", "cache", "event", "task"):
        assert set(snapshot[plugin_key]) == {"null"}

    cache = NullCacheRegion()
    assert cache.domain == "null"
    assert cache.get("k") is None
    assert cache.set("k", 1) is None
    assert cache.delete("k") is False
    assert cache.get_global_version() == 0

    capturer = NullAuditCapturer()
    assert capturer.is_audited("sys_user") is False
    assert capturer.capture(table="sys_user", model_id=1, changes=[]) == EventEnvelope(event_type="audit.null")

    task = NullTask()
    assert task.name == "null_task"
    assert task.run() is None

    publisher = NullEventPublisher()
    assert publisher.event_type == "event.null"


@pytest.mark.kiwi_id(677)
async def test_new_capability_providers_resolve_same_instance() -> None:
    """提供者解析：4 能力经 `resolve_plugin` 取到 null 实现且同 provider 同实例。"""
    build_snapshot()
    assert isinstance(resolve_plugin("cache", ""), NullCacheRegion)
    assert isinstance(resolve_plugin("audit", ""), NullAuditCapturer)
    assert isinstance(resolve_plugin("task", ""), NullTask)
    publisher = resolve_plugin("event", "")
    assert isinstance(publisher, NullEventPublisher)
    assert resolve_plugin("event", "") is publisher
    await publisher.publish(EventEnvelope(event_type="event.null"))
    await publisher.publish_transactional(EventEnvelope(event_type="event.null"))


@pytest.mark.kiwi_id(678)
def test_null_health_registers_really() -> None:
    """health Null 口径对齐：登记后可枚举；聚合仍空集就绪（不探依赖）。"""
    registry = NullHealthCheckRegistry()
    check = NamedCheck("dependency")
    registry.register(check)
    assert registry.keys() == ("dependency",)
    assert registry.get("dependency") is check
    assert registry.checks() == ()
