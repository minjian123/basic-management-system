"""用户↔租户可达关系仓储（`sys_user_tenant` 读写唯一入口，11_01）。

- 只读：`list_active_targets`（有效目标租户，join `sys_tenant` 取编码 / 名称 / 域名）、
  `get`（按唯一键取行，含软删除过滤）、`has_any`（是否已有任何未软删行）、`target_tenant`（按主键取租户行）。
- 写路径：`create` / `set_status`（建 / 复活 / 回收）——调用方负责事务边界（经服务层 `UnitOfWork`）。
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_user_tenant`）。
"""

from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.tenant.membership import TenantMembershipTarget
from bms_tenant.models.tenant import SysTenant
from bms_tenant.models.user_tenant import SysUserTenant

__all__ = ["ACTIVE_MEMBERSHIP_STATUS", "TenantMembershipRepository", "to_target"]

ACTIVE_MEMBERSHIP_STATUS = "active"
"""关系有效状态（读路径只取该状态）。"""


class TenantMembershipRepository(BaseFrameworkObject):
    """用户↔租户可达关系仓储（会话绑定；调用方负责事务边界）。"""

    def __init__(self, session: DbSession) -> None:
        """初始化。

        Args:
            session: 数据库会话（异步会话或达梦同步门面）。
        """
        self._session = session

    async def list_targets(
        self, *, tenant_id: int, user_id: int, include_disabled: bool = False
    ) -> ConcurrentStableList[TenantMembershipTarget]:
        """取某用户可访问目标租户集合（join `sys_tenant`）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            include_disabled: 是否含 `disabled` 行（缺省只取有效行）。

        Returns:
            ConcurrentStableList[TenantMembershipTarget]: 目标集合（按目标租户主键升序）。
        """
        conditions = [
            SysUserTenant.tenant_id == tenant_id,
            SysUserTenant.user_id == user_id,
            SysUserTenant.deleted_at.is_(None),
            SysTenant.deleted_at.is_(None),
        ]
        if not include_disabled:
            conditions.append(SysUserTenant.status == ACTIVE_MEMBERSHIP_STATUS)
        statement = (
            select(SysUserTenant, SysTenant)
            .join(SysTenant, SysUserTenant.target_tenant_id == SysTenant.id)
            .where(*conditions)
            .order_by(SysUserTenant.target_tenant_id)
        )
        rows = (await self._session.execute(statement)).all()
        return ConcurrentStableList([to_target(membership, tenant) for membership, tenant in rows])

    async def get(self, *, tenant_id: int, user_id: int, target_tenant_id: int) -> SysUserTenant | None:
        """按唯一键取未软删关系行。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            target_tenant_id: 目标租户主键。

        Returns:
            SysUserTenant | None: 关系行；未命中返回 None。
        """
        statement = (
            select(SysUserTenant)
            .where(
                SysUserTenant.tenant_id == tenant_id,
                SysUserTenant.user_id == user_id,
                SysUserTenant.target_tenant_id == target_tenant_id,
                SysUserTenant.deleted_at.is_(None),
            )
            .limit(1)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_tenant_rows(self, *, tenant_id: int) -> ConcurrentStableList[SysUserTenant]:
        """取该归属租户下全部未软删关系行（对账巡检用）。

        Args:
            tenant_id: 归属租户主键。

        Returns:
            ConcurrentStableList[SysUserTenant]: 关系行集合（按用户 / 目标租户主键升序）。
        """
        statement = (
            select(SysUserTenant)
            .where(SysUserTenant.tenant_id == tenant_id, SysUserTenant.deleted_at.is_(None))
            .order_by(SysUserTenant.user_id, SysUserTenant.target_tenant_id)
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def list_rows(self, *, tenant_id: int, user_id: int) -> ConcurrentStableList[SysUserTenant]:
        """取该用户全部未软删关系行（回收与巡检用）。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[SysUserTenant]: 关系行集合（按目标租户主键升序）。
        """
        statement = (
            select(SysUserTenant)
            .where(
                SysUserTenant.tenant_id == tenant_id,
                SysUserTenant.user_id == user_id,
                SysUserTenant.deleted_at.is_(None),
            )
            .order_by(SysUserTenant.target_tenant_id)
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def target_tenant(self, target_tenant_id: int) -> SysTenant | None:
        """按主键取未软删租户行（目标租户元信息）。

        Args:
            target_tenant_id: 目标租户主键。

        Returns:
            SysTenant | None: 租户行；未命中返回 None。
        """
        statement = select(SysTenant).where(SysTenant.id == target_tenant_id, SysTenant.deleted_at.is_(None)).limit(1)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def create(
        self,
        *,
        tenant_id: int,
        user_id: int,
        target_tenant_id: int,
        source: str,
        status: str = ACTIVE_MEMBERSHIP_STATUS,
    ) -> SysUserTenant:
        """新建关系行。

        Args:
            tenant_id: 归属租户主键。
            user_id: 用户主键。
            target_tenant_id: 目标租户主键。
            source: 写入来源。
            status: 初始状态（缺省 `active`）。

        Returns:
            SysUserTenant: 新建关系行。
        """
        row = SysUserTenant(
            tenant_id=tenant_id,
            user_id=user_id,
            target_tenant_id=target_tenant_id,
            source=source,
            status=status,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def set_status(self, row: SysUserTenant, status: str) -> SysUserTenant:
        """变更关系状态（复活 / 回收）。

        Args:
            row: 关系行。
            status: 目标状态（`active` / `disabled`）。

        Returns:
            SysUserTenant: 更新后的关系行。
        """
        row.status = status
        await self._session.flush()
        return row


def to_target(membership: SysUserTenant, tenant: SysTenant) -> TenantMembershipTarget:
    """关系行 + 租户行 → 目标条目契约。

    Args:
        membership: 关系行。
        tenant: 目标租户行。

    Returns:
        TenantMembershipTarget: 目标条目。
    """
    return TenantMembershipTarget(
        tenant_id=int(tenant.id),
        code=tenant.code,
        name=tenant.name,
        domain=tenant.domain,
        source=membership.source,
        status=membership.status,
    )
