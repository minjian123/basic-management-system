"""审计日志仓储：分片台账、运行期建表、链尾读取、写入与查询（06_01）。

- **建表**：`ensure_shard` 幂等建物理表 + upsert 台账（`sys_audit_shard`）；分片表用独立
  `MetaData` 声明，不污染 `Base.metadata`。
- **链尾**：`last_hash_before` 从更早分片中取同租户最后一条 `record_hash`（无则空串 → 链头）。
- **查询**：台账定位分片集合后 `UNION ALL` 合并，按 `(occurred_at, id)` 倒序分页；详情由雪花 ID
  反解月份直接定位单一分片。
- 事务边界归调用方（消费处理器 / 查询服务）；本类只 `execute` / `flush`。
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import Table, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.logging import get_logger
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.db.sync import SyncSession
from bms_core.models.platform.log import SHARD_STATUS_ACTIVE, SysAuditShard
from bms_platform.domains.log.schema import (
    LOG_TYPE_LOGIN,
    LOG_TYPE_OPERATION,
    build_shard_table,
    shard_table_name,
)

__all__ = ["LogShardRepository"]

_LOGGER = get_logger("bms.platform.log")


class LogShardRepository(BaseFrameworkObject):
    """审计日志分片仓储（平台库会话）。"""

    def __init__(self, session: DbSession) -> None:
        """初始化。

        Args:
            session: 平台库会话。
        """
        self._session = session

    # ---- 台账 ----

    async def ledger(self, log_type: str) -> ConcurrentStableList[SysAuditShard]:
        """取某类日志的全部分片台账（按月份升序）。

        Args:
            log_type: 日志类型。

        Returns:
            ConcurrentStableList[SysAuditShard]: 台账行。
        """
        result = await self._session.execute(
            select(SysAuditShard)
            .where(SysAuditShard.log_type == log_type, SysAuditShard.deleted_at.is_(None))
            .order_by(SysAuditShard.shard_month)
        )
        return ConcurrentStableList(result.scalars().all())

    async def months(self, log_type: str) -> ConcurrentStableList[str]:
        """取某类日志已建分片月份（升序）。

        Args:
            log_type: 日志类型。

        Returns:
            ConcurrentStableList[str]: 月份键。
        """
        return ConcurrentStableList(row.shard_month for row in await self.ledger(log_type))

    async def months_between(self, log_type: str, start: str | None, end: str | None) -> ConcurrentStableList[str]:
        """取落在 `[start, end]` 内的分片月份（闭区间）。

        Args:
            log_type: 日志类型。
            start: 起始月份（None 不限）。
            end: 结束月份（None 不限）。

        Returns:
            ConcurrentStableList[str]: 月份键（升序）。
        """
        rows = await self.ledger(log_type)
        selected = [
            row.shard_month
            for row in rows
            if (start is None or row.shard_month >= start) and (end is None or row.shard_month <= end)
        ]
        return ConcurrentStableList(selected)

    async def _ledger_row(self, log_type: str, month: str) -> SysAuditShard | None:
        """取单月台账行。"""
        result = await self._session.execute(
            select(SysAuditShard).where(
                SysAuditShard.log_type == log_type,
                SysAuditShard.shard_month == month,
                SysAuditShard.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    # ---- 建表 ----

    async def ensure_shard(self, log_type: str, month: str) -> str:
        """确保某月分片表存在（幂等；同时 upsert 台账）。

        Args:
            log_type: 日志类型。
            month: 月份键。

        Returns:
            str: 物理表名。
        """
        physical = shard_table_name(log_type, month)
        existing = await self._ledger_row(log_type, month)
        if existing is not None:
            return physical
        table = build_shard_table(log_type, physical)
        await self._create_table(table)
        row = SysAuditShard(
            log_type=log_type,
            shard_month=month,
            physical_table=physical,
            status=SHARD_STATUS_ACTIVE,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError:
            # 并发预创建：另一实例已登记同月台账 → 视为成功
            await self._session.rollback()
            _LOGGER.debug("audit_shard_ledger_conflict", log_type=log_type, month=month)
        return physical

    async def _create_table(self, table: Table) -> None:
        """幂等建表（按方言走同会话连接，避免 SQLite 跨连接锁）。"""
        session = self._session
        if isinstance(session, SyncSession):
            await asyncio.to_thread(table.metadata.create_all, session.raw.get_bind(), tables=[table], checkfirst=True)
            return

        def _create(sync_session: Session) -> None:
            """异步会话的同步回调：取同一连接建表（避免 SQLite 跨连接锁）。"""
            table.metadata.create_all(sync_session.connection(), tables=[table], checkfirst=True)

        await session.run_sync(_create)

    # ---- 链与写入 ----

    async def event_exists(self, log_type: str, month: str, event_id: str) -> bool:
        """按事件 ID 判重（同分片内）。

        Args:
            log_type: 日志类型。
            month: 月份键。
            event_id: 事件 ID。

        Returns:
            bool: 已存在 True。
        """
        table = self._table(log_type, month)
        result = await self._session.execute(select(table.c.id).where(table.c.event_id == event_id).limit(1))
        return result.first() is not None

    async def last_hash(self, log_type: str, month: str, tenant_id: int | None) -> str:
        """取同租户链尾哈希（当月优先，其次更早分片；无则空串）。

        Args:
            log_type: 日志类型。
            month: 当前写入月份。
            tenant_id: 租户主键（None 为平台级）。

        Returns:
            str: `record_hash`；无记录返回空串。
        """
        rows = await self.ledger(log_type)
        candidates = [row.shard_month for row in rows if row.shard_month <= month]
        for candidate in reversed(candidates):
            table = self._table(log_type, candidate)
            condition = table.c.tenant_id.is_(None) if tenant_id is None else table.c.tenant_id == tenant_id
            result = await self._session.execute(
                select(table.c.record_hash).where(condition).order_by(table.c.id.desc()).limit(1)
            )
            found = result.first()
            if found is not None:
                return str(found[0])
        return ""

    async def insert(self, log_type: str, month: str, values: ConcurrentStableDict[str, object]) -> None:
        """写入一条日志（调用方负责链计算与幂等判重）。

        Args:
            log_type: 日志类型。
            month: 月份键。
            values: 行值（DB 列名 → 值）。
        """
        table = self._table(log_type, month)
        await self._session.execute(table.insert().values(**dict(values)))

    # ---- 查询 ----

    @staticmethod
    def table_for(log_type: str, month: str) -> Table:
        """取分片表定义（校验服务按整月读取用）。

        Args:
            log_type: 日志类型。
            month: 月份键。

        Returns:
            Table: 分片表定义。
        """
        return build_shard_table(log_type, shard_table_name(log_type, month))

    @classmethod
    def _table(cls, log_type: str, month: str) -> Table:
        """兼容内部简写（等同 `table_for`）。"""
        return cls.table_for(log_type, month)

    async def page_operation(
        self,
        months: Iterable[str],
        *,
        user_id: int | None,
        module: str | None,
        action: str | None,
        status: int | None,
        occurred_from: datetime,
        occurred_to: datetime,
        offset: int,
        limit: int,
    ) -> tuple[ConcurrentStableList[ConcurrentStableDict[str, object]], int]:
        """操作日志分页查询。"""
        conditions: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {"user_id": user_id, "module": module, "action": action, "status": status}
        )
        return await self.page(
            LOG_TYPE_OPERATION,
            months,
            conditions=conditions,
            fuzzy=ConcurrentStableDict[str, str](),
            occurred_from=occurred_from,
            occurred_to=occurred_to,
            offset=offset,
            limit=limit,
        )

    async def page_login(
        self,
        months: Iterable[str],
        *,
        username: str | None,
        status: str | None,
        ip: str | None,
        occurred_from: datetime,
        occurred_to: datetime,
        offset: int,
        limit: int,
    ) -> tuple[ConcurrentStableList[ConcurrentStableDict[str, object]], int]:
        """登录日志分页查询（用户名模糊匹配）。"""
        conditions: ConcurrentStableDict[str, object] = ConcurrentStableDict({"status": status, "ip": ip})
        fuzzy: ConcurrentStableDict[str, str] = ConcurrentStableDict({"username": username or ""})
        return await self.page(
            LOG_TYPE_LOGIN,
            months,
            conditions=conditions,
            fuzzy=fuzzy,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
            offset=offset,
            limit=limit,
        )

    async def page(
        self,
        log_type: str,
        months: Iterable[str],
        *,
        conditions: ConcurrentStableDict[str, object],
        fuzzy: ConcurrentStableDict[str, str],
        occurred_from: datetime,
        occurred_to: datetime,
        offset: int,
        limit: int,
    ) -> tuple[ConcurrentStableList[ConcurrentStableDict[str, object]], int]:
        """跨分片分页查询（UNION ALL + 计数；按 `(occurred_at, id)` 倒序）。

        Args:
            log_type: 日志类型。
            months: 候选分片月份。
            conditions: 精确筛选（列名 → 值；`None` 忽略）。
            fuzzy: 模糊筛选（列名 → 子串；空串忽略）。
            occurred_from: 事件时间下界（UTC naive，闭）。
            occurred_to: 事件时间上界（UTC naive，闭）。
            offset: 偏移。
            limit: 上限。

        Returns:
            tuple[ConcurrentStableList[ConcurrentStableDict[str, object]], int]: （行映射, 总数）。
        """
        selects: ConcurrentStableList[Any] = ConcurrentStableList()
        for month in months:
            table = self._table(log_type, month)
            statement = select(table)
            for name, value in conditions.items():
                if value is not None:
                    statement = statement.where(table.c[name] == value)
            for name, value in fuzzy.items():
                if value:
                    statement = statement.where(table.c[name].like(f"%{value}%"))
            statement = statement.where(table.c.occurred_at >= occurred_from, table.c.occurred_at <= occurred_to)
            selects.append(statement)
        if not selects:
            return ConcurrentStableList(), 0
        union = selects[0].union_all(*selects[1:]) if len(selects) > 1 else selects[0]
        ordered = union.subquery()
        total = int((await self._session.execute(select(func.count()).select_from(ordered))).scalar_one())
        page = select(ordered).order_by(ordered.c.occurred_at.desc(), ordered.c.id.desc()).offset(offset).limit(limit)
        result = await self._session.execute(page)
        return ConcurrentStableList(ConcurrentStableDict(dict(row)) for row in result.mappings().all()), total

    async def get(self, log_type: str, month: str, record_id: int) -> ConcurrentStableDict[str, object] | None:
        """按主键取单条（定位单一分片）。

        Args:
            log_type: 日志类型。
            month: 月份键。
            record_id: 主键。

        Returns:
            ConcurrentStableDict[str, object] | None: 行值映射；不存在 None。
        """
        table = self._table(log_type, month)
        result = await self._session.execute(select(table).where(table.c.id == record_id).limit(1))
        row = result.mappings().first()
        return None if row is None else ConcurrentStableDict(dict(row))
