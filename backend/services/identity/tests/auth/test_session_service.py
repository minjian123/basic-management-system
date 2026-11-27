"""会话管理服务单元测试（Kiwi 2195）：统一撤销原语三态、过期踢出、多端上限无溢出、按租户批量撤销。

运行口径（2026-11-27 重写）：会话行落共享租户库，会话主键 / 用户主键一律按用例命名空间派生
（`sid()` / `uid()`），按 id 撤销的用例因此只碰自己的行。**按租户批量撤销**在语义上就是「整库
撤销全部在线会话」（一租户一库，行上没有租户列），故这两个用例各用**每用例一份的独占租户库**
（`isolated_tenant_db_url` + `own_db(scope="destructive")`）——不再用「同一份可写库 + 文件锁串行」：
那把锁是自造互斥，且会让同库其它用例排队；每例一份库之后，两例可以并发，也不需要任何清场。
"""

from datetime import timedelta
from typing import cast

import pytest
from fastapi import FastAPI

from bms_core.core.exceptions import SessionExpiredError
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.security.session import DefaultSessionSecurity
from bms_core.session.memory import MemorySessionStore
from bms_core.testing.namespace import Namespace
from bms_identity.domains.auth.repositories.session import SessionRepository
from bms_identity.domains.auth.services.session import REASON_KICK, REASON_TENANT_SUSPENDED, SessionService
from tests_support.shared_access import shared_session

from .helpers import RecordingRealtimePublisher
from .session_helpers import insert_session, seed_session, sid, tenant_scope, uid, utc_now


def _service(session: DbSession, store: MemorySessionStore, recorder: RecordingRealtimePublisher) -> SessionService:
    """构造会话管理服务（真实会话 + 内存存储 + 记录推送）。

    Args:
        session: 租户库会话。
        store: 会话存储替身。
        recorder: 广播记录替身。

    Returns:
        SessionService: 服务实例。
    """
    return SessionService(
        session=session,
        uow=DbUnitOfWork(session),
        security=DefaultSessionSecurity(secret_key=""),
        store=store,
        publisher=recorder,
    )


@pytest.mark.kiwi_id(2195)
async def test_revoke_three_states(service_app: FastAPI, ns: Namespace) -> None:
    """统一撤销原语：不存在 / 本次撤销 / 已撤销（幂等不重复写）。"""
    session_id = sid(ns, 1)
    await seed_session(service_app, session_id=session_id, user_id=uid(ns))
    store, recorder = MemorySessionStore(), RecordingRealtimePublisher()
    async with tenant_scope(service_app) as session:
        service = _service(session, store, recorder)
        missing = await service.revoke(sid(ns, 9), tenant="demo", reason="logout")
        assert missing.found is False and missing.already_revoked is False

        first = await service.revoke(session_id, tenant="demo", reason="logout")
        assert first.found is True and first.already_revoked is False
        assert await store.load(session_id, tenant="demo") is None

        again = await service.revoke(session_id, tenant="demo", reason="logout")
        assert again.found is True and again.already_revoked is True
    assert recorder.events == []


@pytest.mark.kiwi_id(2195)
async def test_revoke_broadcasts_when_requested(service_app: FastAPI, ns: Namespace) -> None:
    """统一撤销原语在 `broadcast=True` 时发出 `session.revoked`（占位）。"""
    session_id = sid(ns, 2)
    await seed_session(service_app, session_id=session_id, user_id=uid(ns))
    store, recorder = MemorySessionStore(), RecordingRealtimePublisher()
    async with tenant_scope(service_app) as session:
        service = _service(session, store, recorder)
        await service.revoke(session_id, tenant="demo", reason=REASON_KICK, broadcast=True)
    assert [event.event for event in recorder.events] == ["session.revoked"]


