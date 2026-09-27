"""org 内部 JIT 建号接口测试（Kiwi 2198）：服务层建号 + 撞名语义 + 端点服务 JWT 鉴权。"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.api.deps import get_uow
from bms_core.core.exceptions import AuthError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.oauth.verify import VerifiedToken, get_token_verifier
from bms_org.models.user import SysUser
from bms_org.repositories.user import UserRepository
from bms_org.services.users import SSO_PASSWORD_PLACEHOLDER, UserCreateService

API = "/api/v1/org/internal/users/create"
PBKDF2_PREFIX = "pbkdf2_sha256$"


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


@pytest.mark.kiwi_id(2198)
async def test_service_create_user_and_conflict() -> None:
    """服务层：建号成功（占位口令 + 启用）；同名撞名返回 `created=false`。"""
    session, engine = await _session()
    service = UserCreateService(UserRepository(session), DbUnitOfWork(session))

    created = await service.create_user(username="alice", name="爱丽丝", locale="zh-cn", timezone="Asia/Shanghai")
    assert created.created is True and created.user is not None
    assert created.user.username == "alice" and created.user.status == "enabled"

    conflict = await service.create_user(username="alice", name="另一个")
    assert conflict.created is False and conflict.reason == "username_conflict" and conflict.user is None

    row = await UserRepository(session).get_by_username("alice")
    assert row is not None
    assert row.password_hash == SSO_PASSWORD_PLACEHOLDER
    assert not row.password_hash.startswith(PBKDF2_PREFIX)
    await engine.dispose()


@pytest.mark.kiwi_id(2198)
async def test_service_create_integrity_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    """并发撞名：仓储 flush 触发唯一约束 → 返回 `created=false`（不抛错）。"""
    session, engine = await _session()
    service = UserCreateService(UserRepository(session), DbUnitOfWork(session))

    async def fake_create(self: UserRepository, **values: object) -> object:
        raise IntegrityError("stmt", {}, Exception("duplicate"))

    monkeypatch.setattr(UserRepository, "create", fake_create)
    result = await service.create_user(username="bob", name="鲍勃")
    assert result.created is False and result.reason == "username_conflict"
    await engine.dispose()


@pytest.mark.kiwi_id(2198)
async def test_internal_create_endpoint_requires_identity_service(client: AsyncClient, service_app: FastAPI) -> None:
    """端点：仅放行 `sub=identity` 服务票据；建号成功 / 撞名 / 鉴权分支。"""
    session, engine = await _session()
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    _override_uow(service_app, session)

    ok = await client.post(
        API,
        json={"username": "alice", "name": "爱丽丝", "locale": "zh-cn", "timezone": "Asia/Shanghai"},
        headers={"Authorization": "Bearer identity"},
    )
    assert ok.status_code == 200
    assert ok.json()["data"]["created"] is True
    assert ok.json()["data"]["user"]["username"] == "alice"

    conflict = await client.post(
        API, json={"username": "alice", "name": "重复"}, headers={"Authorization": "Bearer identity"}
    )
    assert conflict.status_code == 200
    assert conflict.json()["data"]["created"] is False
    assert conflict.json()["data"]["reason"] == "username_conflict"

    denied = await client.post(API, json={"username": "bob", "name": "b"}, headers={"Authorization": "Bearer gateway"})
    assert denied.status_code == 401

    anonymous = await client.post(API, json={"username": "bob", "name": "b"})
    assert anonymous.status_code == 401

    await session.close()
    await engine.dispose()
