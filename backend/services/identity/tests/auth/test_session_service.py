"""会话管理服务单元测试（Kiwi 2195）：统一撤销原语三态、过期踢出、多端上限无溢出。

单库叠加口径（04-6-2）：会话行落共享租户库，会话 / 用户主键按用例命名空间派生。
按租户批量撤销的语义是「本租户库全部在线会话」（全局口径），两个相关用例用 `isolated_tenant`
（`own_db`）拿**独占租户库**：共享库上跑会把并行 worker 的在线会话一并撤销；测试库为真自动
提交（13_08），不能再靠「未提交事务回滚」隔离。
"""

from collections.abc import AsyncIterator, Callable
from datetime import timedelta

import pytest
import pytest_asyncio
from fastapi import FastAPI

from bms_core.core.exceptions import SessionExpiredError
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.security.session import DefaultSessionSecurity
from bms_core.session.memory import MemorySessionStore
from bms_core.testing.fixtures import clear_tenant_cache
from bms_core.testing.namespace import Namespace
from bms_identity.domains.auth.repositories.session import SessionRepository
from bms_identity.domains.auth.services.session import REASON_KICK, REASON_TENANT_SUSPENDED, SessionService

from .helpers import RecordingRealtimePublisher
from .session_helpers import seed_session, sid, tenant_scope, uid, utc_now


@pytest_asyncio.fixture(loop_scope="module")
async def isolated_service_app(
    identity_app_factory: Callable[[], FastAPI], isolated_tenant: None
) -> AsyncIterator[FastAPI]:
    """破坏性全局操作专用 app：在 `isolated_tenant` 切到独占库之后自行装配。

    为什么不能复用常驻 `service_app`：按租户批量撤销的语义就是「本租户库全部在线会话」，
    必须在独占库上执行；常驻 app 的库连接在模块装配时已固化，逐例切库对它无效。

    Args:
        identity_app_factory: 应用工厂（注入租户源替身）。
        isolated_tenant: 独占租户库接线（保证先切库、后装配）。

    Yields:
        FastAPI: 独占库上的应用实例。
    """
    app = identity_app_factory()
    clear_tenant_cache(app)
    try:
        async with app.router.lifespan_context(app):
            yield app
    finally:
        clear_tenant_cache(app)


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
@pytest.mark.own_db("按租户批量撤销是破坏性全局操作：独占库避免波及他人会话", scope="destructive")
async def test_revoke_tenant_sessions_revokes_all_active(
    isolated_tenant: None, isolated_service_app: FastAPI, ns: Namespace
) -> None:
    """按租户撤销：只涉及在线会话（已撤销 / 过期不动），返回会话清单并广播。

    独占租户库（`own_db`）：本用例库内只有本用例播种的会话，故「本租户库全部在线会话」的
    全局断言成立，且不会撤销并行 worker 的会话；应用在本用例切库后自行装配。
    """
    active = [sid(ns, 11), sid(ns, 12)]
    await seed_session(isolated_service_app, session_id=active[0], user_id=uid(ns, 1))
    await seed_session(isolated_service_app, session_id=active[1], user_id=uid(ns, 2))
    already = sid(ns, 13)
    await seed_session(isolated_service_app, session_id=already, user_id=uid(ns, 2), revoked_at=utc_now())
    store, recorder = MemorySessionStore(), RecordingRealtimePublisher()
    async with tenant_scope(isolated_service_app) as session:
        service = _service(session, store, recorder)
        revoked = await service.revoke_tenant_sessions(tenant="1", reason=REASON_TENANT_SUSPENDED)
        await session.commit()
    assert set(active) <= set(revoked)
    assert already not in revoked
    assert len(recorder.events) >= 2
    async with tenant_scope(isolated_service_app) as session:
        repo = SessionRepository(session)
        assert await repo.count_active(now=utc_now()) == 0


@pytest.mark.kiwi_id(2325)
@pytest.mark.own_db("按租户批量撤销是破坏性全局操作：独占库避免波及他人会话", scope="destructive")
async def test_revoke_tenant_sessions_cleanup_failure_tolerated(
    isolated_tenant: None, isolated_service_app: FastAPI, ns: Namespace
) -> None:
    """运行时清理失败不阻断 DB 撤销（逐会话尽力而为）。"""
    session_id = sid(ns, 14)
    await seed_session(isolated_service_app, session_id=session_id, user_id=uid(ns, 1))

    class _FailingStore(MemorySessionStore):
        async def delete(self, session_id: str, *, tenant: str | None = None) -> None:
            del session_id, tenant
            raise RuntimeError("store down")

    _store = _FailingStore()
    recorder = RecordingRealtimePublisher()
    async with tenant_scope(isolated_service_app) as session:
        service = _service(session, _store, recorder)
        revoked = await service.revoke_tenant_sessions(tenant="1", reason=REASON_TENANT_SUSPENDED)
        await session.commit()
    assert session_id in revoked
    async with tenant_scope(isolated_service_app) as session:
        assert await SessionRepository(session).count_active(now=utc_now()) == 0
