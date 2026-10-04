"""本地关系数据源：租户与配置服务直读 / 直写自身平台服务库 `sys_user_tenant`（11_01）。

- 数据所有权：本服务是 `sys_user_tenant` 的**唯一写方**；其他服务经关系数据源远端实现
  （`bms_core/tenant/membership_remote.py`）调用本服务内部端点。
- 会话：每次操作经 `session_scope(db_key=PLATFORM_DB_KEY)` 开会话（写走主库、读同库），
  经 `DbUnitOfWork` 包事务；事务边界归 `TenantMembershipService`。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.registry import PLATFORM_DB_KEY, EngineRegistry
from bms_core.db.session import SessionFactory, session_scope
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.tenant.membership import (
    LOCAL_TENANT_MEMBERSHIP_STORE,
    TenantMembershipTarget,
    register_tenant_membership_store,
)
from bms_tenant.repositories.tenant_membership import TenantMembershipRepository
from bms_tenant.services.membership import TenantMembershipService

if TYPE_CHECKING:  # pragma: no cover - 仅类型检查用（本地实现不依赖服务间调用）
    from bms_core.servicecall.base import BaseServiceClient

__all__ = [
    "LOCAL_TENANT_MEMBERSHIP_STORE",
    "LocalTenantMembershipStore",
    "register_local_tenant_membership_store",
]


class LocalTenantMembershipStore(BaseFrameworkObject):
    """本地关系数据源：查 / 写本服务平台库（实现 `TenantMembershipStore` 契约）。"""

    def __init__(self, registry: EngineRegistry, *, session_factory: SessionFactory | None = None) -> None:
        """初始化。

        Args:
            registry: 引擎注册表（经平台服务库取数）。
            session_factory: 会话工厂（缺省 `SessionFactory()`）。
        """
        self._registry = registry
        self._session_factory = session_factory

    async def list_targets(
        self, *, tenant_id: int, user_id: int, include_disabled: bool = False
    ) -> ConcurrentStableList[TenantMembershipTarget]:
        """取某用户可访问目标租户集合。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            include_disabled: 是否含 `disabled` 行。

        Returns:
            ConcurrentStableList[TenantMembershipTarget]: 目标集合。
        """
        async with self._service() as service:
            return await service.list_targets(tenant_id=tenant_id, user_id=user_id, include_disabled=include_disabled)

    async def ensure(
        self, *, tenant_id: int, user_id: int, target_tenant_id: int, source: str
    ) -> TenantMembershipTarget:
        """建立 / 复活关系（幂等）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            target_tenant_id: 目标租户主键。
            source: 写入来源。

        Returns:
            TenantMembershipTarget: 建立 / 复活后的目标条目。
        """
        async with self._service() as service:
            return await service.ensure(
                tenant_id=tenant_id, user_id=user_id, target_tenant_id=target_tenant_id, source=source
            )

    async def revoke(self, *, tenant_id: int, user_id: int, target_tenant_id: int) -> None:
        """回收单个目标租户关系（置 `disabled`，幂等）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            target_tenant_id: 目标租户主键。
        """
        async with self._service() as service:
            await service.revoke(tenant_id=tenant_id, user_id=user_id, target_tenant_id=target_tenant_id)

    async def revoke_all(self, *, tenant_id: int, user_id: int) -> None:
        """回收该用户全部目标租户关系（置 `disabled`，幂等）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
        """
        async with self._service() as service:
            await service.revoke_all(tenant_id=tenant_id, user_id=user_id)

    @asynccontextmanager
    async def _service(self) -> AsyncGenerator[TenantMembershipService]:
        """打开平台服务库会话并装配关系服务（会话退出即释放）。

        Yields:
            TenantMembershipService: 会话绑定的关系服务。
        """
        async with session_scope(self._registry, db_key=PLATFORM_DB_KEY, factory=self._session_factory) as session:
            yield TenantMembershipService(TenantMembershipRepository(session), DbUnitOfWork(session))


def register_local_tenant_membership_store() -> None:
    """向共享基座登记 `local` 实现（本服务模块导入时调用，幂等）。"""

    def _factory(
        *,
        settings: Settings,
        registry: EngineRegistry,
        session_factory: SessionFactory | None,
        service_client: BaseServiceClient | None,
    ) -> LocalTenantMembershipStore:
        """构造本地关系数据源。"""
        del settings, service_client  # 本地实现只需平台库引擎与会话工厂
        return LocalTenantMembershipStore(registry, session_factory=session_factory)

    register_tenant_membership_store(LOCAL_TENANT_MEMBERSHIP_STORE, _factory)
