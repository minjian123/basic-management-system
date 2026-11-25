"""审计链消费组声明与处理器护栏（06_01 / 06_02）。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.audit.sha256 import Sha256HashChain
from bms_core.core.config import get_settings
from bms_core.core.plugin import build_plugin_registry
from bms_core.testing.namespace import Namespace
from bms_platform.domains.log import jobs
from bms_platform.domains.log.jobs import AUDIT_CHAIN_GROUP, AuditLogConsumer, event_consumer_records
from bms_platform.domains.log.repositories.shard import LogShardRepository
from bms_platform.domains.log.schema import LOG_TYPE_LOGIN, LOG_TYPE_OPERATION, month_key
from tests.log.helpers import login_event, operation_event

pytestmark = pytest.mark.kiwi_id(2407)


def test_event_consumer_records_shape() -> None:
    """三条事件一个有序组；工厂每次返回独立处理器。"""
    records = event_consumer_records()
    assert [record.event_type for record in records] == [
        "sys.operation.logged",
        "sys.login.logged",
        "sys.data.changed",
    ]
    for record in records:
        assert record.consumer == AUDIT_CHAIN_GROUP
        assert record.ordered is True
        assert record.concurrency is None
        handler = record.handler_factory()
        assert isinstance(handler, AuditLogConsumer)
        assert handler.event_type == record.event_type


def test_hash_chain_resolution_and_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    """哈希链按配置解析并缓存；复位后重建。"""
    monkeypatch.setenv("BMS_HASH_CHAIN__PROVIDER", "sha256")
    get_settings.cache_clear()
    build_plugin_registry()
    jobs.reset_audit_registry()
    first = jobs._hash_chain()  # pyright: ignore[reportPrivateUsage]
    assert isinstance(first, Sha256HashChain)
    assert jobs._hash_chain() is first  # pyright: ignore[reportPrivateUsage]
    jobs.reset_audit_registry()
    assert isinstance(jobs._hash_chain(), Sha256HashChain)  # pyright: ignore[reportPrivateUsage]
    jobs.reset_audit_registry()


def _fake_registry_factory(factory: object) -> _FakeRegistry:
    """注册表工厂替身。"""
    return _FakeRegistry(factory)


class _FakeRegistry:
    """注册表替身（仅记录构造入参）。"""

    def __init__(self, factory: object) -> None:
        self.factory = factory


def test_registry_lazy_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    """引擎注册表懒建且进程内复用。"""
    created: list[object] = []  # bare-collections:allow（测试记录容器）

    def _factory(settings: object) -> object:
        created.append(settings)
        return object()

    monkeypatch.setattr(jobs, "EngineFactory", _factory)
    monkeypatch.setattr(jobs, "EngineRegistry", _fake_registry_factory)
    jobs.reset_audit_registry()
    registry = jobs._audit_registry()  # pyright: ignore[reportPrivateUsage]
    assert isinstance(registry, _FakeRegistry)
    assert jobs._audit_registry() is registry  # pyright: ignore[reportPrivateUsage]
    jobs.reset_audit_registry()


async def test_consumer_writes_through_writer(
    log_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, ns: Namespace
) -> None:
    """处理器：按事件类型写入对应分片表（会话作用域替换为进程内库）。"""

    @asynccontextmanager
    async def _scope(*args: object, **kwargs: object) -> AsyncGenerator[Any]:
        del args, kwargs
        yield log_session

    monkeypatch.setattr(jobs, "session_scope", _scope)
    monkeypatch.setattr(jobs, "_hash_chain", lambda: Sha256HashChain())

    operation_id = ns.code("e1")
    login_id = ns.code("l1")
    await AuditLogConsumer("sys.operation.logged").consume(operation_event(operation_id))
    await AuditLogConsumer("sys.login.logged").consume(login_event(login_id))
    await log_session.commit()

    # 消费器的写入时钟是真实时钟；分片表是共享的，故只断言「本用例的两个事件各自落到了对应分片」
    month = month_key(datetime.now(UTC).replace(tzinfo=None))
    repo = LogShardRepository(log_session)
    assert month in list(await repo.months(LOG_TYPE_OPERATION))
    assert month in list(await repo.months(LOG_TYPE_LOGIN))
    assert await repo.event_exists(LOG_TYPE_OPERATION, month, operation_id) is True
    assert await repo.event_exists(LOG_TYPE_LOGIN, month, login_id) is True
