"""org 内部凭据接口测试（Kiwi 2194）：服务层校验 / 改密 / 登录态 + 端点服务 JWT 鉴权。"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.api.deps import get_uow
from bms_core.core.exceptions import AuthError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.oauth.verify import VerifiedToken, get_token_verifier
from bms_core.security.pbkdf2 import Pbkdf2PasswordHasher
from bms_org.models.user import SysUser
from bms_org.repositories.user import UserRepository
from bms_org.services.credentials import CredentialService, parse_password_history

API = "/api/v1/org/internal/credentials"


def _hasher() -> Pbkdf2PasswordHasher:
    """低迭代 PBKDF2（测试提速；仍满足下限）。

    Returns:
        Pbkdf2PasswordHasher: 哈希实现。
    """
    return Pbkdf2PasswordHasher(iterations=100_000)


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


@pytest.mark.kiwi_id(2194)
async def test_service_verify_and_rehash() -> None:
    """服务层：命中 / 未命中 / 密码错误 / 参数过期重哈希。"""
    session, engine = await _session()
    hasher = _hasher()
    repo = UserRepository(session)
    await repo.create(username="admin", password_hash=hasher.hash("secret"), name="管理员")
    await session.commit()

    service = CredentialService(repo, hasher, DbUnitOfWork(session))
    ok = await service.verify("admin", "secret")
    assert ok.found and ok.valid and not ok.locked and ok.status == "enabled"
    assert ok.user is not None and ok.user.username == "admin"

    bad = await service.verify("admin", "wrong")
    assert bad.found and not bad.valid

    missing = await service.verify("nobody", "x")
    assert not missing.found and not missing.valid and missing.user is None

    # 参数升级：以更强迭代重新构造哈希实现后，命中应触发重哈希
    stronger = Pbkdf2PasswordHasher(iterations=200_000)
    rehashed = await CredentialService(repo, stronger, DbUnitOfWork(session)).verify("admin", "secret")
    assert rehashed.valid and rehashed.rehashed is True
    stored = await repo.get_by_username("admin")
    assert stored is not None and stronger.needs_rehash(stored.password_hash) is False
    await engine.dispose()


@pytest.mark.kiwi_id(2194)
async def test_service_update_password_and_history() -> None:
    """服务层：改密写新哈希 + 变更时间 + 历史追加；账号不存在返回 False。"""
    session, engine = await _session()
    hasher = _hasher()
    repo = UserRepository(session)
    old = hasher.hash("old")
    await repo.create(username="u1", password_hash=old, name="U1")
    await session.commit()

    service = CredentialService(repo, hasher, DbUnitOfWork(session))
    result = await service.update_password("u1", "new", keep_history=5)
    assert result.updated is True
    assert (await service.update_password("nobody", "x")).updated is False

    updated = await repo.get_by_username("u1")
    assert updated is not None and hasher.verify("new", updated.password_hash)
    assert parse_password_history(updated.pwd_history) == [old]
    await session.rollback()
    await engine.dispose()


@pytest.mark.kiwi_id(2194)
async def test_service_login_state() -> None:
    """服务层：成功清零并记登录时间；失败计数；锁定；账号不存在。"""
    session, engine = await _session()
    hasher = _hasher()
    repo = UserRepository(session)
    await repo.create(username="u2", password_hash=hasher.hash("p"), name="U2")
    await session.commit()

    service = CredentialService(repo, hasher, DbUnitOfWork(session))
    ok = await service.apply_login_state("u2", success=True)
    assert ok.failed_count == 0 and ok.last_login_at is not None

    fail = await service.apply_login_state("u2", success=False, failed_count=3)
    assert fail.failed_count == 3 and fail.locked_until is None

    locked = await service.apply_login_state("u2", success=False, failed_count=5, lock_seconds=900)
    assert locked.failed_count == 5 and locked.locked_until is not None

    absent = await service.apply_login_state("nobody", success=True)
    assert absent.failed_count == 0
    await engine.dispose()


@pytest.mark.kiwi_id(2194)
def testparse_password_history_dirty() -> None:
    """历史密码解析：空 / 脏值按空列表；非字符串项剔除。"""
    assert parse_password_history(None) == []
    assert parse_password_history("not-json") == []
    assert parse_password_history('{"a":1}') == []
    assert parse_password_history('["a", 1, "b"]') == ["a", "b"]


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


@pytest.mark.kiwi_id(2194)
async def test_internal_endpoint_requires_identity_service(client: AsyncClient, service_app: FastAPI) -> None:
    """端点：仅放行 `sub=identity` 服务票据；网关 / 无票据 / 用户票据一律拒。"""
    session, engine = await _session()
    hasher = _hasher()
    await UserRepository(session).create(username="admin", password_hash=hasher.hash("secret"), name="管理员")
    await session.commit()

    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    _override_uow(service_app, session)

    body = {"account": "admin", "password": "secret"}
    ok = await client.post(f"{API}/verify", json=body, headers={"Authorization": "Bearer identity"})
    assert ok.status_code == 200
    assert ok.json()["data"]["valid"] is True

    denied = await client.post(f"{API}/verify", json=body, headers={"Authorization": "Bearer gateway"})
    assert denied.status_code == 401

    anonymous = await client.post(f"{API}/verify", json=body)
    assert anonymous.status_code == 401

    bad = await client.post(f"{API}/verify", json=body, headers={"Authorization": "Bearer bogus"})
    assert bad.status_code == 401

    updated = await client.post(
        f"{API}/update-password",
        json={"account": "admin", "new_password": "new"},
        headers={"Authorization": "Bearer identity"},
    )
    assert updated.status_code == 200 and updated.json()["data"]["updated"] is True

    state = await client.post(
        f"{API}/login-state",
        json={"account": "admin", "success": True},
        headers={"Authorization": "Bearer identity"},
    )
    assert state.status_code == 200 and state.json()["data"]["failed_count"] == 0

    await session.close()
    await engine.dispose()
