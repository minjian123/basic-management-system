"""租户管理服务（列表 / 详情 / 修改 / 停用 / 启用 + 事件；任务 `04_01`）。

- 数据访问：`sys_tenant` / `sys_tenant_database` / `sys_tenant_module` / `sys_tenant_quota`（tenant 服务平台库）。
- 边界：平台租户（`kind = platform`）不参与业务租户列表，且禁止停用 / 修改（只经引导维护）。
- 事件：`tenant.created/suspended/activated` 经 Outbox 与状态变更同事务。
"""

from __future__ import annotations

from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import (
    TenantAdminNotFoundError,
    TenantDomainConflictError,
    TenantStateConflictError,
)
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.events.base import EventEnvelope
from bms_core.models.tenant.tenant import (
    TENANT_KIND_PLATFORM,
    TENANT_STATUS_ACTIVE,
    TENANT_STATUS_SUSPENDED,
    SysTenant,
)
from bms_core.outbox.base import BaseOutboxStore
from bms_tenant.domains.tenant.repositories.tenant_registry import TenantRegistryRepository
from bms_tenant.domains.tenant.schemas.tenant_admin import (
    TenantDetail,
    TenantList,
    TenantListItem,
    TenantStatus,
    TenantUpdateRequest,
)
from bms_tenant.domains.tenant.services.tenant_module import TenantModuleService
from bms_tenant.domains.tenant.services.tenant_quota import TenantQuotaService

__all__ = ["TenantAdminService"]


