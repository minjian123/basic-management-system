"""审计日志链写入器：幂等判重 → 取链尾 → 计算哈希 → 写分片（06_01 / 06_02）。

- **分片键 = 写入时刻**（`clock()`，缺省当前 UTC）：事件时间另存 `occurred_at`，避免延迟事件插入
  旧月破坏跨月链（见详细设计 §4）。
- **链序**：同一租户的写入由 `audit-chain` 有序组串行执行；`prev_hash` 取更早分片同租户末条，
  无则 `GENESIS_HASH`。
- **幂等**：同分片内 `event_id` 已存在即跳过（消费去重兜底）。
- **载荷**：事件已由捕获侧脱敏；本类不再改写敏感字段。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from bms_core.audit.events import (
    DATA_CHANGED_EVENT,
    LOGIN_LOG_EVENT,
    OPERATION_LOG_EVENT,
    normalize_occurred_at,
)
from bms_core.audit.hashchain import GENESIS_HASH, BaseHashChain
from bms_core.audit.observability import GLOBAL_TENANT_LABEL, record_audit_write
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenSet,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.exceptions import EventConsumeError
from bms_core.core.id import id_generator
from bms_core.core.logging import get_logger
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.events.base import BatchConsumeOutcome, EventEnvelope
from bms_core.metrics.base import BaseMetrics
from bms_platform.domains.log.repositories.shard import LogShardRepository
from bms_platform.domains.log.schema import (
    LOG_TYPE_DATA_AUDIT,
    LOG_TYPE_LOGIN,
    LOG_TYPE_OPERATION,
    canonical_record,
    month_key,
)

__all__ = ["AuditLogWriter", "parse_occurred_at"]

_LOGGER = get_logger("bms.platform.log")

_LOG_TYPE_OF_EVENT: ConcurrentStableFrozenDict[str, str] = ConcurrentStableFrozenDict(
    {
        OPERATION_LOG_EVENT: LOG_TYPE_OPERATION,
        LOGIN_LOG_EVENT: LOG_TYPE_LOGIN,
        DATA_CHANGED_EVENT: LOG_TYPE_DATA_AUDIT,
    }
)
"""审计事件类型 → 分片日志类型（批量写入分组用）。"""


def _utc_now() -> datetime:
    """当前 UTC naive 时间。"""
    return datetime.now(UTC).replace(tzinfo=None)


def parse_occurred_at(envelope: EventEnvelope) -> datetime:
    """取事件发生时间（信封 `occurred_at`；缺失取当前 UTC）。

    口径：与 `normalize_occurred_at` 同源——**naive 值按 UTC 解释**（库内统一 UTC naive 存储，
    发件箱读回即 naive；不能当本地时间再转一次，否则 UTC+8 开发机会整体偏移 8 小时，
    容量指标与分片月份都会跟着漂）。

    Args:
        envelope: 事件信封。

    Returns:
        datetime: UTC naive 时间。
    """
    if envelope.occurred_at is not None:
        return normalize_occurred_at(envelope.occurred_at)
    return _utc_now()


def _as_int(value: object) -> int | None:
    """把载荷值转为整数（雪花 ID 字符串 / 数字）。"""
    if value is None or value == "":
        return None
    try:
        return int(str(value))
    except ValueError as exc:
        raise EventConsumeError(f"审计事件字段应为整数：{value!r}") from exc


def _as_str(value: object) -> str | None:
    """把载荷值转为字符串（None / 空串 → None）。"""
    if value is None or value == "":
        return None
    return str(value)


class AuditLogWriter(BaseFrameworkObject):
    """审计日志写入器（操作 / 登录共用）。"""

    def __init__(
        self,
        session: DbSession,
        hash_chain: BaseHashChain,
        *,
        clock: Callable[[], datetime] = _utc_now,
        metrics: BaseMetrics | None = None,
    ) -> None:
        """初始化。

        Args:
            session: 平台库会话（事务边界由调用方管理）。
            hash_chain: 哈希链实现。
            clock: 写入时钟（测试可注入）。
            metrics: 指标器（可选；None = 不记容量指标）。
        """
        self._repo = LogShardRepository(session)
        self._chain = hash_chain
        self._clock = clock
        self._metrics = metrics

    async def write(self, event: EventEnvelope) -> bool:
        """按事件类型写入对应日志表。

        Args:
            event: 审计事件信封。

        Returns:
            bool: 写入 True；幂等跳过 False。

        Raises:
            EventConsumeError: 事件类型未知 / 必填字段非法（毒消息）。
        """
        if event.event_type == OPERATION_LOG_EVENT:
            return await self.write_operation(event)
        if event.event_type == LOGIN_LOG_EVENT:
            return await self.write_login(event)
        if event.event_type == DATA_CHANGED_EVENT:
            return await self.write_data_audit(event)
        raise EventConsumeError(f"未知审计事件类型：{event.event_type}")

    async def write_operation(self, event: EventEnvelope) -> bool:
        """写一条操作日志。

        Args:
            event: `sys.operation.logged` 事件。

        Returns:
            bool: 写入 True；幂等跳过 False。

        Raises:
            EventConsumeError: 必填字段缺失 / 非法。
        """
        now = self._clock()
        month = month_key(now)
        event_id = event.event_id
        if not event_id:
            raise EventConsumeError("操作审计事件缺少 event_id")
        await self._repo.ensure_shard(LOG_TYPE_OPERATION, month)
        if await self._repo.event_exists(LOG_TYPE_OPERATION, month, event_id):
            _LOGGER.debug("audit_log_duplicate", log_type=LOG_TYPE_OPERATION, event_id=event_id)
            return False
        values, tenant_id = self.operation_row(event)
        await self._append(LOG_TYPE_OPERATION, month, values, tenant_id)
        return True

    def operation_row(self, event: EventEnvelope) -> tuple[ConcurrentStableDict[str, object], int | None]:
        """取操作日志行值（不含链字段；批量写入复用）。

        Args:
            event: `sys.operation.logged` 事件。

        Returns:
            tuple[ConcurrentStableDict[str, object], int | None]: 行值与租户主键。

        Raises:
            EventConsumeError: 必填字段缺失 / 非法。
        """
        payload = event.payload
        event_id = event.event_id
        if not event_id:
            raise EventConsumeError("操作审计事件缺少 event_id")
        module = _as_str(payload.get("module"))
        action = _as_str(payload.get("action"))
        method = _as_str(payload.get("method"))
        path = _as_str(payload.get("path"))
        status = _as_int(payload.get("status"))
        if not module or not action or not method or not path or status is None:
            raise EventConsumeError("操作审计事件缺少必填字段（module/action/method/path/status）")
        tenant_id = _as_int(payload.get("tenant_id"))
        values: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "id": id_generator.next_id(),
                "event_id": event_id,
                "tenant_id": tenant_id,
                "user_id": _as_int(payload.get("user_id")),
                "username": _as_str(payload.get("username")),
                "module": module,
                "action": action,
                "method": method,
                "path": path,
                "query_params": _as_str(payload.get("query")),
                "params": _as_str(payload.get("params")),
                "ip": _as_str(payload.get("ip")),
                "user_agent": _as_str(payload.get("user_agent")),
                "cost_time": _as_int(payload.get("cost_time")),
                "status": status,
                "error_msg": _as_str(payload.get("error_msg")),
                "occurred_at": parse_occurred_at(event),
            }
        )
        return values, tenant_id

    async def write_login(self, event: EventEnvelope) -> bool:
        """写一条登录日志。

        Args:
            event: `sys.login.logged` 事件。

        Returns:
            bool: 写入 True；幂等跳过 False。

        Raises:
            EventConsumeError: 必填字段缺失 / 非法。
        """
        now = self._clock()
        month = month_key(now)
        event_id = event.event_id
        if not event_id:
            raise EventConsumeError("登录审计事件缺少 event_id")
        await self._repo.ensure_shard(LOG_TYPE_LOGIN, month)
        if await self._repo.event_exists(LOG_TYPE_LOGIN, month, event_id):
            _LOGGER.debug("audit_log_duplicate", log_type=LOG_TYPE_LOGIN, event_id=event_id)
            return False
        values, tenant_id = self.login_row(event)
        await self._append(LOG_TYPE_LOGIN, month, values, tenant_id)
        return True

    def login_row(self, event: EventEnvelope) -> tuple[ConcurrentStableDict[str, object], int | None]:
        """取登录日志行值（不含链字段；批量写入复用）。

        Args:
            event: `sys.login.logged` 事件。

        Returns:
            tuple[ConcurrentStableDict[str, object], int | None]: 行值与租户主键。

        Raises:
            EventConsumeError: 必填字段缺失 / 非法。
        """
        payload = event.payload
        event_id = event.event_id
        if not event_id:
            raise EventConsumeError("登录审计事件缺少 event_id")
        username = _as_str(payload.get("username"))
        status = _as_str(payload.get("status"))
        if not username or not status:
            raise EventConsumeError("登录审计事件缺少必填字段（username/status）")
        tenant_id = _as_int(payload.get("tenant_id"))
        values: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "id": id_generator.next_id(),
                "event_id": event_id,
                "tenant_id": tenant_id,
                "user_id": _as_int(payload.get("user_id")),
                "username": username,
                "ip": _as_str(payload.get("ip")),
                "user_agent": _as_str(payload.get("user_agent")),
                "status": status,
                "fail_reason": _as_str(payload.get("fail_reason")),
                "occurred_at": parse_occurred_at(event),
            }
        )
        return values, tenant_id

    async def write_data_audit(self, event: EventEnvelope) -> bool:
        """写一条字段级变更审计记录。

        Args:
            event: `sys.data.changed` 事件。

        Returns:
            bool: 写入 True；幂等跳过 False。

        Raises:
            EventConsumeError: 必填字段缺失 / 非法。
        """
        now = self._clock()
        month = month_key(now)
        event_id = event.event_id
        if not event_id:
            raise EventConsumeError("字段级审计事件缺少 event_id")
        await self._repo.ensure_shard(LOG_TYPE_DATA_AUDIT, month)
        if await self._repo.event_exists(LOG_TYPE_DATA_AUDIT, month, event_id):
            _LOGGER.debug("audit_log_duplicate", log_type=LOG_TYPE_DATA_AUDIT, event_id=event_id)
            return False
        values, tenant_id = self.data_audit_row(event)
        await self._append(LOG_TYPE_DATA_AUDIT, month, values, tenant_id)
        return True

    def data_audit_row(self, event: EventEnvelope) -> tuple[ConcurrentStableDict[str, object], int | None]:
        """取字段级审计行值（不含链字段；批量写入复用）。

        Args:
            event: `sys.data.changed` 事件。

        Returns:
            tuple[ConcurrentStableDict[str, object], int | None]: 行值与租户主键。

        Raises:
            EventConsumeError: 必填字段缺失 / 非法。
        """
        payload = event.payload
        event_id = event.event_id
        if not event_id:
            raise EventConsumeError("字段级审计事件缺少 event_id")
        table_name = _as_str(payload.get("table"))
        field = _as_str(payload.get("field"))
        if not table_name or not field:
            raise EventConsumeError("字段级审计事件缺少必填字段（table/field）")
        tenant_id = _as_int(payload.get("tenant_id"))
        domain_key = _as_str(payload.get("domain_key")) or "unknown"
        values: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "id": id_generator.next_id(),
                "event_id": event_id,
                "tenant_id": tenant_id,
                "table_name": table_name,
                "record_id": _as_int(payload.get("model_id")),
                "field": field,
                "old_value": _as_str(payload.get("old_value")),
                "new_value": _as_str(payload.get("new_value")),
                "operator_id": _as_int(payload.get("operator_id")),
                "domain_key": domain_key[:64],
                "occurred_at": parse_occurred_at(event),
            }
        )
        return values, tenant_id

    async def _append(
        self,
        log_type: str,
        month: str,
        values: ConcurrentStableDict[str, object],
        tenant_id: int | None,
    ) -> None:
        """取链尾 → 计算哈希 → 写入。

        Args:
            log_type: 日志类型。
            month: 分片月份。
            values: 业务字段。
            tenant_id: 租户主键（None 为平台级）。
        """
        prev_hash = (await self._repo.last_hash(log_type, month, tenant_id)) or GENESIS_HASH
        record = canonical_record(log_type, values)
        record_hash = self._chain.compute(prev_hash, record)
        values.set("prev_hash", prev_hash)
        values.set("record_hash", record_hash)
        written_at = self._clock()
        values.set("created_at", written_at)
        await self._repo.insert(log_type, month, values)
        await self._record_metrics(log_type, tenant_id, values.get("occurred_at"), written_at)
        _LOGGER.debug("audit_log_appended", log_type=log_type, month=month, record_id=str(values.get("id")))

    async def write_batch(
        self, events: ConcurrentStableList[EventEnvelope]
    ) -> ConcurrentStableList[BatchConsumeOutcome]:
        """批量写入（一个事务内：每链一次链尾查询 + 内存衔接哈希 + 一次 executemany）。

        语义与逐条 `write` 一致：命中幂等返回 `skipped`，毒消息返回 `failed(retryable=False)`；
        事务由调用方管理，异常向上抛出由调用方整批回滚。

        Args:
            events: 同一链键内按拉取顺序排列的事件。

        Returns:
            ConcurrentStableList[BatchConsumeOutcome]: 与入参等长的逐条结果。

        Raises:
            EventConsumeError: 批内出现链计算 / 数据库错误时整体上抛（调用方回滚并整批重试）。
        """
        outcomes: ConcurrentStableDict[int, BatchConsumeOutcome] = ConcurrentStableDict()
        month = month_key(self._clock())
        pending: ConcurrentStableDict[
            tuple[str, int | None], ConcurrentStableList[tuple[int, ConcurrentStableDict[str, object]]]
        ] = ConcurrentStableDict()
        used_types: ConcurrentStableSet[str] = ConcurrentStableSet()
        ids_by_type: ConcurrentStableDict[str, ConcurrentStableList[str]] = ConcurrentStableDict()
        for index, event in enumerate(events):
            log_type = _LOG_TYPE_OF_EVENT.get(event.event_type)
            if log_type is None:
                outcomes.set(
                    index,
                    BatchConsumeOutcome(
                        event_id=event.event_id or "",
                        kind="failed",
                        retryable=False,
                        error=f"未知审计事件类型：{event.event_type}",
                    ),
                )
                continue
            try:
                values, tenant_id = self._row_of(log_type, event)
            except EventConsumeError as exc:
                outcomes.set(
                    index,
                    BatchConsumeOutcome(event_id=event.event_id or "", kind="failed", retryable=False, error=str(exc)),
                )
                continue
            used_types.add(log_type)
            ids = ids_by_type.get(log_type)
            if ids is None:
                created_ids: ConcurrentStableList[str] = ConcurrentStableList()
                ids_by_type.set(log_type, created_ids)
                ids = created_ids
            ids.add(str(values["event_id"]))
            items = pending.get((log_type, tenant_id))
            if items is None:
                created_items: ConcurrentStableList[tuple[int, ConcurrentStableDict[str, object]]] = (
                    ConcurrentStableList()
                )
                pending.set((log_type, tenant_id), created_items)
                items = created_items
            items.add((index, values))

        existing: ConcurrentStableDict[str, ConcurrentStableFrozenSet[str]] = ConcurrentStableDict()
        for log_type in used_types:
            await self._repo.ensure_shard(log_type, month)
            existing.set(log_type, await self._repo.event_exists_many(log_type, month, ids_by_type[log_type]))

        written_at = self._clock()
        rows_by_type: ConcurrentStableDict[str, ConcurrentStableList[ConcurrentStableDict[str, object]]] = (
            ConcurrentStableDict()
        )
        seen_ids: ConcurrentStableSet[str] = ConcurrentStableSet()
        for (log_type, tenant_id), items in pending.items():
            prev_hash = (await self._repo.last_hash(log_type, month, tenant_id)) or GENESIS_HASH
            for index, values in items:
                event_id = str(values["event_id"])
                if event_id in existing[log_type] or event_id in seen_ids:
                    outcomes.set(
                        index,
                        BatchConsumeOutcome(event_id=event_id, kind="skipped"),
                    )
                    continue
                seen_ids.add(event_id)
                record = canonical_record(log_type, values)
                record_hash = self._chain.compute(prev_hash, record)
                values.set("prev_hash", prev_hash)
                values.set("record_hash", record_hash)
                values.set("created_at", written_at)
                prev_hash = record_hash
                rows = rows_by_type.get(log_type)
                if rows is None:
                    created_rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
                    rows_by_type.set(log_type, created_rows)
                    rows = created_rows
                rows.add(values)
                outcomes.set(index, BatchConsumeOutcome(event_id=event_id, kind="succeeded"))
        for log_type, rows in rows_by_type.items():
            await self._repo.insert_many(log_type, month, rows)
            for values in rows:
                tenant_value = values.get("tenant_id")
                await self._record_metrics(
                    log_type,
                    None if tenant_value is None else int(str(tenant_value)),
                    values.get("occurred_at"),
                    written_at,
                )
        _LOGGER.debug("audit_log_batch_appended", month=month, records=len(events))
        return ConcurrentStableList(
            outcomes.get(index)
            or BatchConsumeOutcome(event_id=events[index].event_id or "", kind="failed", error="批次结果缺失")
            for index in range(len(events))
        )

    def _row_of(self, log_type: str, event: EventEnvelope) -> tuple[ConcurrentStableDict[str, object], int | None]:
        """按日志类型取行值（批量写入用）。

        Args:
            log_type: 日志类型。
            event: 审计事件信封。

        Returns:
            tuple[ConcurrentStableDict[str, object], int | None]: 行值与租户主键。
        """
        if log_type == LOG_TYPE_OPERATION:
            return self.operation_row(event)
        if log_type == LOG_TYPE_LOGIN:
            return self.login_row(event)
        return self.data_audit_row(event)

    async def _record_metrics(
        self,
        log_type: str,
        tenant_id: int | None,
        occurred_at: object,
        written_at: datetime,
    ) -> None:
        """记录容量指标（写入计数 + 消费时延；指标器缺失时空操作）。

        Args:
            log_type: 日志类型。
            tenant_id: 租户主键（None 为平台级）。
            occurred_at: 事件发生时间（行值；非 datetime 按写入时刻计）。
            written_at: 落库完成时刻。
        """
        lag = (written_at - occurred_at).total_seconds() if isinstance(occurred_at, datetime) else 0.0
        await record_audit_write(
            self._metrics,
            log_type=log_type,
            tenant=GLOBAL_TENANT_LABEL if tenant_id is None else str(tenant_id),
            lag_seconds=lag,
        )
