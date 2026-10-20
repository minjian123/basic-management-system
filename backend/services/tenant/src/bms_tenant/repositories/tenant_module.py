"""租户-模块关系仓储（`sys_tenant_module` 写路径唯一入口；任务 `04_01`）。

- 读：按租户取清单 / 单模块行 / 状态集（模块门禁内部契约用）。
- 写：开通清单 upsert（`enabled`）、开关切状态（`enabled` ↔ `disabled`）；**不物理删行**（存量数据保留可查）。
"""

from datetime import UTC, datetime

from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_tenant.models.tenant_module import (
    TENANT_MODULE_DISABLED,
    TENANT_MODULE_ENABLED,
    SysTenantModule,
)

__all__ = ["TenantModuleRepository"]


def _utc_now() -> datetime:
    """当前 UTC 时间（naive，库内统一口径）。

    Returns:
        datetime: UTC 时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


class TenantModuleRepository(BaseFrameworkObject):
    """租户-模块关系仓储（会话绑定；调用方负责事务边界）。"""

    def __init__(self, session: DbSession) -> None:
        """初始化。

        Args:
            session: 数据库会话。
        """
        self._session = session

    async def list_by_tenant(self, tenant_id: int) -> ConcurrentStableList[SysTenantModule]:
        """取租户全部模块行（含已停用；不含软删）。

        Args:
            tenant_id: 租户主键。

        Returns:
            ConcurrentStableList[SysTenantModule]: 模块行（按模块标识升序）。
        """
        statement = (
            select(SysTenantModule)
            .where(SysTenantModule.tenant_id == tenant_id, SysTenantModule.deleted_at.is_(None))
            .order_by(SysTenantModule.module_key)
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def get(self, tenant_id: int, module_key: str) -> SysTenantModule | None:
        """取单模块行。

        Args:
            tenant_id: 租户主键。
            module_key: 模块标识。

        Returns:
            SysTenantModule | None: 模块行；未开通返回 None。
        """
        statement = (
            select(SysTenantModule)
            .where(
                SysTenantModule.tenant_id == tenant_id,
                SysTenantModule.module_key == module_key,
                SysTenantModule.deleted_at.is_(None),
            )
            .limit(1)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def status_map(self, tenant_id: int) -> ConcurrentStableDict[str, str]:
        """取租户模块状态映射（模块标识 → `enabled` / `disabled`）。

        Args:
            tenant_id: 租户主键。

        Returns:
            ConcurrentStableDict[str, str]: 状态映射。
        """
        rows = await self.list_by_tenant(tenant_id)
        return ConcurrentStableDict({row.module_key: row.status for row in rows})

    async def open(
        self,
        *,
        tenant_id: int,
        module_keys: ConcurrentStableList[str],
        opened_by: int | None = None,
    ) -> ConcurrentStableList[SysTenantModule]:
        """开通模块（不存在则建 `enabled`；已存在且停用则重新开通；幂等）。

        Args:
            tenant_id: 租户主键。
            module_keys: 模块标识清单（保序去重由调用方保证）。
            opened_by: 开通操作人（平台租户 `sys_user.id`；引导为 None）。

        Returns:
            ConcurrentStableList[SysTenantModule]: 本次涉及的模块行。
        """
        now = _utc_now()
        rows: ConcurrentStableList[SysTenantModule] = ConcurrentStableList()
        for module_key in module_keys:
            row = await self.get(tenant_id, module_key)
            if row is None:
                row = SysTenantModule(
                    tenant_id=tenant_id,
                    module_key=module_key,
                    status=TENANT_MODULE_ENABLED,
                    opened_by=opened_by,
                    opened_at=now,
                )
                self._session.add(row)
            elif row.status != TENANT_MODULE_ENABLED:
                row.status = TENANT_MODULE_ENABLED
                row.opened_at = now
                row.closed_at = None
                row.opened_by = opened_by
            rows.add(row)
        await self._session.flush()
        return rows

    async def set_status(self, row: SysTenantModule, status: str, *, opened_by: int | None = None) -> SysTenantModule:
        """切换模块状态（停用记 `closed_at`、开通记 `opened_at`）。

        Args:
            row: 模块行。
            status: 目标状态（`enabled` / `disabled`）。
            opened_by: 操作人（重新开通时记录；停用可为 None）。

        Returns:
            SysTenantModule: 更新后的模块行。
        """
        now = _utc_now()
        row.status = status
        if status == TENANT_MODULE_DISABLED:
            row.closed_at = now
        else:
            row.opened_at = now
            row.closed_at = None
            if opened_by is not None:
                row.opened_by = opened_by
        await self._session.flush()
        return row
