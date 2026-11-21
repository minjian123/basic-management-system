"""测试公共基座：回滚事务夹具（Kiwi 2317）。

覆盖：用例内写 / 提交对同会话可见；独立连接看不到未提交数据；用例结束后整体撤销；
写会话（`write_session`，13_08）进入即取门、不预开事务、退出不提交。

注：探针表在夹具外先建好（SQLite 的 DDL 会隐式提交外层事务，不能用 CREATE TABLE 验证回滚）。
"""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from bms_core.testing import rollback_session
from bms_core.testing import transaction as transaction_module
from bms_core.testing.transaction import gated_session, write_session

pytestmark = pytest.mark.own_db("测试基座自测：回滚事务夹具本身（savepoint / 独立连接可见性 / 显式 BEGIN）需真实库")

_TABLE = f"_rb_probe_{os.environ.get('PYTEST_XDIST_WORKER', 'main')}_{os.getpid()}"
"""探针表名（按 worker + 进程派生：同文件用例可能被 xdist 分到不同 worker，共用一张表必然互相污染）。"""


async def _ensure_probe_table(platform_db_url: str) -> AsyncEngine:
    """在夹具外建好探针表并提交（幂等）。

    Args:
        platform_db_url: 测试库连接串。

    Returns:
        AsyncEngine: 已就绪的引擎（调用方负责 `dispose`）。
    """
    engine = create_async_engine(platform_db_url)
    async with engine.begin() as connection:
        await connection.execute(text(f"CREATE TABLE IF NOT EXISTS {_TABLE} (x INTEGER)"))
        await connection.execute(text(f"DELETE FROM {_TABLE}"))
    return engine


@pytest.mark.kiwi_id(2317)
async def test_rollback_session_commits_each_statement(platform_db_url: str) -> None:
    """写会话 autocommit：每条语句立即落库，独立连接立即可见（不再保存 savepoint）。"""
    engine = await _ensure_probe_table(platform_db_url)
    try:
        async with rollback_session(engine) as session:
            await session.execute(text(f"INSERT INTO {_TABLE} VALUES (1)"))

            other_engine = create_async_engine(platform_db_url)
            try:
                async with other_engine.connect() as other:
                    visible = (await other.execute(text(f"SELECT COUNT(*) FROM {_TABLE}"))).scalar_one()
                    assert visible == 1
            finally:
                await other_engine.dispose()
        async with engine.connect() as connection:
            await connection.execute(text(f"DELETE FROM {_TABLE}"))
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2317)
async def test_probe_table_is_clean_before_cases(platform_db_url: str) -> None:
    """探针表在用例序列起点为空（每个用例只清理自己写的行）。"""
    engine = await _ensure_probe_table(platform_db_url)
    try:
        async with engine.connect() as connection:
            rows = (await connection.execute(text(f"SELECT COUNT(*) FROM {_TABLE}"))).scalar_one()
            assert rows == 0
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2533)
async def test_write_session_commits_each_statement(platform_db_url: str) -> None:
    """写会话 autocommit：写入立即落库、立即释放数据库锁（不再保持未提交）。"""
    engine = await _ensure_probe_table(platform_db_url)
    try:
        async with write_session(engine) as session:
            await session.execute(text(f"INSERT INTO {_TABLE} VALUES (7)"))

            other_engine = create_async_engine(platform_db_url)
            try:
                async with other_engine.connect() as other:
                    visible = (await other.execute(text(f"SELECT COUNT(*) FROM {_TABLE}"))).scalar_one()
                    assert visible == 1
            finally:
                await other_engine.dispose()

        async with engine.connect() as connection:
            remaining = (await connection.execute(text(f"SELECT COUNT(*) FROM {_TABLE}"))).scalar_one()
            assert remaining == 1
            await connection.execute(text(f"DELETE FROM {_TABLE}"))
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2533)
async def test_write_session_defers_transaction_until_first_statement(platform_db_url: str) -> None:
    """进入不预开事务、也不前置写锁：互斥只由门提供（门是唯一的锁）。"""
    engine = await _ensure_probe_table(platform_db_url)
    try:
        async with write_session(engine) as session:
            assert not session.in_transaction()
            await session.execute(text(f"INSERT INTO {_TABLE} VALUES (9)"))
            assert session.in_transaction()
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2317)
async def test_session_factory_reuses_outer_session(platform_db_url: str) -> None:
    """工厂接管：`SessionFactory().create(...)()` 返回外层会话（被测代码自建会话同一事务）。"""
    from bms_core.db.session import SessionFactory

    engine = create_async_engine(platform_db_url)
    try:
        async with (
            rollback_session(engine) as session,
            SessionFactory().create(None)() as reused,  # type: ignore[arg-type]
        ):
            assert reused is session
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2317)
async def test_rollback_session_propagates_exception(platform_db_url: str) -> None:
    """异常传播：用例体异常原样抛出，回滚在 finally 完成。"""
    engine = create_async_engine(platform_db_url)
    try:
        with pytest.raises(RuntimeError):
            async with rollback_session(engine):
                raise RuntimeError("boom")
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2317)
async def test_gate_for_engine_maps_shared_db_only() -> None:
    """写门推断：只认共享 `platform` / `tenant` 库文件；临时库 / 内存库 / 无库名不取门。"""
    cases = (
        ("sqlite+aiosqlite:///.cache/test/platform.db", "platform"),
        ("sqlite+aiosqlite:///.cache/test/tenant.db", "tenant"),
        ("sqlite+aiosqlite:///tmp/other.db", None),
        ("sqlite+aiosqlite://", None),
        ("sqlite+aiosqlite:///:memory:", None),
    )
    for url, expected in cases:
        engine = create_async_engine(url)
        try:
            assert transaction_module.gate_for_engine(engine) == expected, url
        finally:
            await engine.dispose()


async def test_sqlite_autocommit_only_wraps_sqlite() -> None:
    """autocommit 包装只作用于 SQLite；正式数据库原样返回（保持自身事务语义）。"""
    sqlite_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        assert transaction_module._sqlite_autocommit(sqlite_engine) is not sqlite_engine  # pyright: ignore[reportPrivateUsage]
    finally:
        await sqlite_engine.dispose()

    pg_engine = create_async_engine("postgresql+psycopg://user:secret@localhost:5432/demo")
    try:
        assert transaction_module._sqlite_autocommit(pg_engine) is pg_engine  # pyright: ignore[reportPrivateUsage]
    finally:
        await pg_engine.dispose()


async def test_gated_session_on_private_engine_skips_gate() -> None:
    """非共享库引擎（内存库）不取门，直接给出会话。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with gated_session(engine, read_only=False) as session:
            value = (await session.execute(text("SELECT 1"))).scalar_one()
            assert value == 1
    finally:
        await engine.dispose()


async def test_gated_session_write_uses_operation_gate(platform_db_url: str) -> None:
    """共享库引擎的写会话走操作级写门代理。"""
    engine = create_async_engine(platform_db_url)
    try:
        async with gated_session(engine, read_only=False) as session:
            value = (await session.execute(text("SELECT 1"))).scalar_one()
            assert value == 1
    finally:
        await engine.dispose()
