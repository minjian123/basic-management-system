"""审计日志查询服务：时间范围收敛、分片路由与详情（06_01）。

- **默认范围**：未给时间范围时回看 `[audit_log].query_default_days` 天；单次跨度超
  `[audit_log].max_query_days` 按参数非法（`90203`）。
- **分片路由**：取台账中落在 `[起始月-1, 结束月+1]` 的分片（覆盖跨月写入延迟），`UNION ALL` 查询。
- **详情**：由雪花 ID 反解写入月份，直接定位单一分片；台账无该分片 / 记录不存在 → `90201` / `90301`。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import AuditLogSettings
from bms_core.core.exceptions import (
    LoginLogNotFoundError,
    LogTimeRangeExceededError,
    OperationLogNotFoundError,
)
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_platform.domains.log.repositories.shard import LogShardRepository
from bms_platform.domains.log.schema import (
    LOG_TYPE_LOGIN,
    LOG_TYPE_OPERATION,
    month_key,
    month_shift,
    shard_of_id,
)

__all__ = ["LoginLogQueryService", "OperationLogQueryService"]


def _utc_now() -> datetime:
    """当前 UTC naive 时间。"""
    return datetime.now(UTC).replace(tzinfo=None)


def _naive(value: datetime | None) -> datetime | None:
    """带时区时间转 UTC naive（None 原样）。"""
    if value is None:
        return None
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def _range(
    settings: AuditLogSettings,
    occurred_from: datetime | None,
    occurred_to: datetime | None,
    *,
    now: datetime,
) -> tuple[datetime, datetime]:
    """收敛查询时间范围并校验跨度。

    Args:
        settings: 审计日志参数。
        occurred_from: 起始时间（可空）。
        occurred_to: 结束时间（可空）。
        now: 当前时间（UTC naive）。

    Returns:
        tuple[datetime, datetime]: （起始, 结束）。

    Raises:
        LogTimeRangeExceededError: 跨度超过 `max_query_days`（90203）。
    """
    start = _naive(occurred_from)
    end = _naive(occurred_to)
    if start is None:
        resolved_end = end if end is not None else now
        start = resolved_end - timedelta(days=settings.query_default_days)
        end = resolved_end
    elif end is None:
        end = now
    if end < start:
        raise LogTimeRangeExceededError("查询结束时间早于开始时间")
    if (end - start).days > settings.max_query_days:
        raise LogTimeRangeExceededError(f"查询时间范围不得超过 {settings.max_query_days} 天")
    return start, end


class _BaseLogQueryService(BaseFrameworkObject):
    """查询服务公共段（范围收敛 / 分片集合计算）。"""

    log_type: str

    def __init__(
        self,
        session: DbSession,
        settings: AuditLogSettings,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        """初始化。

        Args:
            session: 平台库只读会话。
            settings: 审计日志参数。
            clock: 当前时钟（测试可注入）。
        """
        self._repo = LogShardRepository(session)
        self._settings = settings
        self._clock = clock

    async def _months(self, start: datetime, end: datetime) -> ConcurrentStableList[str]:
        """取候选分片月份（前后各扩一月）。"""
        return await self._repo.months_between(
            self.log_type,
            month_shift(month_key(start), -1),
            month_shift(month_key(end), 1),
        )


class OperationLogQueryService(_BaseLogQueryService):
    """操作日志查询。"""

    log_type = LOG_TYPE_OPERATION

    async def page(
        self,
        *,
        user_id: int | None,
        module: str | None,
        action: str | None,
        status: int | None,
        occurred_from: datetime | None,
        occurred_to: datetime | None,
        page: int,
        size: int,
    ) -> tuple[ConcurrentStableList[ConcurrentStableDict[str, object]], int]:
        """分页查询操作日志。

        Args:
            user_id: 操作人主键。
            module: 模块（精确）。
            action: 动作（精确）。
            status: HTTP 状态码。
            occurred_from: 事件时间下界。
            occurred_to: 事件时间上界。
            page: 页码（从 1 起）。
            size: 每页条数。

        Returns:
            tuple[ConcurrentStableList[ConcurrentStableDict[str, object]], int]: （当前页, 总数）。
        """
        start, end = _range(self._settings, occurred_from, occurred_to, now=self._clock())
        months = await self._months(start, end)
        return await self._repo.page_operation(
            months,
            user_id=user_id,
            module=module,
            action=action,
            status=status,
            occurred_from=start,
            occurred_to=end,
            offset=(page - 1) * size,
            limit=size,
        )

    async def detail(self, record_id: int) -> ConcurrentStableDict[str, object]:
        """操作日志详情。

        Args:
            record_id: 主键（雪花 ID）。

        Returns:
            ConcurrentStableDict[str, object]: 行值。

        Raises:
            OperationLogNotFoundError: 分片 / 记录不存在（90201）。
        """
        month = shard_of_id(record_id)
        months = await self._repo.months_between(LOG_TYPE_OPERATION, month, month)
        if not months:
            raise OperationLogNotFoundError()
        row = await self._repo.get(LOG_TYPE_OPERATION, month, record_id)
        if row is None:
            raise OperationLogNotFoundError()
        return row


class LoginLogQueryService(_BaseLogQueryService):
    """登录日志查询。"""

    log_type = LOG_TYPE_LOGIN

    async def page(
        self,
        *,
        username: str | None,
        status: str | None,
        ip: str | None,
        occurred_from: datetime | None,
        occurred_to: datetime | None,
        page: int,
        size: int,
    ) -> tuple[ConcurrentStableList[ConcurrentStableDict[str, object]], int]:
        """分页查询登录日志。

        Args:
            username: 登录名（模糊）。
            status: 结果（success / failed）。
            ip: 客户端 IP（精确）。
            occurred_from: 事件时间下界。
            occurred_to: 事件时间上界。
            page: 页码（从 1 起）。
            size: 每页条数。

        Returns:
            tuple[ConcurrentStableList[ConcurrentStableDict[str, object]], int]: （当前页, 总数）。
        """
        start, end = _range(self._settings, occurred_from, occurred_to, now=self._clock())
        months = await self._months(start, end)
        return await self._repo.page_login(
            months,
            username=username,
            status=status,
            ip=ip,
            occurred_from=start,
            occurred_to=end,
            offset=(page - 1) * size,
            limit=size,
        )

    async def detail(self, record_id: int) -> ConcurrentStableDict[str, object]:
        """登录日志详情。

        Args:
            record_id: 主键（雪花 ID）。

        Returns:
            ConcurrentStableDict[str, object]: 行值。

        Raises:
            LoginLogNotFoundError: 分片 / 记录不存在（90301）。
        """
        month = shard_of_id(record_id)
        months = await self._repo.months_between(LOG_TYPE_LOGIN, month, month)
        if not months:
            raise LoginLogNotFoundError()
        row = await self._repo.get(LOG_TYPE_LOGIN, month, record_id)
        if row is None:
            raise LoginLogNotFoundError()
        return row
