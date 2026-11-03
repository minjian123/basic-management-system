"""审计日志链写入器：幂等判重 → 取链尾 → 计算哈希 → 写分片（06_01）。

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

from bms_core.audit.hashchain import GENESIS_HASH, BaseHashChain
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import EventConsumeError
from bms_core.core.id import id_generator
from bms_core.core.logging import get_logger
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.events.base import EventEnvelope
from bms_platform.domains.log.repositories.shard import LogShardRepository
from bms_platform.domains.log.schema import (
    LOG_TYPE_LOGIN,
    LOG_TYPE_OPERATION,
    canonical_record,
    month_key,
)

__all__ = ["AuditLogWriter", "parse_occurred_at"]

_LOGGER = get_logger("bms.platform.log")


def _utc_now() -> datetime:
    """当前 UTC naive 时间。"""
    return datetime.now(UTC).replace(tzinfo=None)


def parse_occurred_at(envelope: EventEnvelope) -> datetime:
    """取事件发生时间（信封 `occurred_at`；缺失取当前 UTC）。

    Args:
        envelope: 事件信封。

    Returns:
        datetime: UTC naive 时间。
    """
    if envelope.occurred_at is not None:
        return envelope.occurred_at.astimezone(UTC).replace(tzinfo=None)
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
    ) -> None:
        """初始化。

        Args:
            session: 平台库会话（事务边界由调用方管理）。
            hash_chain: 哈希链实现。
            clock: 写入时钟（测试可注入）。
        """
        self._repo = LogShardRepository(session)
        self._chain = hash_chain
        self._clock = clock

    async def write(self, event: EventEnvelope) -> bool:
        """按事件类型写入对应日志表。

        Args:
            event: 审计事件信封。

        Returns:
            bool: 写入 True；幂等跳过 False。

        Raises:
            EventConsumeError: 事件类型未知 / 必填字段非法（毒消息）。
        """
        if event.event_type == "sys.operation.logged":
            return await self.write_operation(event)
        if event.event_type == "sys.login.logged":
            return await self.write_login(event)
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
        payload = event.payload
        now = self._clock()
        month = month_key(now)
        event_id = event.event_id
        if not event_id:
            raise EventConsumeError("操作审计事件缺少 event_id")
        await self._repo.ensure_shard(LOG_TYPE_OPERATION, month)
        if await self._repo.event_exists(LOG_TYPE_OPERATION, month, event_id):
            _LOGGER.debug("audit_log_duplicate", log_type=LOG_TYPE_OPERATION, event_id=event_id)
            return False
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
        await self._append(LOG_TYPE_OPERATION, month, values, tenant_id)
        return True

    async def write_login(self, event: EventEnvelope) -> bool:
        """写一条登录日志。

        Args:
            event: `sys.login.logged` 事件。

        Returns:
            bool: 写入 True；幂等跳过 False。

        Raises:
            EventConsumeError: 必填字段缺失 / 非法。
        """
        payload = event.payload
        now = self._clock()
        month = month_key(now)
        event_id = event.event_id
        if not event_id:
            raise EventConsumeError("登录审计事件缺少 event_id")
        await self._repo.ensure_shard(LOG_TYPE_LOGIN, month)
        if await self._repo.event_exists(LOG_TYPE_LOGIN, month, event_id):
            _LOGGER.debug("audit_log_duplicate", log_type=LOG_TYPE_LOGIN, event_id=event_id)
            return False
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
        await self._append(LOG_TYPE_LOGIN, month, values, tenant_id)
        return True

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
        values.set("created_at", self._clock())
        await self._repo.insert(log_type, month, values)
        _LOGGER.debug("audit_log_appended", log_type=log_type, month=month, record_id=str(values.get("id")))