@pytest.mark.kiwi_id(2195)
async def test_kick_expired_session(service_app: FastAPI, ns: Namespace) -> None:
    """已过期会话踢出：清理标记后抛 20012（不写 revoked_at）。"""
    store, recorder = MemorySessionStore(), RecordingRealtimePublisher()
    session_id = sid(ns, 3)
    await seed_session(service_app, session_id=session_id, user_id=uid(ns), expires_at=utc_now() - timedelta(minutes=1))
    async with tenant_scope(service_app) as session:
        service = _service(session, store, recorder)
        with pytest.raises(SessionExpiredError):
            await service.kick(session_id, tenant="demo")
    assert await store.load(session_id, tenant="demo") is None


@pytest.mark.kiwi_id(2195)
async def test_enforce_max_active_no_overflow(service_app: FastAPI, ns: Namespace) -> None:
    """未达上限：不作废、返回空列表。"""
    await seed_session(service_app, session_id=sid(ns, 4), user_id=uid(ns))
    store, recorder = MemorySessionStore(), RecordingRealtimePublisher()
    async with tenant_scope(service_app) as session:
        service = _service(session, store, recorder)
        assert await service.enforce_max_active(uid(ns), tenant="demo", max_active=5) == []
    assert recorder.events == []


@pytest.mark.kiwi_id(2325)
@pytest.mark.own_db(
    "按租户批量撤销 = 整库撤销全部在线会话（一租户一库）：每用例一份独占租户库，避免波及共享库他人会话",
    scope="destructive",
)
async def test_revoke_tenant_sessions_revokes_all_active(isolated_tenant_db_url: str, ns: Namespace) -> None:
    """按租户撤销：只涉及在线会话（已撤销 / 过期不动），返回会话清单并广播。"""
    active = [sid(ns, 11), sid(ns, 12)]
    already = sid(ns, 13)
    async with shared_session(isolated_tenant_db_url, read_only=False) as raw:
        session = cast("DbSession", raw)
        await insert_session(session, session_id=active[0], user_id=uid(ns, 1))
        await insert_session(session, session_id=active[1], user_id=uid(ns, 2))
        await insert_session(session, session_id=already, user_id=uid(ns, 2), revoked_at=utc_now())
        store, recorder = MemorySessionStore(), RecordingRealtimePublisher()
        service = _service(session, store, recorder)
        revoked = await service.revoke_tenant_sessions(tenant="1", reason=REASON_TENANT_SUSPENDED)
        await session.commit()
    assert set(revoked) == set(active)
    assert already not in revoked
    assert len(recorder.events) >= 2
    async with shared_session(isolated_tenant_db_url, read_only=True) as raw:
        repo = SessionRepository(cast("DbSession", raw))
        assert await repo.count_active(now=utc_now(), user_id=uid(ns, 1)) == 0
        assert await repo.count_active(now=utc_now(), user_id=uid(ns, 2)) == 0


@pytest.mark.kiwi_id(2325)
@pytest.mark.own_db(
    "按租户批量撤销 = 整库撤销全部在线会话（一租户一库）：每用例一份独占租户库，避免波及共享库他人会话",
    scope="destructive",
)
async def test_revoke_tenant_sessions_cleanup_failure_tolerated(isolated_tenant_db_url: str, ns: Namespace) -> None:
    """运行时清理失败不阻断 DB 撤销（逐会话尽力而为）。"""
    session_id = sid(ns, 14)

    class _FailingStore(MemorySessionStore):
        async def delete(self, session_id: str, *, tenant: str | None = None) -> None:
            del session_id, tenant
            raise RuntimeError("store down")

    _store = _FailingStore()
    recorder = RecordingRealtimePublisher()
    async with shared_session(isolated_tenant_db_url, read_only=False) as raw:
        session = cast("DbSession", raw)
        await insert_session(session, session_id=session_id, user_id=uid(ns, 1))
        service = _service(session, _store, recorder)
        revoked = await service.revoke_tenant_sessions(tenant="1", reason=REASON_TENANT_SUSPENDED)
        await session.commit()
    assert revoked == [session_id]
    async with shared_session(isolated_tenant_db_url, read_only=True) as raw:
        active = await SessionRepository(cast("DbSession", raw)).count_active(now=utc_now(), user_id=uid(ns, 1))
        assert active == 0
