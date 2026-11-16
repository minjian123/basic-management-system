"""归档执行器：第一段（热表→归档库）、第二段（归档库→对象存储）、直冷与链校验。"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.schema import DropTable

from bms_core.audit.hashchain import BaseHashChain
from bms_core.audit.shard_repository import LogShardRepository
from bms_core.audit.shards import LOGIC_TABLES
from bms_core.audit.verifier import AuditChainVerifier
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import ArchiveChainIncompleteError
from bms_core.core.logging import get_logger
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.events.base import EventEnvelope
from bms_core.lock.base import BaseDistributedLock, build_lock_key
from bms_core.models.base import Base
from bms_core.models.platform.archive import (
    ARCHIVE_LOG_STATUS_FAILED,
    ARCHIVE_LOG_STATUS_RUNNING,
    ARCHIVE_LOG_STATUS_SKIPPED,
    ARCHIVE_LOG_STATUS_SUCCESS,
    ARCHIVE_TARGET_MINIO,
    SysArchiveLog,
    SysArchivePolicy,
    SysArchiveRecord,
)
from bms_core.outbox.store import SqlOutboxStore
from bms_core.storage.base import BaseObjectStorage
from bms_platform.domains.archive.repositories.chain_tail import ArchiveChainTailRepository
from bms_platform.domains.archive.repositories.log import ArchiveLogRepository
from bms_platform.domains.archive.repositories.policy import ArchivePolicyRepository
from bms_platform.domains.archive.repositories.record import ArchiveRecordRepository
from bms_platform.domains.archive.services.cold import ColdFile, build_cold_file, delete_cold_file, encode_value

__all__ = ["ARCHIVE_COMPLETED_EVENT", "ArchiveExecutor", "month_end"]

_LOGGER = get_logger("bms.platform.archive")

ARCHIVE_COMPLETED_EVENT = "sys.archive.completed"
"""归档批次完成事件（概况 §2.2；Webhook 不订阅）。"""

ProgressCallback = Callable[[int, "int | None"], Awaitable[None]]
CancelChecker = Callable[[], Awaitable[bool]]


def month_end(month: str) -> datetime:
    """取分片月份的月末次日零点（整月早于该时刻即满阈值）。

    Args:
        month: 分片月份（`yyyyMM`）。

    Returns:
        datetime: 下月 1 日 00:00（UTC naive）。
    """
    year = int(month[:4])
    value = int(month[4:6])
    if value == 12:
        return datetime(year + 1, 1, 1)
    return datetime(year, value + 1, 1)


class ArchiveExecutor(BaseFrameworkObject):
    """归档执行器（平台库 + 归档库双会话；事务按批次提交）。"""

    def __init__(
        self,
        platform_session: DbSession,
        archive_session: DbSession,
        *,
        settings: Settings,
        storage: BaseObjectStorage,
        chain: BaseHashChain,
        lock: BaseDistributedLock,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """初始化。

        Args:
            platform_session: 平台库会话。
            archive_session: 归档库会话。
            settings: 应用配置。
            storage: 对象存储。
            chain: 哈希链实现。
            lock: 分布式锁。
            clock: 当前时钟（测试可注入）。
        """
        self._platform = platform_session
        self._archive = archive_session
        self._settings = settings
        self._storage = storage
        self._chain = chain
        self._lock = lock
        self._clock = clock or _utc_now
        self._policies = ArchivePolicyRepository(platform_session)
        self._logs = ArchiveLogRepository(platform_session)
        self._records = ArchiveRecordRepository(archive_session)
        self._tails = ArchiveChainTailRepository(platform_session)
        self._shards = LogShardRepository(platform_session)

    async def run(
        self,
        *,
        policy_ids: ConcurrentStableList[int] | None = None,
        operator_id: int | None = None,
        progress: ProgressCallback | None = None,
        should_cancel: CancelChecker | None = None,
    ) -> ConcurrentStableDict[str, object]:
        """执行归档（指定策略或全部启用策略）。

        Args:
            policy_ids: 指定策略主键（None = 全部启用策略）。
            operator_id: 操作人（手动触发）。
            progress: 进度回调（`(done, total)`）。
            should_cancel: 取消检查回调。

        Returns:
            ConcurrentStableDict[str, object]: 执行摘要。
        """
        now = self._clock()
        reclaimed = await self._logs.reclaim_stale(
            now - timedelta(seconds=self._settings.archive_options.running_timeout_seconds)
        )
        await self._platform.commit()
        policies: ConcurrentStableList[SysArchivePolicy] = ConcurrentStableList()
        if policy_ids is None:
            policies = await self._policies.enabled()
        else:
            for policy_id in policy_ids:
                policy = await self._policies.get(policy_id)
                if policy is not None:
                    policies.append(policy)
        summary: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {"policies": len(policies), "archived": 0, "cold": 0, "failed": 0, "reclaimed": reclaimed}
        )
        for index, policy in enumerate(policies, start=1):
            if should_cancel is not None and await should_cancel():
                break
            result = await self._run_policy(policy, operator_id=operator_id)
            summary["archived"] = int(str(summary["archived"])) + int(str(result.get("archived", 0)))
            summary["cold"] = int(str(summary["cold"])) + int(str(result.get("cold", 0)))
            if result.get("failed"):
                summary["failed"] = int(str(summary["failed"])) + 1
            if progress is not None:
                await progress(index, len(policies))
        return summary

    async def _run_policy(
        self, policy: SysArchivePolicy, *, operator_id: int | None
    ) -> ConcurrentStableDict[str, object]:
        """执行单条策略（锁 + 日志 + 两段式）。"""
        lock_key = build_lock_key(tenant=None, resource=f"archive:{policy.id}")
        token = await self._lock.acquire(lock_key, ttl=self._settings.archive_options.running_timeout_seconds, wait=0)
        if token is None and await self._policies.running(policy.id):
            await self._skipped(policy, operator_id, "策略执行中，跳过本次触发")
            return ConcurrentStableDict({"archived": 0, "cold": 0, "failed": False, "skipped": True})
        if token is None:
            await self._skipped(policy, operator_id, "未取得策略执行锁，跳过本次触发")
            return ConcurrentStableDict({"archived": 0, "cold": 0, "failed": False, "skipped": True})
        try:
            return await self._execute_locked(policy, operator_id=operator_id)
        finally:
            await self._lock.release(lock_key, token)

    async def _execute_locked(
        self, policy: SysArchivePolicy, *, operator_id: int | None
    ) -> ConcurrentStableDict[str, object]:
        """持锁执行策略主体。"""
        policy_id = int(policy.id)
        table_name = policy.table_name
        target = policy.target
        log = await self._start_log(policy, target=target, operator_id=operator_id, tenant_id=None)
        log_id = int(log.id)
        archived = 0
        cold = 0
        try:
            if target == ARCHIVE_TARGET_MINIO:
                cold = await self._direct_cold(policy, operator_id=operator_id)
            else:
                archived = await self._archive_hot(policy, batch_id=int(log.id))
                cold = await self._cold_archive(policy, operator_id=operator_id)
            await self._finish_log(
                log,
                status=ARCHIVE_LOG_STATUS_SUCCESS,
                archived_count=archived + cold,
                detail=ConcurrentStableDict({"archived": archived, "cold": cold}),
                policy=policy,
            )
            return ConcurrentStableDict({"archived": archived, "cold": cold, "failed": False})
        except ArchiveChainIncompleteError as exc:
            await self._platform.rollback()
            await self._archive.rollback()
            fresh = await self._policies.get(policy_id)
            if fresh is not None:
                await self._fail_log(log_id, message=str(exc), policy=fresh)
            _LOGGER.error("archive_chain_broken", policy_id=str(policy_id), table=table_name, detail=str(exc))
            return ConcurrentStableDict({"archived": archived, "cold": cold, "failed": True})
        except Exception as exc:
            await self._platform.rollback()
            await self._archive.rollback()
            fresh = await self._policies.get(policy_id)
            if fresh is not None:
                await self._fail_log(log_id, message=f"{type(exc).__name__}: {exc}", policy=fresh)
            _LOGGER.error("archive_batch_failed", policy_id=str(policy_id), table=table_name, error=repr(exc))
            return ConcurrentStableDict({"archived": archived, "cold": cold, "failed": True})

    async def _archive_hot(self, policy: SysArchivePolicy, *, batch_id: int) -> int:
        """第一段：热表 → 归档库。"""
        log_type = _log_type_of(policy.table_name)
        if log_type is not None:
            return await self._archive_shards(policy, batch_id=batch_id)
        return await self._archive_normal(policy, batch_id=batch_id)

    async def _archive_shards(self, policy: SysArchivePolicy, *, batch_id: int) -> int:
        """审计分片整月归档（链校验 → 迁归档库 → 写链尾 → 删表 → 台账 archived）。"""
        log_type = str(_log_type_of(policy.table_name))
        cutoff = self._clock() - timedelta(days=policy.threshold_days)
        outcome = await AuditChainVerifier(self._platform, self._chain).verify(log_type, None)
        if not outcome.valid:
            raise ArchiveChainIncompleteError(
                f"审计链校验不通过：month={outcome.broken_month} index={outcome.broken_index} "
                f"record_id={outcome.broken_record_id}"
            )
        months = ConcurrentStableList(
            row.shard_month
            for row in await self._shards.ledger(log_type)
            if row.status == "active" and month_end(row.shard_month) <= cutoff
        )
        total = 0
        for month in months:
            table = self._shards.table_for(log_type, month)
            result = await self._platform.execute(select(table).order_by(table.c.id))
            rows = ConcurrentStableList(result.mappings().all())
            if not rows:
                await self._platform.execute(DropTable(table))
                await self._shards.mark_archived(log_type, month)
                await self._platform.commit()
                continue
            inserted = await self._insert_records(
                policy=policy,
                batch_id=batch_id,
                source_table=policy.table_name,
                source_month=month,
                rows=rows,
            )
            await self._archive.commit()
            await self._write_chain_tails(log_type=log_type, month=month, rows=rows, batch_id=batch_id)
            await self._platform.execute(DropTable(table))
            await self._shards.mark_archived(log_type, month)
            await self._platform.commit()
            total += inserted
        return total

    async def _archive_normal(self, policy: SysArchivePolicy, *, batch_id: int) -> int:
        """普通平台表按时间字段分批迁移。"""
        table = Base.metadata.tables[policy.table_name]
        time_column = table.columns[policy.time_field]
        id_column = table.columns["id"]
        cutoff = self._clock() - timedelta(days=policy.threshold_days)
        total = 0
        while total < self._settings.archive_options.max_batch_rows:
            result = await self._platform.execute(
                select(table).where(time_column < cutoff).order_by(time_column, id_column).limit(policy.batch_size)
            )
            rows = ConcurrentStableList(result.mappings().all())
            if not rows:
                break
            inserted = await self._insert_records(
                policy=policy,
                batch_id=batch_id,
                source_table=policy.table_name,
                source_month=None,
                rows=rows,
            )
            await self._archive.commit()
            ids = ConcurrentStableList(int(row["id"]) for row in rows)
            await self._platform.execute(delete(table).where(id_column.in_(list(ids))))
            await self._platform.commit()
            total += inserted
            if len(rows) < policy.batch_size:
                break
        return total

    async def _insert_records(
        self,
        *,
        policy: SysArchivePolicy,
        batch_id: int,
        source_table: str,
        source_month: str | None,
        rows: ConcurrentStableList[Any],
    ) -> int:
        """把源行写入归档库（已归档的源主键跳过）。"""
        source_ids = ConcurrentStableList(str(row["id"]) for row in rows)
        existing = await self._records.existing_source_ids(source_table, source_ids)
        archived_at = self._clock()
        records: ConcurrentStableList[SysArchiveRecord] = ConcurrentStableList()
        for row in rows:
            source_id = str(row["id"])
            if source_id in existing:
                continue
            values = ConcurrentStableDict(dict(row))
            records.add(
                SysArchiveRecord(
                    tenant_id=_optional_int(values.get("tenant_id")),
                    source_table=source_table,
                    source_id=source_id,
                    source_month=source_month,
                    policy_id=int(policy.id),
                    batch_id=batch_id,
                    payload=json.dumps(
                        {key: encode_value(value) for key, value in values.items()},
                        ensure_ascii=False,
                        default=str,
                    ),
                    archived_at=archived_at,
                )
            )
        return await self._records.insert_many(records)

    async def _write_chain_tails(
        self, *, log_type: str, month: str, rows: ConcurrentStableList[Any], batch_id: int
    ) -> None:
        """按租户写链尾（删表前）。"""
        grouped: ConcurrentStableDict[str, ConcurrentStableList[Any]] = ConcurrentStableDict()
        for row in rows:
            tenant_id = row.get("tenant_id")
            key = "global" if tenant_id is None else str(tenant_id)
            self._push(grouped, key, row)
        for tenant_key, group in grouped.items():
            await self._tails.upsert(
                log_type=log_type,
                month=month,
                tenant_key=tenant_key,
                first_prev_hash=str(group[0].get("prev_hash") or ""),
                last_record_hash=str(group[-1].get("record_hash") or ""),
                record_count=len(group),
                archive_log_id=batch_id,
            )

    async def _cold_archive(self, policy: SysArchivePolicy, *, operator_id: int | None) -> int:
        """第二段：归档库满保留期数据冷化到对象存储。"""
        before = self._clock() - timedelta(days=policy.retention_days)
        rows = await self._records.expired(
            policy_id=int(policy.id), before=before, limit=self._settings.archive_options.cold_chunk_rows
        )
        if not rows:
            return 0
        grouped: ConcurrentStableDict[str, ConcurrentStableList[SysArchiveRecord]] = ConcurrentStableDict()
        for row in rows:
            key = "global" if row.tenant_id is None else str(row.tenant_id)
            self._push(grouped, key, row)
        total = 0
        for tenant_key, group in grouped.items():
            total += await self._cold_group(policy, tenant_key=tenant_key, rows=group, operator_id=operator_id)
        return total

    async def _direct_cold(self, policy: SysArchivePolicy, *, operator_id: int | None) -> int:
        """直冷：热表数据直接导出对象存储。"""
        table = Base.metadata.tables[policy.table_name]
        time_column = table.columns[policy.time_field]
        id_column = table.columns["id"]
        cutoff = self._clock() - timedelta(days=policy.threshold_days)
        total = 0
        while total < self._settings.archive_options.max_batch_rows:
            result = await self._platform.execute(
                select(table)
                .where(time_column < cutoff)
                .order_by(time_column, id_column)
                .limit(self._settings.archive_options.cold_chunk_rows)
            )
            rows = ConcurrentStableList(result.mappings().all())
            if not rows:
                break
            bucket: ConcurrentStableDict[str, ConcurrentStableList[Any]] = ConcurrentStableDict()
            for row in rows:
                key = "global" if row.get("tenant_id") is None else str(row.get("tenant_id"))
                self._push(bucket, key, ConcurrentStableDict(dict(row)))
            for tenant_key, group in bucket.items():
                total += await self._cold_hot_group(policy, tenant_key=tenant_key, rows=group, operator_id=operator_id)
            ids = ConcurrentStableList(int(row["id"]) for row in rows)
            await self._platform.execute(delete(table).where(id_column.in_(list(ids))))
            await self._platform.commit()
            if len(rows) < self._settings.archive_options.cold_chunk_rows:
                break
        return total

    async def _cold_group(
        self,
        policy: SysArchivePolicy,
        *,
        tenant_key: str,
        rows: ConcurrentStableList[SysArchiveRecord],
        operator_id: int | None,
    ) -> int:
        """冷化一组归档行（同一租户）并删除归档行。"""
        tenant_id = None if tenant_key == "global" else int(tenant_key)
        log = await self._start_log(policy, target=ARCHIVE_TARGET_MINIO, operator_id=operator_id, tenant_id=tenant_id)
        payload_rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList(
            ConcurrentStableDict(
                {
                    "id": str(row.id),
                    "payload": row.payload,
                    "archived_at": row.archived_at,
                    "source_month": row.source_month,
                }
            )
            for row in rows
        )
        file = await self._write_cold_file(policy, tenant_key=tenant_key, log_id=int(log.id), rows=payload_rows)
        await self._records.delete_ids(ConcurrentStableList(int(row.id) for row in rows))
        await self._archive.commit()
        await self._finish_log(
            log,
            status=ARCHIVE_LOG_STATUS_SUCCESS,
            archived_count=len(rows),
            detail=ConcurrentStableDict({"sha256": file.sha256, "row_count": file.row_count}),
            policy=policy,
            file_key=file.data_key,
        )
        return len(rows)

    async def _cold_hot_group(
        self,
        policy: SysArchivePolicy,
        *,
        tenant_key: str,
        rows: ConcurrentStableList[ConcurrentStableDict[str, object]],
        operator_id: int | None,
    ) -> int:
        """直冷一组热表行。"""
        tenant_id = None if tenant_key == "global" else int(tenant_key)
        log = await self._start_log(policy, target=ARCHIVE_TARGET_MINIO, operator_id=operator_id, tenant_id=tenant_id)
        payload_rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList(
            ConcurrentStableDict(
                {
                    "id": str(row["id"]),
                    "payload": json.dumps({key: encode_value(value) for key, value in row.items()}, default=str),
                    "archived_at": self._clock(),
                    "source_month": None,
                }
            )
            for row in rows
        )
        file = await self._write_cold_file(policy, tenant_key=tenant_key, log_id=int(log.id), rows=payload_rows)
        await self._finish_log(
            log,
            status=ARCHIVE_LOG_STATUS_SUCCESS,
            archived_count=len(rows),
            detail=ConcurrentStableDict({"sha256": file.sha256, "row_count": file.row_count}),
            policy=policy,
            file_key=file.data_key,
        )
        return len(rows)

    @staticmethod
    def _push(bucket: ConcurrentStableDict[str, ConcurrentStableList[Any]], key: str, row: object) -> None:
        """把行推入按租户分组的桶（None 安全替代 setdefault）。

        Args:
            bucket: 分组桶。
            key: 租户键。
            row: 行。
        """
        group: ConcurrentStableList[Any] | None = bucket.get(key)
        if group is None:
            group = ConcurrentStableList[Any]()
            bucket[key] = group
        group.append(row)

    async def _write_cold_file(
        self,
        policy: SysArchivePolicy,
        *,
        tenant_key: str,
        log_id: int,
        rows: ConcurrentStableList[ConcurrentStableDict[str, object]],
    ) -> ColdFile:
        """生成并上传 NDJSON.gz + 清单。"""
        file, data_bytes, manifest_bytes = build_cold_file(
            prefix=self._settings.archive_options.file_prefix,
            tenant_key=tenant_key,
            source_table=policy.table_name,
            log_id=log_id,
            rows=rows,
        )
        await self._storage.put(file.data_key, data_bytes, content_type="application/gzip")
        await self._storage.put(file.manifest_key, manifest_bytes, content_type="application/json")
        return file

    async def _start_log(
        self,
        policy: SysArchivePolicy,
        *,
        target: str,
        operator_id: int | None,
        tenant_id: int | None,
    ) -> SysArchiveLog:
        """创建 running 执行记录并提交（并发可见）。"""
        now = self._clock()
        tenant_part = "all" if tenant_id is None else str(tenant_id)
        log = SysArchiveLog(
            policy_id=int(policy.id),
            table_name=policy.table_name,
            batch_key=f"{policy.id}:{target}:{tenant_part}:{uuid4().hex}",
            target=target,
            tenant_id=tenant_id,
            status=ARCHIVE_LOG_STATUS_RUNNING,
            started_at=now,
            operator_id=operator_id,
        )
        await self._logs.add(log)
        await self._platform.commit()
        return log

    async def _finish_log(
        self,
        log: SysArchiveLog,
        *,
        status: str,
        archived_count: int,
        detail: ConcurrentStableDict[str, object],
        policy: SysArchivePolicy,
        file_key: str | None = None,
        error_msg: str | None = None,
    ) -> None:
        """回写终态并发完成事件。"""
        now = self._clock()
        retention_until = (
            now + timedelta(days=self._settings.archive_options.cleanup_retention_days)
            if file_key is not None
            else None
        )
        await self._logs.finish(
            int(log.id),
            status=status,
            finished_at=now,
            cost_time=max(0, int((now - log.started_at).total_seconds() * 1000)),
            archived_count=archived_count,
            error_msg=error_msg,
            detail=json.dumps(dict(detail), ensure_ascii=False),
            file_key=file_key,
            retention_until=retention_until,
        )
        envelope = EventEnvelope(
            event_type=ARCHIVE_COMPLETED_EVENT,
            payload=ConcurrentStableDict(
                {
                    "policy_id": str(policy.id),
                    "archived_count": archived_count,
                    "target": log.target,
                }
            ),
            aggregate_key=f"archive:{policy.id}",
        )
        await SqlOutboxStore().enqueue(self._platform, envelope)
        await self._platform.commit()

    async def _fail_log(self, log_id: int, *, message: str, policy: SysArchivePolicy) -> None:
        """回写失败终态（尽力而为；回滚后重新取记录，避免过期对象触发懒加载）。"""
        try:
            log = await self._logs.get(log_id)
            if log is None:
                return
            await self._finish_log(
                log,
                status=ARCHIVE_LOG_STATUS_FAILED,
                archived_count=0,
                detail=ConcurrentStableDict({"error": message}),
                policy=policy,
                error_msg=message[:512],
            )
        except Exception as exc:  # pragma: no cover - 失败路径的二次失败只记日志
            _LOGGER.error("archive_fail_log_failed", log_id=str(log_id), error=repr(exc))

    async def _skipped(self, policy: SysArchivePolicy, operator_id: int | None, reason: str) -> None:
        """写跳过记录（并发 / 锁失败）。"""
        log = await self._start_log(policy, target=policy.target, operator_id=operator_id, tenant_id=None)
        await self._finish_log(
            log,
            status=ARCHIVE_LOG_STATUS_SKIPPED,
            archived_count=0,
            detail=ConcurrentStableDict({"reason": reason}),
            policy=policy,
        )

    async def cleanup(self, *, limit: int | None = None) -> int:
        """清理过期冷化文件（数据 + 清单），并留痕。

        Args:
            limit: 单批上限（None 取 batch_size_default）。

        Returns:
            int: 清理条数。
        """
        now = self._clock()
        rows = await self._logs.pending_cleanup(now, limit=limit or self._settings.archive_options.batch_size_default)
        cleaned = 0
        for row in rows:
            file_key = row.file_key
            if file_key is None:  # pragma: no cover - 查询已过滤
                continue
            await delete_cold_file(self._storage, file_key)
            await self._logs.mark_disposed(int(row.id), dispose_type="cleanup", now=now)
            await self._platform.commit()
            cleaned += 1
        return cleaned


def _log_type_of(table_name: str) -> str | None:
    """按逻辑表名反查审计日志类型（非分片表返回 None）。"""
    for log_type, logical in LOGIC_TABLES.items():
        if logical == table_name:
            return log_type
    return None


def _optional_int(value: object) -> int | None:
    """把值转为 int（None / 空串为空）。"""
    if value is None or value == "":
        return None
    return int(str(value))


def _utc_now() -> datetime:
    """当前 UTC naive 时间。"""
    from datetime import UTC as _UTC

    return datetime.now(_UTC).replace(tzinfo=None)
