"""任务存储护栏：到期候选筛选 / 条件 UPDATE 抢占 / 记录写入 / 超时回收 / 停用。

事务口径：每个数据库交互都包在 `async with session.begin()` 内（会话自动开事务，勿嵌套）。
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.models.platform.task import (
    TASK_RUN_FAILED,
    TASK_RUN_RUNNING,
    TASK_RUN_SUCCESS,
    TASK_STATUS_DISABLED,
    TASK_STATUS_ENABLED,
    SysTask,
    SysTaskLog,
)
from bms_core.tasks.store import (
    TIMEOUT_ERROR,
    claim_task,
    create_run_record,
    disable_task,
    list_due_tasks,
    reclaim_timeout_runs,
)

pytestmark = pytest.mark.kiwi_id(2371)


def _now() -> datetime:
    """固定当前时刻（naive UTC）。

    Returns:
        datetime: 时刻。
    """
    return datetime(2026, 11, 1, 3, 0, 0)


async def _add_task(
    session: AsyncSession,
    *,
    code: str = "task_a",
    cron: str | None = "0 3 * * *",
    status: str = TASK_STATUS_ENABLED,
    next_run_at: datetime | None = None,
    deleted: bool = False,
    args: str | None = None,
) -> int:
    """插入一条任务定义。

    Args:
        session: 会话。
        code: 任务代码。
        cron: 调度表达式（None 表示仅手动）。
        status: 状态。
        next_run_at: 下次到期时间。
        deleted: 是否软删除。
        args: 参数原文。

    Returns:
        int: 任务主键。
    """
    async with session.begin():
        task = SysTask(
            code=code,
            name=code,
            handler=f"bms_core.tasks.builtin:run_{code}",
            cron=cron,
            args=args,
            status=status,
            enabled=status == TASK_STATUS_ENABLED,
            next_run_at=next_run_at,
            deleted_at=_now() if deleted else None,
        )
        session.add(task)
        await session.flush()
        return int(task.id)


async def test_list_due_filters(session: AsyncSession) -> None:
    """候选只含「启用 + 有 cron + 已到期 / 未排期」的任务。"""
    await _add_task(session, code="due_never", next_run_at=None)
    await _add_task(session, code="due_past", next_run_at=_now() - timedelta(minutes=5))
    await _add_task(session, code="future", next_run_at=_now() + timedelta(hours=1))
    await _add_task(session, code="disabled", status=TASK_STATUS_DISABLED)
    await _add_task(session, code="manual_only", cron=None)
    await _add_task(session, code="removed", deleted=True)
    async with session.begin():
        claims = await list_due_tasks(session, now=_now(), limit=10)
    assert {claim.code for claim in claims} == {"due_never", "due_past"}


async def test_list_due_respects_limit(session: AsyncSession) -> None:
    """单次上限生效（tick 时长有界的依据之一）。"""
    await _add_task(session, code="a1")
    await _add_task(session, code="a2")
    await _add_task(session, code="a3")
    async with session.begin():
        claims = await list_due_tasks(session, now=_now(), limit=2)
    assert len(claims) == 2


async def test_list_due_carries_args_and_handler(session: AsyncSession) -> None:
    """候选带出参数原文与执行体路径（入队所需）。"""
    await _add_task(session, code="with_args", args='{"keep_days": 7}')
    async with session.begin():
        claims = await list_due_tasks(session, now=_now(), limit=1)
    assert claims[0].args_json == '{"keep_days": 7}'
    assert claims[0].handler.endswith(":run_with_args")
    assert claims[0].cron == "0 3 * * *"


async def test_claim_advances_and_is_exclusive(session: AsyncSession) -> None:
    """抢占成功推进 next_run_at / last_run_at；同一行再抢失败（数据库 CAS）。"""
    task_id = await _add_task(session, next_run_at=None)
    upcoming = _now() + timedelta(days=1)
    async with session.begin():
        assert await claim_task(session, task_id=task_id, next_run_at=upcoming, now=_now()) is True
    async with session.begin():
        row = (await session.execute(select(SysTask).where(SysTask.id == task_id))).scalar_one()
        assert row.next_run_at == upcoming
        assert row.last_run_at == _now()
        assert row.version is not None
        assert row.version > 1
    async with session.begin():
        assert await claim_task(session, task_id=task_id, next_run_at=upcoming, now=_now()) is False


async def test_claim_rejects_disabled_and_deleted(session: AsyncSession) -> None:
    """停用 / 软删除的任务不可被抢占。"""
    disabled = await _add_task(session, code="off", status=TASK_STATUS_DISABLED)
    deleted = await _add_task(session, code="gone", deleted=True)
    async with session.begin():
        assert await claim_task(session, task_id=disabled, next_run_at=None, now=_now()) is False
        assert await claim_task(session, task_id=deleted, next_run_at=None, now=_now()) is False


async def test_create_run_record_starts_running(session: AsyncSession) -> None:
    """执行记录先落 `running`（先记录再入队的顺序保障）。"""
    task_id = await _add_task(session)
    async with session.begin():
        log_id = await create_run_record(
            session, task_id=task_id, run_id="run-1", trigger_source="manual", started_at=_now()
        )
    async with session.begin():
        row = (await session.execute(select(SysTaskLog).where(SysTaskLog.id == log_id))).scalar_one()
        assert row.status == TASK_RUN_RUNNING
        assert row.run_id == "run-1"
        assert row.trigger_source == "manual"
        assert row.retry_count == 0
        assert row.started_at == _now()


async def test_reclaim_timeout_only_touches_stale_running(session: AsyncSession) -> None:
    """超时回收只改「早于阈值且仍 running」的记录。"""
    task_id = await _add_task(session)
    async with session.begin():
        session.add_all(
            [
                SysTaskLog(
                    task_id=task_id, status=TASK_RUN_RUNNING, started_at=_now() - timedelta(hours=3), run_id="old"
                ),
                SysTaskLog(task_id=task_id, status=TASK_RUN_RUNNING, started_at=_now(), run_id="fresh"),
                SysTaskLog(task_id=task_id, status=TASK_RUN_SUCCESS, started_at=_now() - timedelta(hours=3)),
            ]
        )
    async with session.begin():
        reclaimed = await reclaim_timeout_runs(session, cutoff=_now() - timedelta(seconds=1800), finished_at=_now())
    assert reclaimed == 1
    async with session.begin():
        rows = (await session.execute(select(SysTaskLog))).scalars().all()
    by_run = {row.run_id: row for row in rows if row.run_id is not None}
    assert by_run["old"].status == TASK_RUN_FAILED
    assert by_run["old"].error_msg == TIMEOUT_ERROR
    assert by_run["old"].finished_at == _now()
    assert by_run["fresh"].status == TASK_RUN_RUNNING


async def test_disable_task_clears_schedule(session: AsyncSession) -> None:
    """停用清空 next_run_at 与 enabled，保证不再产生记录。"""
    task_id = await _add_task(session, next_run_at=_now())
    async with session.begin():
        assert await disable_task(session, task_id=task_id, now=_now()) is True
    async with session.begin():
        row = (await session.execute(select(SysTask).where(SysTask.id == task_id))).scalar_one()
        assert row.status == TASK_STATUS_DISABLED
        assert row.enabled is False
        assert row.next_run_at is None
    async with session.begin():
        assert await disable_task(session, task_id=task_id, now=_now()) is False
