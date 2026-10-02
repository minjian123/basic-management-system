"""org 内部用户概要接口测试（Kiwi 2197）：服务层概要 + 端点服务 JWT 鉴权。"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.api.deps import get_uow
from bms_core.core.exceptions import AuthError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.oauth.verify import VerifiedToken, get_token_verifier
from bms_org.models.user import SysUser
from bms_org.repositories.user import UserRepository
from bms_org.services.users import UserProfileService

API = "/api/v1/org/internal/users/profile"


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
    locale: str | None = "zh-cn",
    timezone: str | None = "Asia/Shanghai",
    pwd_reset_required: bool = False,
) -> SysUser:
    """插入一条测试用户。

    Args:
        session: 临时会话。
        username: 登录账号。
        name: 显示名。
        status: 账号状态。
        locale: 语言偏好。
        timezone: 时区偏好。
        pwd_reset_required: 是否需强制改密。

    Returns:
        SysUser: 持久化后的用户行。
    """
    user = SysUser(
        username=username,
        password_hash="hash",
        name=name,
        status=status,
        locale=locale,
        timezone=timezone,
        pwd_reset_required=pwd_reset_required,
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


@pytest.mark.kiwi_id(2197)
@pytest.mark.kiwi_id(2229)
async def test_service_profile_found_and_missing() -> None:
    """服务层：命中返回概要字段（含强制改密标记）；未知 / 禁用用户按状态返回。"""
    session, engine = await _session()
    repo = UserRepository(session)
    user = await _add_user(session, "admin", name="管理员", locale="zh-cn", timezone="Asia/Shanghai")
    expired = await _add_user(session, "expired", name="超期用户", pwd_reset_required=True)
    disabled = await _add_user(session, "banned", name="停用用户", status="disabled")
    await session.commit()

    service = UserProfileService(repo)
    found = await service.profile(user.id)
    assert found.found is True
    assert found.user is not None
    assert found.user.id == user.id
    assert found.user.username == "admin"
    assert found.user.name == "管理员"
    assert found.user.status == "enabled"
    assert found.user.locale == "zh-cn"
    assert found.user.timezone == "Asia/Shanghai"
    assert found.user.pwd_reset_required is False

    expired_profile = await service.profile(expired.id)
    assert expired_profile.user is not None and expired_profile.user.pwd_reset_required is True

    banned = await service.profile(disabled.id)
    assert banned.found is True and banned.user is not None and banned.user.status == "disabled"

    missing = await service.profile(999999)
    assert missing.found is False and missing.user is None
    await engine.dispose()


@pytest.mark.kiwi_id(2197)
async def test_internal_profile_endpoint_requires_identity_service(client: AsyncClient, service_app: FastAPI) -> None:
    """端点：仅放行 `sub=identity` 服务票据；网关 / 无票据 / 未知票据一律拒。"""
    session, engine = await _session()
    user = await _add_user(session, "admin", name="管理员")
    await session.commit()

    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    _override_uow(service_app, session)

    ok = await client.post(API, json={"user_id": user.id}, headers={"Authorization": "Bearer identity"})
    assert ok.status_code == 200
    assert ok.json()["data"]["found"] is True
    assert ok.json()["data"]["user"]["username"] == "admin"

    absent = await client.post(API, json={"user_id": 999999}, headers={"Authorization": "Bearer identity"})
    assert absent.status_code == 200 and absent.json()["data"]["found"] is False

    denied = await client.post(API, json={"user_id": user.id}, headers={"Authorization": "Bearer gateway"})
    assert denied.status_code == 401

    anonymous = await client.post(API, json={"user_id": user.id})
    assert anonymous.status_code == 401

    bogus = await client.post(API, json={"user_id": user.id}, headers={"Authorization": "Bearer bogus"})
    assert bogus.status_code == 401

    await session.close()
    await engine.dispose()
