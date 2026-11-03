"""审计分片启动预热与预创建（06_01）。

- `ensure_audit_shards`：确保「当月 + 未来 `months_ahead` 月」两类日志分片存在（幂等）。
- `bootstrap_audit_shards`：启动钩子——预热失败只告警、不阻断服务启动（写路径仍会在消费时兜底建表）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast

from fastapi import FastAPI

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.logging import get_logger
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope
from bms_platform.domains.log.repositories.shard import LogShardRepository
from bms_platform.domains.log.schema import LOG_TYPE_LOGIN, LOG_TYPE_OPERATION, month_key, month_shift

__all__ = ["bootstrap_audit_shards", "ensure_audit_shards"]

_LOGGER = get_logger("bms.platform.log")
_LOG_TYPES = (LOG_TYPE_OPERATION, LOG_TYPE_LOGIN)


def _utc_now() -> datetime:
    """当前 UTC naive 时间。"""
    return datetime.now(UTC).replace(tzinfo=None)


async def ensure_audit_shards(
    session: DbSession,
    *,
    months_ahead: int = 1,
    clock: Callable[[], datetime] = _utc_now,
) -> ConcurrentStableList[str]:
    """确保审计分片存在（当月 + 未来 N 月，两类日志）。

    Args:
        session: 平台库会话（事务边界由调用方管理）。
        months_ahead: 提前月数（0 = 仅当月）。
        clock: 当前时钟（测试可注入）。

    Returns:
        ConcurrentStableList[str]: 已确保存在的月份（升序）。
    """
    current = month_key(clock())
    months = ConcurrentStableList(month_shift(current, offset) for offset in range(0, max(0, months_ahead) + 1))
    repo = LogShardRepository(session)
    for month in months:
        for log_type in _LOG_TYPES:
            await repo.ensure_shard(log_type, month)
    return months


async def bootstrap_audit_shards(app: FastAPI) -> None:
    """启动钩子：预热当月 / 次月审计分片（失败只告警）。

    Args:
        app: 应用实例（取引擎注册表 / 会话工厂 / 配置）。
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
            months = await ensure_audit_shards(session, months_ahead=settings.audit_log.precreate_months_ahead)
    except Exception as exc:  # 预热失败不阻断启动；消费时 ensure_shard 兜底
        _LOGGER.warning("audit_shard_bootstrap_failed", error=repr(exc))
        return
    _LOGGER.info("audit_shard_bootstrap", months=list(months))
