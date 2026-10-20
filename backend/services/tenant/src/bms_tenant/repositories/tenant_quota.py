"""租户配额仓储（`sys_tenant_quota` 写路径唯一入口；任务 `04_01`）。

- 读：按租户取配额清单 / 单维度行。
- 写：默认值播种（幂等）、限额更新、**原子条件占用**（`used + amount <= limit`）与释放（下限 0）。
- 无配额行 = 不限制（占用 / 校验直接放行）。
"""

from sqlalchemy import case, select, update

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_tenant.models.tenant_quota import SysTenantQuota

__all__ = ["TenantQuotaRepository"]


class TenantQuotaRepository(BaseFrameworkObject):
    """租户配额仓储（会话绑定；调用方负责事务边界）。"""

    def __init__(self, session: DbSession) -> None:
        """初始化。

        Args:
            session: 数据库会话。
        """
        self._session = session

    async def list_by_tenant(self, tenant_id: int) -> ConcurrentStableList[SysTenantQuota]:
        """取租户配额行（未软删；按维度升序）。

        Args:
            tenant_id: 租户主键。

        Returns:
            ConcurrentStableList[SysTenantQuota]: 配额行。
        """
        statement = (
            select(SysTenantQuota)
            .where(SysTenantQuota.tenant_id == tenant_id, SysTenantQuota.deleted_at.is_(None))
            .order_by(SysTenantQuota.quota_key)
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def get(self, tenant_id: int, quota_key: str) -> SysTenantQuota | None:
        """取单维度配额行。

        Args:
            tenant_id: 租户主键。
            quota_key: 配额维度。

        Returns:
            SysTenantQuota | None: 配额行；未配置返回 None。
        """
        statement = (
            select(SysTenantQuota)
            .where(
                SysTenantQuota.tenant_id == tenant_id,
                SysTenantQuota.quota_key == quota_key,
                SysTenantQuota.deleted_at.is_(None),
            )
            .limit(1)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def ensure_default(self, *, tenant_id: int, quota_key: str, limit_value: int) -> SysTenantQuota:
        """幂等播种默认配额（不存在则建，存在不改限额）。

        Args:
            tenant_id: 租户主键。
            quota_key: 配额维度。
            limit_value: 默认限额。

        Returns:
            SysTenantQuota: 配额行。
        """
        row = await self.get(tenant_id, quota_key)
        if row is None:
            row = SysTenantQuota(tenant_id=tenant_id, quota_key=quota_key, limit_value=limit_value, used_value=0)
            self._session.add(row)
            await self._session.flush()
        return row

    async def update_limit(self, row: SysTenantQuota, limit_value: int) -> SysTenantQuota:
        """更新限额（已用量不变）。

        Args:
            row: 配额行。
            limit_value: 新限额。

        Returns:
            SysTenantQuota: 更新后的配额行。
        """
        row.limit_value = limit_value
        await self._session.flush()
        return row

    async def consume(self, *, tenant_id: int, quota_key: str, amount: int) -> bool:
        """原子条件占用（`used_value + amount <= limit_value`）。

        Args:
            tenant_id: 租户主键。
            quota_key: 配额维度。
            amount: 占用数量（正数）。

        Returns:
            bool: 占用成功 True；无配额行或超限 False（调用方区分「不限制」与「超限」）。
        """
        row = await self.get(tenant_id, quota_key)
        if row is None:
            return False
        statement = (
            update(SysTenantQuota)
            .where(
                SysTenantQuota.id == row.id,
                SysTenantQuota.deleted_at.is_(None),
                SysTenantQuota.used_value + amount <= SysTenantQuota.limit_value,
            )
            .values(used_value=SysTenantQuota.used_value + amount)
        )
        result = await self._session.execute(statement)
        return int(getattr(result, "rowcount", 0) or 0) == 1

    async def release(self, *, tenant_id: int, quota_key: str, amount: int) -> int:
        """释放用量（`max(0, used_value - amount)`；无配额行空操作）。

        Args:
            tenant_id: 租户主键。
            quota_key: 配额维度。
            amount: 释放数量（正数）。

        Returns:
            int: 释放后的已用量；无配额行返回 0。
        """
        row = await self.get(tenant_id, quota_key)
        if row is None:
            return 0
        released = case((SysTenantQuota.used_value - amount < 0, 0), else_=SysTenantQuota.used_value - amount)
        statement = (
            update(SysTenantQuota)
            .where(SysTenantQuota.id == row.id, SysTenantQuota.deleted_at.is_(None))
            .values(used_value=released)
        )
        await self._session.execute(statement)
        updated = await self.get(tenant_id, quota_key)
        return int(updated.used_value) if updated is not None else 0
