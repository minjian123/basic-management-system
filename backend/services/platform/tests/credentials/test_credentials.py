"""platform 内部凭据接口测试（Kiwi 2194 / 2209）：服务层校验 / 改密 / 登录态 + 密码策略闸门 + 端点服务 JWT 鉴权。

跑共享租户库（`sys_user` 属 platform 服务租户库 `bms_platform_{code}`）：账号名一律带用例命名
空间；端点用例走真实鉴权（服务令牌由测试助手签发），不再替换 `get_token_verifier` / `get_uow`。
"""

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.config.null import NullConfigSource
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.password.default import DefaultPasswordPolicy
from bms_core.security.pbkdf2 import Pbkdf2PasswordHasher
from bms_core.testing.namespace import Namespace
from bms_platform.domains.user.repositories.user import UserRepository
from bms_platform.domains.user.services.credentials import CredentialService, parse_password_history
from tests_support.service_token import issue_service_token
from tests_support.shared_access import shared_write

API = "/api/v1/platform/internal/credentials"


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


@pytest.mark.kiwi_id(2194)
async def test_service_verify_and_rehash(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """服务层：命中 / 未命中 / 密码错误 / 参数过期重哈希。"""
    account = ns.code("admin")
    async with shared_write(shared_tenant_engine) as session:
        hasher = _hasher()
        repo = UserRepository(session)
        await repo.create(username=account, password_hash=hasher.hash("secret"), name="管理员")
        await session.commit()

        service = CredentialService(repo, hasher, DbUnitOfWork(session))
        ok = await service.verify(account, "secret")
        assert ok.found and ok.valid and not ok.locked and ok.status == "enabled"
        assert ok.user is not None and ok.user.username == account

        bad = await service.verify(account, "wrong")
        assert bad.found and not bad.valid

        missing = await service.verify(ns.code("nobody"), "x")
        assert not missing.found and not missing.valid and missing.user is None

        # 参数升级：以更强迭代重新构造哈希实现后，命中应触发重哈希
        stronger = Pbkdf2PasswordHasher(iterations=200_000)
        rehashed = await CredentialService(repo, stronger, DbUnitOfWork(session)).verify(account, "secret")
        assert rehashed.valid and rehashed.rehashed is True
        stored = await repo.get_by_username(account)
        assert stored is not None and stronger.needs_rehash(stored.password_hash) is False


@pytest.mark.kiwi_id(2194)
async def test_service_update_password_and_history(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """服务层：改密写新哈希 + 变更时间 + 历史追加；账号不存在返回 False。"""
    account = ns.code("u1")
    async with shared_write(shared_tenant_engine) as session:
        hasher = _hasher()
        repo = UserRepository(session)
        old = hasher.hash("old")
        await repo.create(username=account, password_hash=old, name="U1")
        await session.commit()

        service = CredentialService(repo, hasher, DbUnitOfWork(session))
        result = await service.update_password(account, "new", keep_history=5)
        assert result.updated is True
        assert (await service.update_password(ns.code("nobody"), "x")).updated is False

        updated = await repo.get_by_username(account)
        assert updated is not None and hasher.verify("new", updated.password_hash)
        assert parse_password_history(updated.pwd_history) == [old]
        await session.rollback()


@pytest.mark.kiwi_id(2209)
async def test_service_update_password_enforces_policy(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """服务层：改密强制过策略（弱口令 30005 语义；合规写库并清 `pwd_reset_required`）。"""
    account = ns.code("u3")
    async with shared_write(shared_tenant_engine) as session:
        hasher = _hasher()
        repo = UserRepository(session)
        old_hash = hasher.hash("OldPass1!")
        await repo.create(username=account, password_hash=old_hash, name="U3", pwd_reset_required=True)
        await session.commit()
        service = CredentialService(repo, hasher, DbUnitOfWork(session), _policy(hasher))

        weak = await service.update_password(account, "weak")
        assert weak.updated is False and weak.reason == "policy_violation"
        assert "too_short" in weak.violations

        reused = await service.update_password(account, "OldPass1!")
        assert reused.updated is False and reused.reason == "history_reused"

        ok = await service.update_password(account, "Str0ng!Pass")
        assert ok.updated is True and ok.reason == ""
        stored = await repo.get_by_username(account)
        assert stored is not None and hasher.verify("Str0ng!Pass", stored.password_hash)
        assert stored.pwd_reset_required is False
        assert parse_password_history(stored.pwd_history) == [old_hash]
        await session.rollback()

        missing = await service.update_password(ns.code("nobody"), "Str0ng!Pass")
        assert missing.updated is False and missing.reason == "not_found"


@pytest.mark.kiwi_id(2209)
async def test_service_verify_sets_pwd_reset_required_when_expired(
    shared_tenant_engine: AsyncEngine, ns: Namespace
) -> None:
    """服务层：口令命中且超有效期时置 `pwd_reset_required` 并随结果返回。"""
    account = ns.code("u4")
    async with shared_write(shared_tenant_engine) as session:
        hasher = _hasher()
        repo = UserRepository(session)
        expired_at = datetime(2020, 1, 1, 0, 0, 0)
        await repo.create(
            username=account, password_hash=hasher.hash("Str0ng!Pass"), name="U4", pwd_changed_at=expired_at
        )
        await session.commit()
        service = CredentialService(repo, hasher, DbUnitOfWork(session), _policy(hasher))

        result = await service.verify(account, "Str0ng!Pass")
        assert result.valid and result.pwd_reset_required is True
        stored = await repo.get_by_username(account)
        assert stored is not None and stored.pwd_reset_required is True
        await session.rollback()

        fresh = await CredentialService(repo, hasher, DbUnitOfWork(session), _policy(hasher)).verify(account, "bad")
        assert fresh.pwd_reset_required is True  # 未成功不改写，保持既有标志


@pytest.mark.kiwi_id(2194)
async def test_service_login_state(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """服务层：成功清零并记登录时间；失败计数；锁定；账号不存在。"""
    account = ns.code("u2")
    async with shared_write(shared_tenant_engine) as session:
        hasher = _hasher()
        repo = UserRepository(session)
        await repo.create(username=account, password_hash=hasher.hash("p"), name="U2")
        await session.commit()

        service = CredentialService(repo, hasher, DbUnitOfWork(session))
        ok = await service.apply_login_state(account, success=True)
        assert ok.failed_count == 0 and ok.last_login_at is not None

        fail = await service.apply_login_state(account, success=False, failed_count=3)
        assert fail.failed_count == 3 and fail.locked_until is None

        locked = await service.apply_login_state(account, success=False, failed_count=5, lock_seconds=900)
        assert locked.failed_count == 5 and locked.locked_until is not None

        absent = await service.apply_login_state(ns.code("nobody"), success=True)
        assert absent.failed_count == 0


@pytest.mark.kiwi_id(2194)
def testparse_password_history_dirty() -> None:
    """历史密码解析：空 / 脏值按空列表；非字符串项剔除。"""
    assert parse_password_history(None) == []
    assert parse_password_history("not-json") == []
    assert parse_password_history('{"a":1}') == []
    assert parse_password_history('["a", 1, "b"]') == ["a", "b"]


@pytest.mark.kiwi_id(2194)
async def test_internal_endpoint_requires_identity_service(
    client: AsyncClient, shared_tenant_engine: AsyncEngine, ns: Namespace
) -> None:
    """端点：仅放行 `sub=identity` 服务票据；网关 / 无票据 / 用户票据一律拒。"""
    account = ns.code("admin")
    async with shared_write(shared_tenant_engine) as session:
        hasher = _hasher()
        await UserRepository(session).create(username=account, password_hash=hasher.hash("secret"), name="管理员")
        await session.commit()

    identity = issue_service_token("identity")
    auth = {"Authorization": f"Bearer {identity}"}

    body = {"account": account, "password": "secret"}
    ok = await client.post(f"{API}/verify", json=body, headers=auth)
    assert ok.status_code == 200
    assert ok.json()["data"]["valid"] is True

    # 白名单只放行 identity：gateway 是**合法签名的服务令牌**，仍须拒
    gateway = issue_service_token("gateway")
    denied = await client.post(f"{API}/verify", json=body, headers={"Authorization": f"Bearer {gateway}"})
    assert denied.status_code == 401

    anonymous = await client.post(f"{API}/verify", json=body)
    assert anonymous.status_code == 401

    bad = await client.post(f"{API}/verify", json=body, headers={"Authorization": "Bearer bogus"})
    assert bad.status_code == 401

    updated = await client.post(
        f"{API}/update-password",
        json={"account": account, "new_password": "NewSecret1!"},
        headers=auth,
    )
    assert updated.status_code == 200 and updated.json()["data"]["updated"] is True

    weak = await client.post(
        f"{API}/update-password",
        json={"account": account, "new_password": "weak"},
        headers=auth,
    )
    assert weak.status_code == 200
    assert weak.json()["data"]["updated"] is False and weak.json()["data"]["reason"] == "policy_violation"

    state = await client.post(
        f"{API}/login-state",
        json={"account": account, "success": True},
        headers=auth,
    )
    assert state.status_code == 200 and state.json()["data"]["failed_count"] == 0
