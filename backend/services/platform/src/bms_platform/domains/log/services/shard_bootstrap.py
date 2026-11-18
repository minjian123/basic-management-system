"""审计分片启动预热与预创建（06_01）。

- `ensure_audit_shards`：确保「当月 + 未来 `months_ahead` 月」两类日志分片存在（幂等）。
- `bootstrap_audit_shards`：启动钩子——预热失败即拒启（任一分片建不出来，审计写路径的兜底也建不出来）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast

from fastapi import FastAPI

from bms_core.audit.observability import record_shard_readiness
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import CatalogError
from bms_core.core.logging import get_logger
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope
from bms_core.metrics.base import BaseMetrics
from bms_platform.domains.log.repositories.shard import LogShardRepository
from bms_platform.domains.log.schema import LOGIC_TABLES, month_key, month_shift

__all__ = ["bootstrap_audit_shards", "ensure_audit_shards"]

_LOGGER = get_logger("bms.platform.log")
_LOG_TYPES = tuple(LOGIC_TABLES)
"""预创建的日志类型（三类：操作 / 登录 / 字段级变更；06_02 遗留由 14_01 补齐）。"""


def _utc_now() -> datetime:
    """当前 UTC naive 时间。"""
    return datetime.now(UTC).replace(tzinfo=None)


async def ensure_audit_shards(
    session: DbSession,
    *,
    months_ahead: int = 1,
    clock: Callable[[], datetime] = _utc_now,
    metrics: BaseMetrics | None = None,
) -> ConcurrentStableList[str]:
    """确保审计分片存在（当月 + 未来 N 月，三类日志），并记录次月就绪信号。

    Args:
        session: 平台库会话（事务边界由调用方管理）。
        months_ahead: 提前月数（0 = 仅当月）。
        clock: 当前时钟（测试可注入）。
        metrics: 指标器（可选；记录 `bms_audit_shard_next_month_ready`）。

    Returns:
        ConcurrentStableList[str]: 已确保存在的月份（升序）。
    """
    current = month_key(clock())
    months = ConcurrentStableList(month_shift(current, offset) for offset in range(0, max(0, months_ahead) + 1))
    repo = LogShardRepository(session)
    for month in months:
        for log_type in _LOG_TYPES:
            await repo.ensure_shard(log_type, month)
    next_month = month_shift(current, 1)
    for log_type in _LOG_TYPES:
        ready = next_month in set(await repo.months(log_type))
        await record_shard_readiness(metrics, log_type=log_type, ready=ready)
    return months


async def bootstrap_audit_shards(app: FastAPI) -> None:
    """启动钩子：预热当月 / 次月审计分片（失败即拒启）。

    Args:
        app: 应用实例（取引擎注册表 / 会话工厂 / 配置）。

    Raises:
        CatalogError: 分片建表失败（库未就绪 / DDL 失败）。
    """
    settings = app.state.settings
    if not settings.audit_log.enabled:
        return
    registry = cast("EngineRegistry", app.state.engine_registry)
    factory = app.state.session_factory
    try:
        async with (
            session_scope(registry, db_key=PLATFORM_DB_KEY, factory=factory) as session,
            session.begin(),
        ):
            months = await ensure_audit_shards(
                session,
                months_ahead=settings.audit_log.precreate_months_ahead,
                metrics=cast("BaseMetrics | None", getattr(app.state, "metrics", None)),
            )
    except Exception as exc:
        _LOGGER.critical("audit_shard_bootstrap_failed", error=repr(exc))
        raise CatalogError(f"审计分片预热失败（{type(exc).__name__}: {exc}）") from exc
    _LOGGER.info("audit_shard_bootstrap", months=list(months))
