"""platform 统一建号入口的关系维护测试（11_01）：建号后经关系数据源建立自有租户关系。

覆盖：服务层注入关系数据源（建号 → `ensure`）、未注入 / 无归属租户时跳过、关系写入失败不阻断建号、
内部端点透传 `source` 与归属租户。

跑共享租户库（`sys_user` 属 platform 服务租户库）：账号名带用例命名空间；端点用例走真实装配
（服务令牌由测试助手签发），不再替换鉴权 / 工作单元。
"""

from typing import cast

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.tenant.membership import TenantMembershipStore, TenantMembershipTarget
from bms_core.testing.namespace import Namespace
from bms_platform.domains.user.repositories.user import UserRepository
from bms_platform.domains.user.services.users import UserCreateService
from tests_support.service_token import issue_service_token
from tests_support.shared_access import shared_write

API = "/api/v1/platform/internal/users/create"
DEMO_TENANT_ID = 1001


class _RecordingStore:
    """关系数据源替身：记录 `ensure` 调用（结构上满足 `TenantMembershipStore`）。"""

    def __init__(self, *, fail: bool = False) -> None:
        """初始化。

        Args:
            fail: 是否在 `ensure` 时抛服务不可用（验证不阻断建号）。
        """
        self.fail = fail
        self.calls: ConcurrentStableList[tuple[int, int, int, str]] = ConcurrentStableList()

    async def list_targets(
        self, *, tenant_id: int, user_id: int, include_disabled: bool = False
    ) -> ConcurrentStableList[TenantMembershipTarget]:
        """取目标集合（替身空实现）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            include_disabled: 是否含 `disabled` 行。

        Returns:
            ConcurrentStableList[TenantMembershipTarget]: 空集合。
        """
        del tenant_id, user_id, include_disabled
        return ConcurrentStableList()

    async def ensure(
        self, *, tenant_id: int, user_id: int, target_tenant_id: int, source: str
    ) -> TenantMembershipTarget:
        """记录建关系调用（可选抛错）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            target_tenant_id: 目标租户主键。
            source: 来源标识。

        Returns:
            TenantMembershipTarget: 关系目标。

        Raises:
            ServiceUnavailableError: `fail=True` 时抛出。
        """
        self.calls.add((tenant_id, user_id, target_tenant_id, source))
        if self.fail:
            raise ServiceUnavailableError("membership store down")
        return TenantMembershipTarget(tenant_id=target_tenant_id, code="demo", name="演示租户", source=source)


@pytest.mark.kiwi_id(2198)
async def test_service_create_ensures_self_membership(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """服务层：建号成功后按来源与归属租户建立自有租户关系；未注入 / 无归属租户则跳过。"""
    alice, bob, carol = ns.code("alice"), ns.code("bob"), ns.code("carol")
    async with shared_write(shared_tenant_engine) as session:
        store = _RecordingStore()
        service = UserCreateService(
            UserRepository(session), DbUnitOfWork(session), membership=cast("TenantMembershipStore", store)
        )

        created = await service.create_user(
            username=alice, name="爱丽丝", source="admin_create", owner_tenant_id=DEMO_TENANT_ID
        )
        assert created.created is True and created.user is not None
        assert list(store.calls) == [(DEMO_TENANT_ID, created.user.id, DEMO_TENANT_ID, "admin_create")]

        skipped = await service.create_user(username=bob, name="鲍勃", owner_tenant_id=None)
        assert skipped.created is True
        assert len(store.calls) == 1

        no_store = UserCreateService(UserRepository(session), DbUnitOfWork(session))
        assert (
            await no_store.create_user(username=carol, name="卡罗尔", owner_tenant_id=DEMO_TENANT_ID)
        ).created is True


@pytest.mark.kiwi_id(2198)
async def test_service_create_degrades_when_membership_fails(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """服务层：关系写入失败不阻断建号（降级记日志）。"""
    async with shared_write(shared_tenant_engine) as session:
        service = UserCreateService(
            UserRepository(session),
            DbUnitOfWork(session),
            membership=cast("TenantMembershipStore", _RecordingStore(fail=True)),
        )

        result = await service.create_user(username=ns.code("dave"), name="戴夫", owner_tenant_id=DEMO_TENANT_ID)
        assert result.created is True and result.user is not None


@pytest.mark.kiwi_id(2198)
async def test_internal_create_passes_source_and_tenant(
    client: AsyncClient, shared_tenant_engine: AsyncEngine, ns: Namespace
) -> None:
    """端点：建号透传 `source`，并以解析链租户为主体的归属租户建立关系。

    真实装配下关系数据源是产品实现（不记录调用），故断言落在「建号成功 + 账号落在库里」；
    「`source` / 归属租户透传」由服务层用例覆盖。
    """
    account = ns.code("erin")
    resp = await client.post(
        API,
        json={"username": account, "name": "艾琳", "source": "import"},
        headers={"Authorization": f"Bearer {issue_service_token('identity')}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["created"] is True

    async with shared_write(shared_tenant_engine) as probe:
        row = await UserRepository(probe).get_by_username(account)
        assert row is not None
