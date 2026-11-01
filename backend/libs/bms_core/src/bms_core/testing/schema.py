"""测试建表工具：并发安全的幂等建表（单库化后多 worker 共用同一份库）。"""

from __future__ import annotations

from collections.abc import Iterable
from functools import partial

from sqlalchemy import Table
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.base import Base

_ALREADY_EXISTS = "already exists"


async def ensure_tables(
    engine: AsyncEngine,
    tables: Iterable[Table] | None = None,
) -> None:
    """幂等建表：表已存在视为成功（并发 worker 同时建表不再撞 `table already exists`）。

    单库化（`04-6-2`）后全 worker 共用一份共享库，用例侧 `create_all(checkfirst=True)` 在并发下
    仍可能「都判不存在 → 都 CREATE → 一方报已存在」；本函数**逐表**建表并吞掉该错误
    （逐表独立事务，避免整体回滚把已建成的表一并撤掉）。

    Args:
        engine: 目标库引擎。
        tables: 需要建的表（任一可迭代）；None 表示 `Base.metadata` 全量并集（按依赖序）。
    """
    targets: ConcurrentStableList[Table] = ConcurrentStableList(
        tables if tables is not None else Base.metadata.sorted_tables
    )
    for raw in targets:
        table: Table = raw
        try:
            async with engine.begin() as connection:
                await connection.run_sync(partial(table.create, checkfirst=True))
        except OperationalError as exc:
            if _ALREADY_EXISTS not in str(exc.orig):
                raise
