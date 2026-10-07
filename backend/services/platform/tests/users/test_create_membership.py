"""platform 统一建号入口的关系维护测试（11_01）：建号后经关系数据源建立自有租户关系。

覆盖：服务层注入关系数据源（建号 → `ensure`）、未注入 / 无归属租户时跳过、关系写入失败不阻断建号、
内部端点透传 `source` 与归属租户。
"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.api.deps import get_tenant, get_tenant_membership_store, get_uow
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.db.tenant import TenantContext
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.oauth.verify import VerifiedToken, get_token_verifier
from bms_core.tenant.membership import TenantMembershipTarget
from bms_platform.models.user import SysUser
from bms_platform.repositories.user import UserRepository
from bms_platform.services.users import UserCreateService

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
            source: 写入来源。

        Returns:
            TenantMembershipTarget: 目标条目。

        Raises:
            ServiceUnavailableError: 替身配置为失败时（10007）。
        """
        if self.fail:
            raise ServiceUnavailableError("契约不可达")
        self.calls.add((tenant_id, user_id, target_tenant_id, source))
        return TenantMembershipTarget(tenant_id=target_tenant_id, code="demo", name="演示租户")

    async def revoke(self, *, tenant_id: int, user_id: int, target_tenant_id: int) -> None:
        """回收单个目标租户关系（替身空实现）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            target_tenant_id: 目标租户主键。
        """

    async def revoke_all(self, *, tenant_id: int, user_id: int) -> None:
        """回收全部目标租户关系（替身空实现）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
        """


class _StubVerifier:
    """测试替身：按令牌串返回服务身份（无签名）。"""

    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        """按令牌串返回固定身份声明。

        Args:
            token: 令牌串。
            audience: 期望受众（未使用）。

        Returns:
            VerifiedToken: 身份声明。
        """
        del audience
        return VerifiedToken(subject=token, service=token, token_type="service")


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


@pytest.mark.kiwi_id(2198)
async def test_service_create_ensures_self_membership() -> None:
    """服务层：建号成功后按来源与归属租户建立自有租户关系；未注入 / 无归属租户则跳过。"""
    session, engine = await _session()
    store = _RecordingStore()
    service = UserCreateService(UserRepository(session), DbUnitOfWork(session), membership=store)

    created = await service.create_user(
        username="alice", name="爱丽丝", source="admin_create", owner_tenant_id=DEMO_TENANT_ID
    )
    assert created.created is True and created.user is not None
    assert list(store.calls) == [(DEMO_TENANT_ID, created.user.id, DEMO_TENANT_ID, "admin_create")]

    skipped = await service.create_user(username="bob", name="鲍勃", owner_tenant_id=None)
    assert skipped.created is True
    assert len(store.calls) == 1

    no_store = UserCreateService(UserRepository(session), DbUnitOfWork(session))
    assert (await no_store.create_user(username="carol", name="卡罗尔", owner_tenant_id=DEMO_TENANT_ID)).created is True
    await engine.dispose()


@pytest.mark.kiwi_id(2198)
async def test_service_create_degrades_when_membership_fails() -> None:
    """服务层：关系写入失败不阻断建号（降级记日志）。"""
    session, engine = await _session()
    service = UserCreateService(UserRepository(session), DbUnitOfWork(session), membership=_RecordingStore(fail=True))

    result = await service.create_user(username="dave", name="戴夫", owner_tenant_id=DEMO_TENANT_ID)
    assert result.created is True and result.user is not None
    await engine.dispose()


@pytest.mark.kiwi_id(2198)
async def test_internal_create_passes_source_and_tenant(client: AsyncClient, service_app: FastAPI) -> None:
    """端点：建号透传 `source`，并以解析链租户为主体的归属租户建立关系。"""
    session, engine = await _session()
    store = _RecordingStore()
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    service_app.dependency_overrides[get_tenant_membership_store] = lambda: store
    service_app.dependency_overrides[get_tenant] = lambda: TenantContext(
        code="demo", db_key="tenant_demo", name="演示租户", tenant_id=DEMO_TENANT_ID
    )
    service_app.dependency_overrides[get_uow] = lambda: DbUnitOfWork(session)

    resp = await client.post(
        API,
        json={"username": "erin", "name": "艾琳", "source": "import"},
        headers={"Authorization": "Bearer identity"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["created"] is True
    calls = list(store.calls)
    assert len(calls) == 1
    assert calls[0][0] == DEMO_TENANT_ID
    assert calls[0][2] == DEMO_TENANT_ID
    assert calls[0][3] == "import"
    await session.close()
    await engine.dispose()
