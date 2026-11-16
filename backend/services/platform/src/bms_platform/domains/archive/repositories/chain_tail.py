"""归档链尾仓储（平台库）：审计分片删表前写入、校验器读取。"""

from __future__ import annotations

from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.models.platform.archive import SysArchiveChainTail

__all__ = ["ArchiveChainTailRepository"]


class ArchiveChainTailRepository(BaseFrameworkObject):
    """归档链尾读写（事务边界归调用方）。"""

    def __init__(self, session: DbSession) -> None:
        """初始化。

        Args:
            session: 平台库会话。
        """
        self._session = session

    async def get(self, log_type: str, month: str, tenant_key: str) -> SysArchiveChainTail | None:
        """按唯一键取链尾。

        Args:
            log_type: 日志类型。
            month: 分片月份。
            tenant_key: 租户键。

        Returns:
            SysArchiveChainTail | None: 命中返回链尾。
        """
        result = await self._session.execute(
            select(SysArchiveChainTail).where(
                SysArchiveChainTail.log_type == log_type,
                SysArchiveChainTail.shard_month == month,
                SysArchiveChainTail.tenant_key == tenant_key,
                SysArchiveChainTail.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        log_type: str,
        month: str,
        tenant_key: str,
        first_prev_hash: str,
        last_record_hash: str,
        record_count: int,
        archive_log_id: int,
    ) -> SysArchiveChainTail:
        """写入 / 校正一条链尾（删除物理分片前调用）。

        Args:
            log_type: 日志类型。
            month: 分片月份。
            tenant_key: 租户键。
            first_prev_hash: 首条 prev_hash。
            last_record_hash: 末条 record_hash。
            record_count: 记录条数。
            archive_log_id: 归档批次主键。

        Returns:
            SysArchiveChainTail: 链尾行。
        """
        existing = await self.get(log_type, month, tenant_key)
        if existing is None:
            existing = SysArchiveChainTail(
                log_type=log_type,
                shard_month=month,
                tenant_key=tenant_key,
                first_prev_hash=first_prev_hash,
                last_record_hash=last_record_hash,
                record_count=record_count,
                archive_log_id=archive_log_id,
            )
            self._session.add(existing)
        else:
            existing.first_prev_hash = first_prev_hash
            existing.last_record_hash = last_record_hash
            existing.record_count = record_count
            existing.archive_log_id = archive_log_id
        await self._session.flush()
        return existing

    async def list_month(self, log_type: str, month: str) -> ConcurrentStableList[SysArchiveChainTail]:
        """取某月全部租户链尾。

        Args:
            log_type: 日志类型。
            month: 分片月份。

        Returns:
            ConcurrentStableList[SysArchiveChainTail]: 链尾行。
        """
        result = await self._session.execute(
            select(SysArchiveChainTail)
            .where(
                SysArchiveChainTail.log_type == log_type,
                SysArchiveChainTail.shard_month == month,
                SysArchiveChainTail.deleted_at.is_(None),
            )
            .order_by(SysArchiveChainTail.tenant_key)
        )
        return ConcurrentStableList(result.scalars().all())
