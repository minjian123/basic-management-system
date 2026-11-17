"""表单定制用例的数据库辅助（共享基座：**唯一允许建引擎的位置**）。

为什么放在 `tests_support`：测试库隔离护栏（`base test-db-isolation`）把「用例自建 SQLite 引擎」
列为违规（单库叠加口径），只放行共享基座模块；本模块即该基座（与 `tests_support/shared_db.py` 同口径）。
用例只调本模块的函数，不直接构造引擎。
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import Table, delete, inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.base import Base

__all__ = [
    "create_probe_table",
    "drop_probe_table",
    "list_columns",
    "purge_models",
    "run_statement",
]


async def purge_models(url: str, models: ConcurrentStableList[Any]) -> None:
    """建表（缺则建）并清空给定模型对应表。

    Args:
        url: 数据库连接串。
        models: ORM 模型清单（插入序）。
    """
    engine = create_async_engine(url)
    try:
        tables = [cast("Table", model.__table__) for model in models]
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables))
            for table in tables:
                await connection.execute(delete(table))
    finally:
        await engine.dispose()


async def create_probe_table(url: str, name: str, *, columns: str = "id INTEGER PRIMARY KEY, code VARCHAR(64)") -> None:
    """重建探针表（先删后建，确保结构与列集合从干净状态开始）。

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


del async_sessionmaker
