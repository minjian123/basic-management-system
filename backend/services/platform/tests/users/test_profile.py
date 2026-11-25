"""platform 内部用户概要接口测试（Kiwi 2197）：服务层概要 + 端点服务 JWT 鉴权。

跑共享租户库（`sys_user` 属 platform 服务租户库）：账号名带用例命名空间；端点用例走真实
鉴权（服务令牌由测试助手签发），不再替换 `get_token_verifier` / `get_uow`。
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.models.platform.user import SysUser
from bms_core.testing.namespace import Namespace
from bms_platform.domains.user.repositories.user import UserRepository
from bms_platform.domains.user.services.users import UserProfileService
from tests_support.service_token import issue_service_token
from tests_support.shared_access import shared_write

API = "/api/v1/platform/internal/users/profile"


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
        session: 共享租户库会话。
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


@pytest.mark.kiwi_id(2197)
async def test_service_profile_found_and_missing(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """服务层：命中返回概要字段（含强制改密标记）；未知 / 禁用用户按状态返回。"""
    admin_name = ns.code("admin")
    async with shared_write(shared_tenant_engine) as session:
        repo = UserRepository(session)
        user = await _add_user(session, admin_name, name="管理员", locale="zh-cn", timezone="Asia/Shanghai")
        expired = await _add_user(session, ns.code("expired"), name="超期用户", pwd_reset_required=True)
        disabled = await _add_user(session, ns.code("banned"), name="停用用户", status="disabled")
        await session.commit()

        service = UserProfileService(repo)
        found = await service.profile(user.id)
        assert found.found is True
        assert found.user is not None
        assert found.user.id == user.id
        assert found.user.username == admin_name
        assert found.user.name == "管理员"
        assert found.user.status == "enabled"
        assert found.user.locale == "zh-cn"
        assert found.user.timezone == "Asia/Shanghai"
        assert found.user.pwd_reset_required is False

        expired_profile = await service.profile(expired.id)
        assert expired_profile.user is not None and expired_profile.user.pwd_reset_required is True

        banned = await service.profile(disabled.id)
        assert banned.found is True and banned.user is not None and banned.user.status == "disabled"

        missing = await service.profile(int(ns.prefix[2:], 16) * 100 + 99)
        assert missing.found is False and missing.user is None


@pytest.mark.kiwi_id(2197)
async def test_internal_profile_endpoint_requires_identity_service(
    client: AsyncClient, shared_tenant_engine: AsyncEngine, ns: Namespace
) -> None:
    """端点：仅放行 `sub=identity` 服务票据；网关 / 无票据 / 未知票据一律拒。"""
    admin_name = ns.code("admin")
    async with shared_write(shared_tenant_engine) as session:
        user = await _add_user(session, admin_name, name="管理员")
        await session.commit()
        user_id = user.id
    missing_id = int(ns.prefix[2:], 16) * 100 + 99

    auth = {"Authorization": f"Bearer {issue_service_token('identity')}"}
    ok = await client.post(API, json={"user_id": user_id}, headers=auth)
    assert ok.status_code == 200
    assert ok.json()["data"]["found"] is True
    assert ok.json()["data"]["user"]["username"] == admin_name

    absent = await client.post(API, json={"user_id": missing_id}, headers=auth)
    assert absent.status_code == 200 and absent.json()["data"]["found"] is False

    # 白名单只放行 identity：gateway 是**合法签名的服务令牌**，仍须拒
    gateway = issue_service_token("gateway")
    denied = await client.post(API, json={"user_id": user_id}, headers={"Authorization": f"Bearer {gateway}"})
    assert denied.status_code == 401

    anonymous = await client.post(API, json={"user_id": user_id})
    assert anonymous.status_code == 401

    bogus = await client.post(API, json={"user_id": user_id}, headers={"Authorization": "Bearer bogus"})
    assert bogus.status_code == 401
