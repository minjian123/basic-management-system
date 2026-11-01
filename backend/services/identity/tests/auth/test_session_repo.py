"""会话仓储查询测试（Kiwi 2195）：在线过滤、筛选组合与排序。

单库叠加口径（04-6-2）：会话行落共享租户库。用户主键 / 会话主键 / 设备与 IP 标识一律按用例
命名空间派生，仓储计数断言全部带 `user_id` 或派生标识筛选（不再有「全表 count_active == N」）。
"""

from datetime import timedelta

import pytest
from fastapi import FastAPI

from bms_core.models.identity.session import SysSession
from bms_core.schemas.pagination import BasePageQuery
from bms_core.testing.namespace import Namespace
from bms_identity.domains.auth.repositories.session import SessionRepository

from .session_helpers import sid, tenant_scope, uid, utc_now


async def _seed(app: FastAPI, ns: Namespace) -> None:
    """播种多形态会话：活跃（多用户 / 设备 / IP / 时间）、已撤销、已过期。

    Args:
        app: 应用实例。
        ns: 用例命名空间（主键 / 设备 / IP 均由它派生）。
    """
    now = utc_now()
    rows = [
        {"slot": 1, "user": 0, "device": ns.code("pc-chrome"), "ip": ns.code("ip1"), "hours": 2},
        {"slot": 2, "user": 0, "device": ns.code("mobile-h5"), "ip": ns.code("ip2"), "hours": 1},
        {"slot": 3, "user": 1, "device": ns.code("pc-edge"), "ip": ns.code("ip3"), "hours": 0},
        {"slot": 4, "user": 1, "device": ns.code("pc-edge"), "ip": ns.code("ip4"), "hours": 0, "revoked": True},
        {"slot": 5, "user": 2, "device": ns.code("pc"), "ip": ns.code("ip5"), "hours": 0, "expired": True},
    ]
    async with tenant_scope(app) as session:
        for row in rows:
            session.add(
                SysSession(
                    id=int(sid(ns, int(str(row["slot"])))),
                    session_id=sid(ns, int(str(row["slot"]))),
                    user_id=uid(ns, int(str(row["user"]))),
                    refresh_token_hash="hash",
                    device=str(row["device"]),
                    ip=str(row["ip"]),
                    login_at=now - timedelta(hours=int(str(row["hours"]))),
                    expires_at=(now - timedelta(minutes=1)) if row.get("expired") else (now + timedelta(days=14)),
                    revoked_at=now if row.get("revoked") else None,
                )
            )
        await session.commit()


@pytest.mark.kiwi_id(2195)
async def test_repository_active_queries(service_app: FastAPI, ns: Namespace) -> None:
    """仓储：在线过滤 + 组合筛选 + 用户维度排序。"""
    await _seed(service_app, ns)
    now = utc_now()
    subject = uid(ns)
    peer = uid(ns, 1)
    spare = uid(ns, 2)
    async with tenant_scope(service_app) as session:
        repo = SessionRepository(session)
        query = BasePageQuery()

        # 在线过滤（按用户划命名空间，不碰他人行）
        assert await repo.count_active(now=now, user_id=subject) == 2
        assert await repo.count_active(now=now, user_id=peer) == 1
        assert await repo.count_active(now=now, user_id=spare) == 0
        assert {r.session_id for r in await repo.list_active_by_user(subject, now=now)} == {
            sid(ns, 1),
            sid(ns, 2),
        }
        all_active = {r.session_id for r in await repo.list_active(query, now=now)}
        assert {sid(ns, 1), sid(ns, 2), sid(ns, 3)} <= all_active
        assert sid(ns, 4) not in all_active and sid(ns, 5) not in all_active

        # 组合筛选：设备 / IP / 时间窗 / 用户×设备
        assert await repo.count_active(now=now, device=ns.code("pc-edge")) == 1
        assert await repo.count_active(now=now, ip=ns.code("ip2")) == 1
        assert await repo.count_active(now=now, user_id=subject, login_from=now - timedelta(minutes=90)) == 1
        assert await repo.count_active(now=now, user_id=subject, login_to=now - timedelta(minutes=90)) == 1
        assert await repo.count_active(now=now, user_id=subject, device=ns.code("pc-chrome")) == 1

        by_user = await repo.list_active_by_user(subject, now=now)
        assert [r.session_id for r in by_user] == [sid(ns, 1), sid(ns, 2)]
        scoped_all = [r.session_id for r in await repo.list_active_all(now=now) if r.user_id == subject]
        assert scoped_all == [sid(ns, 1), sid(ns, 2)]


