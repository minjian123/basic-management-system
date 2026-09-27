"""org 内部凭据接口测试（Kiwi 2194 / 2209）：服务层校验 / 改密 / 登录态 + 密码策略闸门 + 端点服务 JWT 鉴权。"""

from datetime import datetime

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.api.deps import get_uow
from bms_core.config.null import NullConfigSource
from bms_core.core.exceptions import AuthError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.oauth.verify import VerifiedToken, get_token_verifier
from bms_core.password.default import DefaultPasswordPolicy
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


def _policy(hasher: Pbkdf2PasswordHasher) -> DefaultPasswordPolicy:
    """构造默认规则的密码策略（Null 取数 → 代码默认：8+ 大小写数字符号、禁止含用户名）。

    Args:
        hasher: 口令哈希实现。

    Returns:
        DefaultPasswordPolicy: 密码策略实例。
    """
    return DefaultPasswordPolicy(config=NullConfigSource(), hasher=hasher)


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


@pytest.mark.kiwi_id(2209)
async def test_service_update_password_enforces_policy() -> None:
    """服务层：改密强制过策略（弱口令 30005 语义；合规写库并清 `pwd_reset_required`）。"""
    session, engine = await _session()
    hasher = _hasher()
    repo = UserRepository(session)
    old_hash = hasher.hash("OldPass1!")
    await repo.create(username="u3", password_hash=old_hash, name="U3", pwd_reset_required=True)
    await session.commit()
    service = CredentialService(repo, hasher, DbUnitOfWork(session), _policy(hasher))

    weak = await service.update_password("u3", "weak")
    assert weak.updated is False and weak.reason == "policy_violation"
    assert "too_short" in weak.violations

    reused = await service.update_password("u3", "OldPass1!")
    assert reused.updated is False and reused.reason == "history_reused"

    ok = await service.update_password("u3", "Str0ng!Pass")
    assert ok.updated is True and ok.reason == ""
    stored = await repo.get_by_username("u3")
    assert stored is not None and hasher.verify("Str0ng!Pass", stored.password_hash)
    assert stored.pwd_reset_required is False
    assert parse_password_history(stored.pwd_history) == [old_hash]
    await session.rollback()

    missing = await service.update_password("nobody", "Str0ng!Pass")
    assert missing.updated is False and missing.reason == "not_found"
    await engine.dispose()


@pytest.mark.kiwi_id(2209)
async def test_service_verify_sets_pwd_reset_required_when_expired() -> None:
    """服务层：口令命中且超有效期时置 `pwd_reset_required` 并随结果返回。"""
    session, engine = await _session()
    hasher = _hasher()
    repo = UserRepository(session)
    expired_at = datetime(2020, 1, 1, 0, 0, 0)
    await repo.create(username="u4", password_hash=hasher.hash("Str0ng!Pass"), name="U4", pwd_changed_at=expired_at)
    await session.commit()
    service = CredentialService(repo, hasher, DbUnitOfWork(session), _policy(hasher))

    result = await service.verify("u4", "Str0ng!Pass")
    assert result.valid and result.pwd_reset_required is True
    stored = await repo.get_by_username("u4")
    assert stored is not None and stored.pwd_reset_required is True
    await session.rollback()

    fresh = await CredentialService(repo, hasher, DbUnitOfWork(session), _policy(hasher)).verify("u4", "bad")
    assert fresh.pwd_reset_required is True  # 未成功不改写，保持既有标志
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
        json={"account": "admin", "new_password": "NewSecret1!"},
        headers={"Authorization": "Bearer identity"},
    )
    assert updated.status_code == 200 and updated.json()["data"]["updated"] is True

    weak = await client.post(
        f"{API}/update-password",
        json={"account": "admin", "new_password": "weak"},
        headers={"Authorization": "Bearer identity"},
    )
    assert weak.status_code == 200
    assert weak.json()["data"]["updated"] is False and weak.json()["data"]["reason"] == "policy_violation"

    state = await client.post(
        f"{API}/login-state",
        json={"account": "admin", "success": True},
        headers={"Authorization": "Bearer identity"},
    )
    assert state.status_code == 200 and state.json()["data"]["failed_count"] == 0

    await session.close()
    await engine.dispose()
