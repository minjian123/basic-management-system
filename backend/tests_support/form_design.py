"""表单定制用例的数据库辅助（共享基座：**唯一允许建引擎的位置**）。

为什么放在 `tests_support`：测试库隔离护栏（`base test-db-isolation`）把「用例自建 SQLite 引擎」
列为违规（单库叠加口径），只放行共享基座模块；本模块即该基座（与 `tests_support/shared_db.py` 同口径）。
用例只调本模块的函数，不直接构造引擎。

**为什么没有「清表」**（2026-11-18 修订）：单库叠加口径下全 worker 共用一份租户库
（`bms_core.testing.shared_db`），**整表 delete 会删掉并行中他人用例正在断言的行**——
这类写法在 `services/identity/tests/auth/conftest.py` 已被明确取消（见
`auth/session_helpers.py` 模块说明）。本域的隔离靠**用例命名空间**（`ns` → 唯一 `form_code`）：
四表查询一律按 `form_code` 过滤、探针表名由 `form_code` 派生，故无需清场即可互不干扰。

**运行期改结构只允许在独占临时库**（2026-11-20 修订，13_08 T7）：`create_probe_table` /
`drop_probe_table` / `run_statement` 一律先判目标库——共享平台库 / 租户库（门名 `platform` /
`tenant`）直接报错。理由：结构只有「数据初始化」一次机会，共享库上改结构会与并行 worker 的
断言互相破坏；需要造表 / 造视图的用例改用 `isolated_tenant` 独占库夹具。
"""

from __future__ import annotations

import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, cast

from sqlalchemy import Table, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.models.base import Base
from bms_core.testing.transaction import gate_for_database
from tests_support.shared_access import shared_engine, shared_session, shared_window

__all__ = [
    "create_probe_table",
    "drop_probe_table",
    "ensure_models",
    "list_columns",
    "run_statement",
    "tenant_session",
]


_ENSURED_URLS: ConcurrentStableSet[str] = ConcurrentStableSet()
"""已建过表的连接串（进程级）：13_08 T7 起每进程只建一次。"""

_ENSURE_LOCK = threading.Lock()
"""占位互斥：并发首次调用时只让一个协程去建表（锁内不含 await）。"""

_DDL_SCOPE_HINT = (
    "运行期改表结构只允许在独占临时库上执行（用例请求 `isolated_tenant` 夹具）；"
    "共享平台库 / 租户库的结构只能由数据初始化建好（ops.init_schema / ops.build_ext_columns）。"
)


def _assert_own_db(url: str, action: str) -> None:
    """断言目标库不是共享平台 / 租户库（结构类操作的前置守卫）。

    Args:
        url: 目标库连接串。
        action: 操作名（用于报错定位）。

    Raises:
        RuntimeError: 目标是共享平台库 / 租户库（那里只允许数据初始化建结构）。
    """
    gate = gate_for_database(make_url(url).database)
    if gate is not None:
        raise RuntimeError(f"{action} 拒绝在共享库（门 {gate}）上执行：{_DDL_SCOPE_HINT}")


async def ensure_models(url: str, models: ConcurrentStableList[Any]) -> None:
    """确保给定模型对应表存在（缺则建；**不清空**——单库叠加下清表会删他人数据）。

    13_08 T7：**每个进程只做一次**。原实现每个用例都跑 `create_all`，4 路并行时每次都要
    争 SQLite schema 锁，实测卡满 `busy_timeout`（30 秒），并把写门占成长临界区。建表幂等，
    共享库在会话开始建好后不再变化，故按连接串记录；失败时撤销占位，下次调用重试。

    Args:
        url: 数据库连接串。
        models: ORM 模型清单（插入序）。
    """
    with _ENSURE_LOCK:
        if url in _ENSURED_URLS:
            return
        _ENSURED_URLS.add(url)
    try:
        engine = shared_engine(url)
        try:
            tables = [cast("Table", model.__table__) for model in models]
            async with shared_window(engine), engine.begin() as connection:
                await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables, checkfirst=True))
        finally:
            await engine.dispose()
    except BaseException:
        _ENSURED_URLS.discard(url)
        raise


async def create_probe_table(url: str, name: str, *, columns: str = "id INTEGER PRIMARY KEY, code VARCHAR(64)") -> None:
    """重建探针表（先删后建，确保结构与列集合从干净状态开始）。

    探针表名由调用方按用例命名空间派生（`biz_{form_code}`），故「先删」只影响本用例自己的表。

    Args:
        url: 数据库连接串。
        name: 表名（调用方保证为白名单形态）。
        columns: 列定义文本。

    Raises:
        RuntimeError: 目标是共享平台库 / 租户库（结构只允许由数据初始化建好）。
    """
    _assert_own_db(url, "create_probe_table")
    engine = shared_engine(url)
    try:
        async with shared_window(engine), engine.begin() as connection:
            await connection.execute(text(f"DROP TABLE IF EXISTS {name}"))
            await connection.execute(text(f"CREATE TABLE {name} ({columns})"))
    finally:
        await engine.dispose()


async def drop_probe_table(url: str, name: str) -> None:
    """删除探针表（不存在不报错）。

    Args:
        url: 数据库连接串。
        name: 表名。

    Raises:
        RuntimeError: 目标是共享平台库 / 租户库（结构只允许由数据初始化建好）。
    """
    _assert_own_db(url, "drop_probe_table")
    engine = shared_engine(url)
    try:
        async with shared_window(engine), engine.begin() as connection:
            await connection.execute(text(f"DROP TABLE IF EXISTS {name}"))
    finally:
        await engine.dispose()


async def list_columns(url: str, table: str) -> ConcurrentStableList[str]:
    """读表现有列名（小写）。

    Args:
        url: 数据库连接串。
        table: 表名。

    Returns:
        ConcurrentStableList[str]: 列名（插入序）。
    """
    engine = shared_engine(url)
    try:
        async with shared_window(engine), engine.begin() as connection:
            rows = await connection.run_sync(lambda conn: inspect(conn).get_columns(table))
        return ConcurrentStableList(str(item["name"]).lower() for item in rows)
    finally:
        await engine.dispose()


async def run_statement(url: str, statement: str) -> None:
    """执行一条 DDL / DML 语句（用例构造前置条件用）。

    Args:
        url: 数据库连接串。
        statement: SQL 文本（调用方保证已参数化 / 来自白名单）。

    Raises:
        RuntimeError: 目标是共享平台库 / 租户库（结构只允许由数据初始化建好）。
    """
    _assert_own_db(url, "run_statement")
    engine = shared_engine(url)
    try:
        async with shared_window(engine), engine.begin() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


@asynccontextmanager
async def tenant_session(url: str) -> AsyncGenerator[AsyncSession]:
    """取一条共享库会话（用例直调域实现时用；用完即关，不清理数据）。

    只提供会话管道，不含任何业务逻辑；隔离仍靠用例命名空间（`form_code` 唯一）。

    Args:
        url: 数据库连接串（共享测试租户库）。

    Yields:
        AsyncSession: 会话（调用方负责 commit）。
    """
    async with shared_session(url, read_only=False) as session:
        yield session
