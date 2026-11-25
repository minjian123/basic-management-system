"""platform 重置目标解析测试（Kiwi 2210）：标识分类 / 通道选择 / 可送达判定 + 端点服务 JWT 鉴权。

跑共享租户库（`sys_user` 属 platform 服务租户库）：账号 / 邮箱 / 手机一律按用例命名空间派生
（三者都是唯一键，共享库里固定值会撞）；端点用例走真实鉴权，不再替换校验实现与工作单元。
"""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.models.platform.user import SysUser
from bms_core.testing.namespace import Namespace
from bms_platform.domains.user.repositories.user import UserRepository
from bms_platform.domains.user.services.users import UserResetTargetService
from tests_support.service_token import issue_service_token
from tests_support.shared_access import shared_write

API = "/api/v1/platform/internal/users/reset-target"


def _phone(ns: Namespace, *, suffix: str = "0") -> str:
    """按用例前缀派生一个 11 位手机号（唯一键）。

    Args:
        ns: 用例命名空间。
        suffix: 末位（同用例内造多个手机号时区分）。

    Returns:
        str: 11 位数字串。
    """
    return f"1{int(ns.prefix[2:], 16) % 10**9:09d}{suffix}"


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
        session: 共享租户库会话。
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


@pytest.mark.kiwi_id(2210)
async def test_resolve_identifier_forms_and_channel(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """三形态标识命中：邮箱大小写不敏感、手机 / 账号精确；邮箱优先、手机兜底。"""
    account, worker, boss = ns.code("admin"), ns.code("worker"), ns.code("boss")
    email = f"{account}@example.com"
    phone, other_phone = _phone(ns), _phone(ns, suffix="9")
    async with shared_write(shared_tenant_engine) as session:
        repo = UserRepository(session)
        both = await _add_user(session, account, email=email.title(), phone=phone)
        phone_only = await _add_user(session, worker, phone=other_phone)
        account_only = await _add_user(session, boss)
        await session.commit()
        service = UserResetTargetService(repo)

        by_email = await service.resolve(email.lower())
        assert by_email.found is True and by_email.user_id == both.id
        assert by_email.account == account and by_email.deliverable is True
        assert by_email.channel == "email" and by_email.target == email.title()

        by_phone = await service.resolve(other_phone)
        assert by_phone.user_id == phone_only.id and by_phone.channel == "sms" and by_phone.target == other_phone

        by_account = await service.resolve(boss)
        assert by_account.user_id == account_only.id
        assert by_account.deliverable is False and by_account.channel == "" and by_account.target == ""

        missing = await service.resolve(ns.code("nobody"))
        assert missing.found is False and missing.user_id is None and missing.deliverable is False


@pytest.mark.kiwi_id(2210)
async def test_resolve_not_deliverable_for_disabled_and_deleted(
    shared_tenant_engine: AsyncEngine, ns: Namespace
) -> None:
    """停用 / 软删账号可解析但不可送达（调用侧统一防枚举不发送）。"""
    banned_email, gone_email = f"{ns.code('banned')}@example.com", f"{ns.code('gone')}@example.com"
    async with shared_write(shared_tenant_engine) as session:
        repo = UserRepository(session)
        disabled = await _add_user(session, ns.code("banned"), email=banned_email, status="disabled")
        await _add_user(session, ns.code("gone"), email=gone_email, deleted_at=datetime.now(UTC).replace(tzinfo=None))
        await session.commit()
        service = UserResetTargetService(repo)

        banned = await service.resolve(banned_email)
        assert banned.found is True and banned.user_id == disabled.id and banned.deliverable is False

        gone = await service.resolve(gone_email)
        assert gone.found is False and gone.deliverable is False


@pytest.mark.kiwi_id(2210)
async def test_reset_target_endpoint_requires_identity_service(
    client: AsyncClient, shared_tenant_engine: AsyncEngine, ns: Namespace
) -> None:
    """端点：仅放行 `sub=identity` 服务票据；网关 / 无票据一律拒；响应含通道与目标。"""
    account, email = ns.code("admin"), f"{ns.code('admin')}@example.com"
    async with shared_write(shared_tenant_engine) as session:
        user = await _add_user(session, account, email=email)
        await session.commit()
        user_id = user.id

    auth = {"Authorization": f"Bearer {issue_service_token('identity')}"}
    ok = await client.post(API, json={"identifier": account}, headers=auth)
    assert ok.status_code == 200
    data = ok.json()["data"]
    assert data["found"] is True and data["user_id"] == str(user_id)
    assert data["deliverable"] is True and data["channel"] == "email" and data["target"] == email

    gateway = issue_service_token("gateway")
    denied = await client.post(API, json={"identifier": account}, headers={"Authorization": f"Bearer {gateway}"})
    assert denied.status_code == 401

    anonymous = await client.post(API, json={"identifier": account})
    assert anonymous.status_code == 401
