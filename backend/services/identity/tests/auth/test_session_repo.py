"""会话仓储查询测试（Kiwi 2195）：在线过滤、筛选组合与排序。"""

from datetime import timedelta

import pytest
from fastapi import FastAPI

from bms_core.schemas.pagination import BasePageQuery
from bms_identity.models.session import SysSession
from bms_identity.repositories.session import SessionRepository

from .session_helpers import tenant_scope, utc_now


async def _seed(app: FastAPI) -> None:
    """播种多形态会话：活跃（多用户 / 设备 / IP / 时间）、已撤销、已过期。

    Args:
        app: 应用实例。
    """
    now = utc_now()
    rows = [
        {
            "session_id": "7001",
            "user_id": 1,
            "device": "PC-Chrome",
            "ip": "10.0.0.1",
            "login_at": now - timedelta(hours=2),
        },
        {
            "session_id": "7002",
            "user_id": 1,
            "device": "Mobile-H5",
            "ip": "10.0.0.2",
            "login_at": now - timedelta(hours=1),
        },
        {"session_id": "7003", "user_id": 2, "device": "PC-Edge", "ip": "10.0.0.3", "login_at": now},
        {
            "session_id": "7004",
            "user_id": 2,
            "device": "PC-Edge",
            "ip": "10.0.0.4",
            "login_at": now,
            "revoked_at": now,
        },
        {
            "session_id": "7005",
            "user_id": 3,
            "device": "PC",
            "ip": "10.0.0.5",
            "login_at": now,
            "expires_at": now - timedelta(minutes=1),
        },
    ]
    async with tenant_scope(app) as session:
        for row in rows:
            session.add(
                SysSession(
                    id=int(str(row["session_id"])),
                    session_id=str(row["session_id"]),
                    user_id=int(str(row["user_id"])),
                    refresh_token_hash="hash",
                    device=str(row.get("device")) if row.get("device") else None,
                    ip=str(row.get("ip")) if row.get("ip") else None,
                    login_at=row["login_at"],  # type: ignore[arg-type]
                    expires_at=row.get("expires_at") or (now + timedelta(days=14)),  # type: ignore[arg-type]
                    revoked_at=row.get("revoked_at"),  # type: ignore[arg-type]
                )
            )
        await session.commit()


@pytest.mark.kiwi_id(2195)
async def test_repository_active_queries(service_app: FastAPI) -> None:
    """仓储：在线过滤 + 组合筛选 + 用户维度排序。"""
    await _seed(service_app)
    now = utc_now()
    async with tenant_scope(service_app) as session:
        repo = SessionRepository(session)
        query = BasePageQuery()

        assert await repo.count_active(now=now) == 3
        assert {r.session_id for r in await repo.list_active(query, now=now)} == {"7001", "7002", "7003"}

        assert await repo.count_active(now=now, user_id=1) == 2
        assert await repo.count_active(now=now, device="Edge") == 1
        assert await repo.count_active(now=now, ip="10.0.0.2") == 1
        assert await repo.count_active(now=now, login_from=now - timedelta(hours=1, minutes=30)) == 2
        assert await repo.count_active(now=now, login_to=now - timedelta(hours=1, minutes=30)) == 1
        assert await repo.count_active(now=now, user_id=1, device="Chrome") == 1

        by_user = await repo.list_active_by_user(1, now=now)
        assert [r.session_id for r in by_user] == ["7001", "7002"]


@pytest.mark.kiwi_id(2195)
async def test_repository_missing_branches(service_app: FastAPI) -> None:
    """仓储：轮换 / 撤销未命中会话返回 None / False。"""
    now = utc_now()
    async with tenant_scope(service_app) as session:
        repo = SessionRepository(session)
        assert await repo.update_refresh_hash("ghost", "h") is None
        assert await repo.revoke("ghost", revoked_at=now) is False


@pytest.mark.kiwi_id(2195)
async def test_repository_scope_and_paging(service_app: FastAPI) -> None:
    """仓储：作用域隔离（无跨库）与分页 limit / offset。"""
    await _seed(service_app)
    now = utc_now()
    async with tenant_scope(service_app) as session:
        repo = SessionRepository(session)

        page1 = await repo.list_active(BasePageQuery(page=1, size=2), now=now)
        assert len(page1) == 2
        page2 = await repo.list_active(BasePageQuery(page=2, size=2), now=now)
        assert len(page2) == 1
        assert {r.session_id for r in page1} | {r.session_id for r in page2} == {"7001", "7002", "7003"}
