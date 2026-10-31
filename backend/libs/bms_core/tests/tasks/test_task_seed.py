"""内置任务种子护栏：首次写入四条 / 二次幂等 / 命中即校正。"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.models.platform.task import SysTask
from bms_core.tasks.builtin import BUILTIN_TASK_SPECS
from bms_core.tenant.seed.tasks import seed_tasks_entry

pytestmark = pytest.mark.kiwi_id(2371)


async def test_seed_writes_four_tasks(session: AsyncSession) -> None:
    """空库：写入四条内置任务（含 cron / handler / 备注）。"""
    async with session.begin():
        await seed_tasks_entry(session, ConcurrentStableDict())
    async with session.begin():
        rows = (await session.execute(select(SysTask))).scalars().all()
    assert {row.code for row in rows} == {spec.code for spec in BUILTIN_TASK_SPECS}
    assert all(row.cron for row in rows)
    assert all(row.handler.startswith("bms_core.tasks.builtin:") for row in rows)


async def test_seed_is_idempotent_and_corrects(session: AsyncSession) -> None:
    """二次执行不重复插入；对已存在的行按清单校正（名称 / 执行体 / cron）。"""
    async with session.begin():
        await seed_tasks_entry(session, ConcurrentStableDict())
    async with session.begin():
        row = (await session.execute(select(SysTask).where(SysTask.code == "cleanup_orphan_parts"))).scalars().one()
        row.name = "被改坏的名字"
        row.cron = "0 0 1 1 *"
    async with session.begin():
        await seed_tasks_entry(session, ConcurrentStableDict())
    async with session.begin():
        rows = (await session.execute(select(SysTask))).scalars().all()
        fixed = (await session.execute(select(SysTask).where(SysTask.code == "cleanup_orphan_parts"))).scalars().one()
    assert len(rows) == len(BUILTIN_TASK_SPECS)
    assert fixed.name == "孤儿分片清理"
    assert fixed.cron == "0 3 * * *"
