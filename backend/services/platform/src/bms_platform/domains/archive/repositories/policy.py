"""归档策略仓储（平台库）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.models.platform.archive import (
    ARCHIVE_LOG_STATUS_RUNNING,
    ARCHIVE_POLICY_STATUS_ENABLED,
    SysArchiveLog,
    SysArchivePolicy,
)

__all__ = ["ArchivePolicyRepository"]


class ArchivePolicyRepository(BaseFrameworkObject):
    """归档策略读写（事务边界归调用方）。"""

    def __init__(self, session: DbSession) -> None:
        """初始化。

        Args:
            session: 平台库会话。
        """
        self._session = session

    async def get(self, policy_id: int) -> SysArchivePolicy | None:
        """按主键取未软删策略。

        Args:
            policy_id: 策略主键。

        Returns:
            SysArchivePolicy | None: 命中返回策略。
        """
        result = await self._session.execute(
            select(SysArchivePolicy).where(
                SysArchivePolicy.id == policy_id,
                SysArchivePolicy.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def by_table(self, table_name: str) -> SysArchivePolicy | None:
        """按表名取未软删策略。

        Args:
            table_name: 逻辑表名。

        Returns:
            SysArchivePolicy | None: 命中返回策略。
        """
        result = await self._session.execute(
            select(SysArchivePolicy).where(
                SysArchivePolicy.table_name == table_name,
                SysArchivePolicy.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def enabled(self) -> ConcurrentStableList[SysArchivePolicy]:
        """取全部启用策略（按主键升序）。

        Returns:
            ConcurrentStableList[SysArchivePolicy]: 策略列表。
        """
        result = await self._session.execute(
            select(SysArchivePolicy)
            .where(
                SysArchivePolicy.status == ARCHIVE_POLICY_STATUS_ENABLED,
                SysArchivePolicy.deleted_at.is_(None),
            )
            .order_by(SysArchivePolicy.id)
        )
        return ConcurrentStableList(result.scalars().all())

    async def page(
        self,
        *,
        page: int,
        size: int,
        table_name: str | None = None,
        status: str | None = None,
    ) -> tuple[ConcurrentStableList[SysArchivePolicy], int]:
        """分页查询策略。

        Args:
            page: 页码（从 1 起）。
            size: 每页条数。
            table_name: 表名筛选。
            status: 状态筛选。

        Returns:
            tuple[ConcurrentStableList[SysArchivePolicy], int]: （当前页, 总数）。
        """
        conditions: ConcurrentStableList[Any] = ConcurrentStableList((SysArchivePolicy.deleted_at.is_(None),))
        if table_name:
            conditions.append(SysArchivePolicy.table_name == table_name)
        if status:
            conditions.append(SysArchivePolicy.status == status)
        total = int(
            (
                await self._session.execute(select(func.count()).select_from(SysArchivePolicy).where(*conditions))
            ).scalar_one()
        )
        result = await self._session.execute(
            select(SysArchivePolicy)
            .where(*conditions)
            .order_by(SysArchivePolicy.table_name)
            .offset((page - 1) * size)
            .limit(size)
        )
        return ConcurrentStableList(result.scalars().all()), total

    async def running(self, policy_id: int) -> bool:
        """策略是否有执行中的批次。

        Args:
            policy_id: 策略主键。

        Returns:
            bool: 存在 `running` 记录返回 True。
        """
        result = await self._session.execute(
            select(SysArchiveLog.id)
            .where(
                SysArchiveLog.policy_id == policy_id,
                SysArchiveLog.status == ARCHIVE_LOG_STATUS_RUNNING,
                SysArchiveLog.deleted_at.is_(None),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    def add(self, policy: SysArchivePolicy) -> None:
        """新增策略（由调用方 flush / commit）。

        Args:
            policy: 策略实体。
        """
        self._session.add(policy)
