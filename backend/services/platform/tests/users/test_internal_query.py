"""platform 内部用户只读出口测试（Kiwi 2257）：服务层筛选 + 端点服务 JWT 鉴权 + 契约字段。

覆盖任务 `02_06 平台用户只读出口内部契约`——`POST /api/v1/platform/internal/users/query`
（`require_service("org")`，供 mdm 组织域只读出口取用户明细）。
"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.api.deps import get_uow
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import AuthError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.oauth.verify import VerifiedToken, get_token_verifier
from bms_platform.models.user import SysUser
from bms_platform.repositories.user import UserRepository
from bms_platform.services.users import InternalUserQueryService

API = "/api/v1/platform/internal/users/query"


async def _session() -> tuple[AsyncSession, AsyncEngine]:
    """建临时 SQLite 会话（含 `sys_user` 表）。

    Returns:
        tuple[AsyncSession, AsyncEngine]: (会话, 引擎)。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SysUser.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory(), engine


async def _add_user(
    session: AsyncSession,
    username: str,
    *,
    name: str = "运营管理员",
    status: str = "enabled",
    phone: str | None = None,
    email: str | None = None,
) -> SysUser:
    """插入一条测试用户。

    Args:
        session: 临时会话。
        username: 登录账号。
        name: 显示名。
        status: 账号状态。
        phone: 手机号。
        email: 邮箱。

    Returns:
        SysUser: 持久化后的用户行。
    """
    user = SysUser(
        username=username,
        password_hash="hash",
        name=name,
        status=status,
        phone=phone,
        email=email,
    )
    session.add(user)
    await session.flush()
    return user


class _StubVerifier:
    """测试替身：按令牌串返回服务身份（无签名）。"""

    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        """按令牌串返回固定身份声明。

        Args:
            token: 令牌串。
            audience: 期望受众（未使用）。

        Returns:
            VerifiedToken: 身份声明。

        Raises:
            AuthError: 未知令牌（20001/401）。
        """
        del audience
        if token == "org":
            return VerifiedToken(subject="org", service="org", token_type="service")
        if token == "identity":
            return VerifiedToken(subject="identity", service="identity", token_type="service")
        if token == "gateway":
            return VerifiedToken(subject="gateway", service="gateway", token_type="service")
        raise AuthError("invalid")


def _override_uow(app: FastAPI, session: AsyncSession) -> None:
    """把 `get_uow` 覆盖为绑定临时会话的工作单元。

    Args:
        app: 应用实例。
        session: 临时会话。
    """
    uow = DbUnitOfWork(session)
    app.dependency_overrides[get_uow] = lambda: uow


@pytest.mark.kiwi_id(2257)
async def test_internal_query_service_filters_and_paging() -> None:
    """服务层：关键字 / 状态 / 限定集合筛选与分页、总数同口径。"""
    session, engine = await _session()
    repo = UserRepository(session)
    alice = await _add_user(session, "alice", name="爱丽丝", phone="13800000001", email="alice@example.com")
    await _add_user(session, "bob", name="鲍勃", status="disabled")
    await _add_user(session, "carol", name="卡罗尔")
    await session.commit()

    service = InternalUserQueryService(repo)

    rows, total = await service.query()
    assert total == 3
    assert [row.username for row in rows] == ["alice", "bob", "carol"]

    rows, total = await service.query(keyword="ALI")
    assert total == 1
    assert rows[0].username == "alice"

    rows, total = await service.query(keyword="鲍勃")
    assert total == 1
    assert rows[0].username == "bob"

    rows, total = await service.query(status="disabled")
    assert total == 1 and rows[0].username == "bob"

    rows, total = await service.query(ids=ConcurrentStableList([alice.id]))
    assert total == 1 and rows[0].username == "alice"

    rows, total = await service.query(ids=ConcurrentStableList([alice.id]), status="disabled")
    assert total == 0 and len(rows) == 0

    rows, total = await service.query(ids=ConcurrentStableList())
    assert total == 3

    rows, total = await service.query(page=2, size=2)
    assert total == 3
    assert [row.username for row in rows] == ["carol"]

    await engine.dispose()


@pytest.mark.kiwi_id(2257)
async def test_internal_query_endpoint_requires_org_service(client: AsyncClient, service_app: FastAPI) -> None:
    """端点：仅放行 `sub=org` 服务票据；identity / 网关 / 无票据 / 未知票据一律拒。"""
    session, engine = await _session()
    user = await _add_user(session, "alice", name="爱丽丝", phone="13800000001", email="alice@example.com")
    await _add_user(session, "bob", name="鲍勃", status="disabled")
    await session.commit()

    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    _override_uow(service_app, session)

    ok = await client.post(API, json={}, headers={"Authorization": "Bearer org"})
    assert ok.status_code == 200
    body = ok.json()["data"]
    assert body["total"] == 2 and body["page"] == 1 and body["size"] == 20

    filtered = await client.post(
        API, json={"keyword": "alice", "ids": [user.id]}, headers={"Authorization": "Bearer org"}
    )
    assert filtered.status_code == 200
    data = filtered.json()["data"]
    assert data["total"] == 1
    item = data["list"][0]
    assert item["id"] == str(user.id)
    assert item["username"] == "alice"
    assert item["name"] == "爱丽丝"
    assert item["status"] == "enabled"
    assert item["phone"] == "13800000001"
    assert item["email"] == "alice@example.com"
    assert item["dept_id"] is None
    assert "password_hash" not in item and "locked_until" not in item

    for token in ("identity", "gateway", "bogus"):
        denied = await client.post(API, json={}, headers={"Authorization": f"Bearer {token}"})
        assert denied.status_code == 401

    anonymous = await client.post(API, json={})
    assert anonymous.status_code == 401

    await session.close()
    await engine.dispose()


@pytest.mark.kiwi_id(2257)
async def test_internal_query_endpoint_rejects_invalid_status(client: AsyncClient, service_app: FastAPI) -> None:
    """端点：状态取值非法抛参数校验错误（10001，不 500）。"""
    session, engine = await _session()
    await session.commit()
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    _override_uow(service_app, session)

    bad = await client.post(API, json={"status": "unknown"}, headers={"Authorization": "Bearer org"})
    assert bad.status_code == 200
    assert bad.json()["code"] == 10001

    await session.close()
    await engine.dispose()
