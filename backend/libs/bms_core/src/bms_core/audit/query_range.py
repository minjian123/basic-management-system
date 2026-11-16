"""审计查询时间范围收敛（基座，06_01 逻辑上移 / 06_02 复用）。

三段口径（与 06_01 详细设计一致）：

- 未给范围 → 回看 `[audit_log].query_default_days` 天；
- 只给一端 → 另一端取当前时刻；
- 跨度超 `[audit_log].max_query_days` → 参数非法（`90203`）。

操作 / 登录日志（`log` 域）与字段级变更审计（`audit` 域）共用本函数，避免两域各写一份范围规则。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bms_core.core.config import AuditLogSettings
from bms_core.core.exceptions import LogTimeRangeExceededError

__all__ = ["resolve_query_range", "to_naive"]


def to_naive(value: datetime | None) -> datetime | None:
    """带时区时间转 UTC naive（None 原样返回）。

    Args:
        value: 时间（可带时区）。

    Returns:
        datetime | None: UTC naive 时间。
    """
    if value is None:
        return None
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def resolve_query_range(
    settings: AuditLogSettings,
    occurred_from: datetime | None,
    occurred_to: datetime | None,
    *,
    now: datetime,
) -> tuple[datetime, datetime]:
    """收敛查询时间范围并校验跨度。

    Args:
        settings: 审计日志参数（`[audit_log]`）。
        occurred_from: 起始时间（可空）。
        occurred_to: 结束时间（可空）。
        now: 当前时间（UTC naive）。

    Returns:
        tuple[datetime, datetime]: （起始, 结束）。

    Raises:
        LogTimeRangeExceededError: 结束早于开始，或跨度超过 `max_query_days`（90203）。
    """
    start = to_naive(occurred_from)
    end = to_naive(occurred_to)
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
