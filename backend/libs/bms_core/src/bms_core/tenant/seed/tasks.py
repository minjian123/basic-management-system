"""内置定时任务种子：`sys_task` 四条（幂等 upsert，按 `code` 对账）。

口径（《详细设计 · 任务调度》§4.6）：

- 四条内置任务随**租户开通**入库（`deploy/registry/platform.toml` 的 `[[seeds]]` 段），
  存量租户由统一编排 `python -m ops.seed_platform` 回填；
- 幂等：按 `code` 命中即校正（名称 / 执行体 / cron / 备注），不重复插入、不改启停状态；
- `next_run_at` 留空：由 beat 下一轮按 cron 计算，避免种子写入时假设调度时钟。
"""

from __future__ import annotations

from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.db.session import DbSession
from bms_core.models.platform.task import TASK_STATUS_ENABLED, SysTask
from bms_core.tasks.builtin import BUILTIN_TASK_SPECS

__all__ = ["seed_tasks_entry"]


async def seed_tasks_entry(session: DbSession, args: ConcurrentStableDict[str, object]) -> None:
    """写入 / 校正内置任务定义（幂等）。

    Args:
        session: 目标租户库会话（编排层负责事务）。
        args: 种子参数（保留位；当前未使用）。
    """
    _ = args
    for spec in BUILTIN_TASK_SPECS:
        existing = (await session.execute(select(SysTask).where(SysTask.code == spec.code))).scalars().first()
        if existing is None:
            session.add(
                SysTask(
                    code=spec.code,
                    name=spec.name,
                    handler=spec.handler,
                    cron=spec.cron,
                    status=TASK_STATUS_ENABLED,
                    enabled=True,
                    remark=spec.summary,
                    next_run_at=None,
                )
            )
            continue
        existing.name = spec.name
        existing.handler = spec.handler
        existing.cron = spec.cron
        existing.remark = spec.summary
    await session.flush()