@pytest.mark.kiwi_id(2195)
async def test_repository_missing_branches(service_app: FastAPI, ns: Namespace) -> None:
    """仓储：轮换 / 撤销未命中会话返回 None / False。"""
    now = utc_now()
    async with tenant_scope(service_app) as session:
        repo = SessionRepository(session)
        assert await repo.update_refresh_hash(sid(ns, 9), "h") is None
        assert await repo.revoke(sid(ns, 9), revoked_at=now) is False


@pytest.mark.kiwi_id(2195)
async def test_repository_scope_and_paging(service_app: FastAPI, ns: Namespace) -> None:
    """仓储：作用域隔离（无跨库）与分页 limit / offset。"""
    await _seed(service_app, ns)
    now = utc_now()
    async with tenant_scope(service_app) as session:
        repo = SessionRepository(session)

        page1 = await repo.list_active(BasePageQuery(page=1, size=1), now=now, user_id=uid(ns))
        assert len(page1) == 1
        page2 = await repo.list_active(BasePageQuery(page=2, size=1), now=now, user_id=uid(ns))
        assert len(page2) == 1
        page3 = await repo.list_active(BasePageQuery(page=3, size=1), now=now, user_id=uid(ns))
        assert len(page3) == 0
        assert {r.session_id for r in page1} | {r.session_id for r in page2} == {sid(ns, 1), sid(ns, 2)}


@pytest.mark.kiwi_id(2195)
async def test_repository_create_rotate_and_revoke(service_app: FastAPI, ns: Namespace) -> None:
    """仓储写路径：创建（主键同会话 id）/ 轮换续期 / 撤销幂等。"""
    now = utc_now()
    session_id = sid(ns, 6)
    async with tenant_scope(service_app) as session:
        repo = SessionRepository(session)

        created = await repo.create_session(
            session_id=session_id,
            user_id=uid(ns, 3),
            refresh_token_hash="hash-1",
            login_at=now,
            expires_at=now + timedelta(days=14),
            device="PC-Chrome",
            ip="10.0.0.9",
            remember_me=True,
        )
        await session.commit()
        assert created.id == int(session_id) and created.session_id == session_id
        assert created.device == "PC-Chrome" and created.ip == "10.0.0.9"

        rotated = await repo.update_refresh_hash(session_id, "hash-2")
        assert rotated is not None and rotated.refresh_token_hash == "hash-2"

        new_expiry = now + timedelta(days=30)
        rolled = await repo.rotate(session_id, refresh_token_hash="hash-3", expires_at=new_expiry)
        assert rolled is not None
        assert rolled.refresh_token_hash == "hash-3" and rolled.expires_at == new_expiry

        assert await repo.revoke(session_id, revoked_at=now) is True
        # 已撤销：幂等（不重复写入，仍返回 True）
        later = now + timedelta(minutes=5)
        assert await repo.revoke(session_id, revoked_at=later) is True

        reloaded = await repo.get_by_session_id(session_id)
        assert reloaded is not None and reloaded.revoked_at is not None
        assert reloaded.revoked_at != later, "已撤销会话不被二次覆盖"

        assert await repo.rotate(sid(ns, 9), refresh_token_hash="h", expires_at=new_expiry) is None
