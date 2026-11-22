"""测试建表工具：并发安全的幂等建表（单库化后多 worker 共用同一份库）。"""

from __future__ import annotations

from collections.abc import Iterable
from functools import partial

from sqlalchemy import Table
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db.gate import GATE_CRITICAL_WAIT
from bms_core.models.base import Base
from bms_core.testing.gates import gate_scope
from bms_core.testing.transaction import gate_for_engine

_ALREADY_EXISTS = "already exists"


async def ensure_tables(
    engine: AsyncEngine,
    tables: Iterable[Table] | None = None,
) -> None:
    """幂等建表：表已存在视为成功（并发 worker 同时建表不再撞 `table already exists`）。

    单库化（`04-6-2`）后全 worker 共用一份共享库，用例侧 `create_all(checkfirst=True)` 在并发下
    仍可能「都判不存在 → 都 CREATE → 一方报已存在」；本函数**逐表**建表并吞掉该错误
    （逐表独立事务，避免整体回滚把已建成的表一并撤掉）。

    **建表是数据库写**：目标引擎属于共享库时先取写门（与数据读写同一条排队路径）；临时库
    （`gate_for_engine` 返回 None，如 `own_db` 用例的独占库）不取门——它与其它 worker 无共享状态。

    Args:
        engine: 目标库引擎。
        tables: 需要建的表（任一可迭代）；None 表示 `Base.metadata` 全量并集（按依赖序）。
    """
    targets: ConcurrentStableList[Table] = ConcurrentStableList(
        tables if tables is not None else Base.metadata.sorted_tables
    )
    gate_name = gate_for_engine(engine)
    for raw in targets:
        table: Table = raw
        try:
            if gate_name is not None:
                async with (
                    gate_scope(gate_name, read_only=False, wait=GATE_CRITICAL_WAIT),
                    engine.begin() as connection,
                ):
                    await connection.run_sync(partial(table.create, checkfirst=True))
                continue
            async with engine.begin() as connection:
                await connection.run_sync(partial(table.create, checkfirst=True))
        except OperationalError as exc:
            if _ALREADY_EXISTS not in str(exc.orig):
                raise
