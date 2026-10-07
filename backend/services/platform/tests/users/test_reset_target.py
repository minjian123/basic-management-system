"""platform 重置目标解析测试（Kiwi 2210）：标识分类 / 通道选择 / 可送达判定 + 端点服务 JWT 鉴权。"""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.api.deps import get_uow
from bms_core.core.exceptions import AuthError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.oauth.verify import VerifiedToken, get_token_verifier
from bms_platform.models.user import SysUser
from bms_platform.repositories.user import UserRepository
from bms_platform.services.users import UserResetTargetService

API = "/api/v1/platform/internal/users/reset-target"


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
    email: str | None = None,
    phone: str | None = None,
    status: str = "enabled",
    deleted_at: datetime | None = None,
) -> SysUser:
    """插入一条测试用户。

    Args:
        session: 临时会话。
        username: 登录账号。
        email: 邮箱。
        phone: 手机号。
        status: 账号状态。
        deleted_at: 软删除时间（None = 未删）。

    Returns:
        SysUser: 持久化后的用户行。
    """
    user = SysUser(
        username=username,
        password_hash="hash",
        name="用户",
        status=status,
        email=email,
        phone=phone,
        deleted_at=deleted_at,
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


@pytest.mark.kiwi_id(2210)
async def test_resolve_identifier_forms_and_channel() -> None:
    """三形态标识命中：邮箱大小写不敏感、手机 / 账号精确；邮箱优先、手机兜底。"""
    session, engine = await _session()
    repo = UserRepository(session)
    both = await _add_user(session, "admin", email="Admin@Example.com", phone="13800000000")
    phone_only = await _add_user(session, "worker", phone="13900000000")
    account_only = await _add_user(session, "boss")
    await session.commit()
    service = UserResetTargetService(repo)

    by_email = await service.resolve("admin@example.com")
    assert by_email.found is True and by_email.user_id == both.id
    assert by_email.account == "admin" and by_email.deliverable is True
    assert by_email.channel == "email" and by_email.target == "Admin@Example.com"

    by_phone = await service.resolve("13900000000")
    assert by_phone.user_id == phone_only.id and by_phone.channel == "sms" and by_phone.target == "13900000000"

    by_account = await service.resolve("boss")
    assert by_account.user_id == account_only.id
    assert by_account.deliverable is False and by_account.channel == "" and by_account.target == ""

    missing = await service.resolve("nobody")
    assert missing.found is False and missing.user_id is None and missing.deliverable is False
    await engine.dispose()


@pytest.mark.kiwi_id(2210)
async def test_resolve_not_deliverable_for_disabled_and_deleted() -> None:
    """停用 / 软删账号可解析但不可送达（调用侧统一防枚举不发送）。"""
    session, engine = await _session()
    repo = UserRepository(session)
    disabled = await _add_user(session, "banned", email="banned@example.com", status="disabled")
    await _add_user(session, "gone", email="gone@example.com", deleted_at=datetime.now(UTC).replace(tzinfo=None))
    await session.commit()
    service = UserResetTargetService(repo)

    banned = await service.resolve("banned@example.com")
    assert banned.found is True and banned.user_id == disabled.id and banned.deliverable is False

    gone = await service.resolve("gone@example.com")
    assert gone.found is False and gone.deliverable is False
    await engine.dispose()


@pytest.mark.kiwi_id(2210)
async def test_reset_target_endpoint_requires_identity_service(client: AsyncClient, service_app: FastAPI) -> None:
    """端点：仅放行 `sub=identity` 服务票据；网关 / 无票据一律拒；响应含通道与目标。"""
    session, engine = await _session()
    user = await _add_user(session, "admin", email="admin@example.com")
    await session.commit()

    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    _override_uow(service_app, session)

    ok = await client.post(API, json={"identifier": "admin"}, headers={"Authorization": "Bearer identity"})
    assert ok.status_code == 200
    data = ok.json()["data"]
    assert data["found"] is True and data["user_id"] == str(user.id)
    assert data["deliverable"] is True and data["channel"] == "email" and data["target"] == "admin@example.com"

    denied = await client.post(API, json={"identifier": "admin"}, headers={"Authorization": "Bearer gateway"})
    assert denied.status_code == 401

    anonymous = await client.post(API, json={"identifier": "admin"})
    assert anonymous.status_code == 401

    await session.close()
    await engine.dispose()