class TenantAdminService(BaseFrameworkObject):
    """租户管理服务（会话绑定；事务边界由调用方负责）。"""

    def __init__(
        self,
        *,
        session: DbSession,
        modules: TenantModuleService,
        quotas: TenantQuotaService,
        outbox: BaseOutboxStore,
    ) -> None:
        """初始化。

        Args:
            session: 平台库会话（写）。
            modules: 租户模块服务。
            quotas: 租户配额服务。
            outbox: 事务性发件箱。
        """
        self._session = session
        self._repo = TenantRegistryRepository(session)
        self._modules = modules
        self._quotas = quotas
        self._outbox = outbox

    async def list(
        self,
        *,
        page: int,
        size: int,
        code: str | None = None,
        name: str | None = None,
        status: str | None = None,
    ) -> TenantList:
        """分页取业务租户。

        Args:
            page: 页码。
            size: 每页条数。
            code: 编码模糊筛选。
            name: 名称模糊筛选。
            status: 状态筛选。

        Returns:
            TenantList: 分页结果。
        """
        rows, total = await self._repo.page_business(page=page, size=size, code=code, name=name, status=status)
        items = ConcurrentStableList[TenantListItem]()
        for row in rows:
            module_rows = await self._modules.list_items(int(row.id))
            items.add(
                TenantListItem(
                    id=int(row.id),
                    code=row.code,
                    name=row.name,
                    domain=row.domain,
                    status=_status(row),
                    expire_at=row.expire_at,
                    modules=ConcurrentStableList(item.module_key for item in module_rows if item.status == "enabled"),
                    created_at=row.created_at,
                    version=int(row.version),
                )
            )
        return TenantList(list=items, total=total, page=page, size=size)

    async def detail(self, tenant_id: int) -> TenantDetail:
        """取租户详情（含配额与模块清单）。

        Args:
            tenant_id: 租户主键。

        Returns:
            TenantDetail: 租户详情。

        Raises:
            TenantAdminNotFoundError: 不存在（82002 / 404）。
        """
        row = await self._require(tenant_id)
        return TenantDetail(
            id=int(row.id),
            code=row.code,
            name=row.name,
            domain=row.domain,
            status=_status(row),
            expire_at=row.expire_at,
            quotas=await self._quotas.list_items(int(row.id)),
            modules=await self._modules.list_items(int(row.id)),
            created_at=row.created_at,
            updated_at=row.updated_at,
            version=int(row.version),
        )

    async def update(self, tenant_id: int, req: TenantUpdateRequest) -> TenantDetail:
        """修改租户（名称 / 域名 / 到期时间）。

        Args:
            tenant_id: 租户主键。
            req: 修改请求。

        Returns:
            TenantDetail: 更新后的详情。

        Raises:
            TenantAdminNotFoundError: 不存在（82002 / 404）。
            TenantStateConflictError: 平台租户不可修改（82003 / 409）。
            TenantDomainConflictError: 域名冲突（82004 / 409）。
        """
        row = await self._require(tenant_id)
        _ensure_business(row)
        domain = req.domain.strip().lower() if req.domain else None
        if (
            domain is not None
            and domain != row.domain
            and await self._repo.domain_taken(domain, exclude_id=int(row.id))
        ):
            raise TenantDomainConflictError(f"租户域名已被占用：{domain}")
        await self._repo.update_fields(row, name=req.name, domain=domain, expire_at=req.expire_at)
        await self._session.commit()
        return await self.detail(tenant_id)

    async def suspend(self, tenant_id: int) -> TenantDetail:
        """停用租户（置 `suspended` + 事件；引擎回收与会话撤销由 API 编排）。

        Args:
            tenant_id: 租户主键。

        Returns:
            TenantDetail: 停用后的详情。

        Raises:
            TenantAdminNotFoundError: 不存在（82002 / 404）。
            TenantStateConflictError: 平台租户 / 状态不允许（82003 / 409）。
        """
        row = await self._require(tenant_id)
        _ensure_business(row)
        if row.status != TENANT_STATUS_ACTIVE:
            raise TenantStateConflictError(f"租户状态不允许停用：{row.status}")
        row.status = TENANT_STATUS_SUSPENDED
        await self._session.flush()
        await self.enqueue_event(row, "tenant.suspended")
        await self._session.commit()
        return await self.detail(tenant_id)

    async def activate(self, tenant_id: int) -> TenantDetail:
        """启用租户（置 `active` + 事件）。

        Args:
            tenant_id: 租户主键。

        Returns:
            TenantDetail: 启用后的详情。

        Raises:
            TenantAdminNotFoundError: 不存在（82002 / 404）。
            TenantStateConflictError: 平台租户 / 状态不允许（82003 / 409）。
        """
        row = await self._require(tenant_id)
        _ensure_business(row)
        if row.status != TENANT_STATUS_SUSPENDED:
            raise TenantStateConflictError(f"租户状态不允许启用：{row.status}")
        row.status = TENANT_STATUS_ACTIVE
        await self._session.flush()
        await self.enqueue_event(row, "tenant.activated")
        await self._session.commit()
        return await self.detail(tenant_id)

    async def tenant_row(self, tenant_id: int) -> SysTenant:
        """取注册行（供 API 编排引擎回收 / 会话撤销）。

        Args:
            tenant_id: 租户主键。

        Returns:
            SysTenant: 注册行。

        Raises:
            TenantAdminNotFoundError: 不存在（82002 / 404）。
        """
        return await self._require(tenant_id)

    async def enqueue_event(self, row: SysTenant, event_type: str) -> None:
        """发布租户生命周期事件（Outbox，与状态变更同事务）。

        Args:
            row: 注册行。
            event_type: 事件类型（`tenant.created` / `tenant.suspended` / `tenant.activated`）。
        """
        payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "tenant_id": str(row.id),
                "db_key": await self._repo.db_basis(int(row.id)) or row.code,
                "status": row.status,
            }
        )
        await self._outbox.enqueue(
            self._session,
            EventEnvelope(
                event_type=event_type,
                payload=payload,
                tenant_id=str(row.id),
                aggregate_key=row.code,
            ),
        )

    async def _require(self, tenant_id: int) -> SysTenant:
        """取注册行或抛 82002。

        Args:
            tenant_id: 租户主键。

        Returns:
            SysTenant: 注册行。

        Raises:
            TenantAdminNotFoundError: 不存在（82002 / 404）。
        """
        row = await self._repo.by_id(tenant_id)
        if row is None:
            raise TenantAdminNotFoundError("租户不存在或已删除")
        return row


def _status(row: SysTenant) -> TenantStatus:
    """注册行状态 → 契约状态。

    Args:
        row: 注册行。

    Returns:
        TenantStatus: 契约状态。
    """
    return cast("TenantStatus", row.status)


def _ensure_business(row: SysTenant) -> None:
    """平台租户不允许停用 / 修改（只经引导维护）。

    Args:
        row: 注册行。

    Raises:
        TenantStateConflictError: 平台租户（82003 / 409）。
    """
    if row.kind == TENANT_KIND_PLATFORM:
        raise TenantStateConflictError("平台租户不可停用或修改（只经平台引导维护）")
