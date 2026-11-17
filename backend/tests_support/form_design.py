"""表单定制用例的数据库辅助（共享基座：**唯一允许建引擎的位置**）。

为什么放在 `tests_support`：测试库隔离护栏（`base test-db-isolation`）把「用例自建 SQLite 引擎」
列为违规（单库叠加口径），只放行共享基座模块；本模块即该基座（与 `tests_support/shared_db.py` 同口径）。
用例只调本模块的函数，不直接构造引擎。

**为什么没有「清表」**（2026-11-18 修订）：单库叠加口径下全 worker 共用一份租户库
（`bms_core.testing.shared_db`），**整表 delete 会删掉并行中他人用例正在断言的行**——
这类写法在 `services/identity/tests/auth/conftest.py` 已被明确取消（见
`auth/session_helpers.py` 模块说明）。本域的隔离靠**用例命名空间**（`ns` → 唯一 `form_code`）：
四表查询一律按 `form_code` 过滤、探针表名由 `form_code` 派生，故无需清场即可互不干扰。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, cast

from sqlalchemy import Table, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.base import Base

__all__ = [
    "create_probe_table",
    "drop_probe_table",
    "ensure_models",
    "list_columns",
    "run_statement",
    "tenant_session",
]


async def ensure_models(url: str, models: ConcurrentStableList[Any]) -> None:
    """确保给定模型对应表存在（缺则建；**不清空**——单库叠加下清表会删他人数据）。

    Args:
        url: 数据库连接串。
        models: ORM 模型清单（插入序）。
    """
    engine = create_async_engine(url)
    try:
        tables = [cast("Table", model.__table__) for model in models]
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables, checkfirst=True))
    finally:
        await engine.dispose()


async def create_probe_table(url: str, name: str, *, columns: str = "id INTEGER PRIMARY KEY, code VARCHAR(64)") -> None:
    """重建探针表（先删后建，确保结构与列集合从干净状态开始）。

    探针表名由调用方按用例命名空间派生（`biz_{form_code}`），故「先删」只影响本用例自己的表。

    Args:
        url: 数据库连接串。
        name: 表名（调用方保证为白名单形态）。
        columns: 列定义文本。
    """
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f"DROP TABLE IF EXISTS {name}"))
            await connection.execute(text(f"CREATE TABLE {name} ({columns})"))
    finally:
        await engine.dispose()


async def drop_probe_table(url: str, name: str) -> None:
    """删除探针表（不存在不报错）。

    Args:
        url: 数据库连接串。
        name: 表名。
    """
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
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
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            rows = await connection.run_sync(lambda conn: inspect(conn).get_columns(table))
        return ConcurrentStableList(str(item["name"]).lower() for item in rows)
    finally:
        await engine.dispose()


async def run_statement(url: str, statement: str) -> None:
    """执行一条 DDL / DML 语句（用例构造前置条件用）。

    Args:
        url: 数据库连接串。
        statement: SQL 文本（调用方保证已参数化 / 来自白名单）。
    """
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
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
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()
