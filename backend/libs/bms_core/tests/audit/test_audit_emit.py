"""审计事件发射器护栏（06_01）：写发件箱成功 / 失败降级（不影响业务）。"""

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any, cast

import pytest

from bms_core.audit import emit as emit_module
from bms_core.audit.emit import AuditEventEmitter
from bms_core.audit.events import build_login_event
from bms_core.core.config import Settings
from bms_core.core.exceptions import InternalError
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory
from bms_core.events.base import EventEnvelope

pytestmark = pytest.mark.kiwi_id(2407)


class _Begin:
    """伪事务边界。"""

    async def __aenter__(self) -> None:
        """进入。"""

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """退出（不提交）。"""


class _Session:
    """伪会话（只提供 begin）。"""

    def begin(self) -> _Begin:
        """取事务边界。"""
        return _Begin()


class _Store:
    """伪发件箱：可配置成功 / 失败。"""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[EventEnvelope] = []  # bare-collections:allow（测试断言容器）

    async def enqueue(self, session: object, event: EventEnvelope) -> str:
        """入队（失败时抛错）。"""
        del session
        if self.fail:
            raise RuntimeError("outbox down")
        self.events.append(event)
        return event.event_id or "e"


def _settings() -> Settings:
    """取当前配置（测试隔离夹具已清理环境变量）。"""
    from bms_core.core.config import get_settings

    return get_settings()


def _resolve_to(store: _Store) -> Callable[..., _Store]:
    """构造固定返回发件箱的解析替身。"""

    def _resolve(*args: object, **kwargs: object) -> _Store:
        del args, kwargs
        return store

    return _resolve


@pytest.fixture
def emitter_harness(monkeypatch: pytest.MonkeyPatch) -> tuple[AuditEventEmitter, _Store]:
    """构造发射器（替换会话作用域与发件箱存储）。"""
    store = _Store()
    monkeypatch.setattr(emit_module, "resolve_plugin", _resolve_to(store))

    @asynccontextmanager
    async def _scope(*args: object, **kwargs: object) -> AsyncGenerator[Any]:
        del args, kwargs
        yield _Session()

    monkeypatch.setattr(emit_module, "session_scope", _scope)
    emitter = AuditEventEmitter(
        registry=cast("EngineRegistry", object()),
        session_factory=cast("SessionFactory", object()),
        settings=_settings(),
    )
    return emitter, store


async def test_emit_success_and_failure_is_swallowed(
    emitter_harness: tuple[AuditEventEmitter, _Store], monkeypatch: pytest.MonkeyPatch
) -> None:
    """成功写入返回 True；发件箱故障只告警返回 False（不抛出）。"""
    emitter, store = emitter_harness
    event = build_login_event(tenant_id="1", user_id=1, username="a", ip=None, user_agent=None, status="success")
    assert await emitter.emit(event) is True
    assert store.events == [event]

    store.fail = True
    assert await emitter.emit(event) is False


async def test_emit_in_session_uses_caller_transaction(
    emitter_harness: tuple[AuditEventEmitter, _Store],
) -> None:
    """同事务写入：成功入队；强审计失败抛错；普通审计失败吞掉。"""
    emitter, store = emitter_harness
    event = build_login_event(tenant_id="1", user_id=1, username="a", ip=None, user_agent=None, status="success")
    session = object()

    assert await emitter.emit_in_session(cast("Any", session), event, required=True) is True
    assert store.events == [event]

    store.fail = True
    with pytest.raises(InternalError):
        await emitter.emit_in_session(cast("Any", session), event, required=True)
    assert await emitter.emit_in_session(cast("Any", session), event) is False
