"""测试公共基座：回滚事务夹具（Kiwi 2317）。

覆盖：用例内写 / 提交对同会话可见；独立连接看不到未提交数据；用例结束后整体撤销；
写会话（`write_session`，13_08）进入即取门、不预开事务、退出不提交。

注：探针表在夹具外先建好（SQLite 的 DDL 会隐式提交外层事务，不能用 CREATE TABLE 验证回滚）。
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from bms_core.testing import rollback_session
from bms_core.testing import transaction as transaction_module
from bms_core.testing.transaction import write_session

pytestmark = pytest.mark.own_db("测试基座自测：回滚事务夹具本身（savepoint / 独立连接可见性 / 显式 BEGIN）需真实库")

_TABLE = "_rb_probe"
"""探针表名（夹具外建表，用例只做 DML）。"""


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
async def test_rollback_session_commit_is_savepoint_only(platform_db_url: str) -> None:
    """提交只提交 savepoint：同会话可见，独立连接看不到未提交的行。"""
    engine = await _ensure_probe_table(platform_db_url)
    try:
        async with rollback_session(engine) as session:
            await session.execute(text(f"INSERT INTO {_TABLE} VALUES (1)"))
            await session.commit()

            rows = (await session.execute(text(f"SELECT COUNT(*) FROM {_TABLE}"))).scalar_one()
            assert rows == 1

            # 另起引擎（独立连接池）读取：未提交数据不可见
            other_engine = create_async_engine(platform_db_url)
            try:
                async with other_engine.connect() as other:
                    visible = (await other.execute(text(f"SELECT COUNT(*) FROM {_TABLE}"))).scalar_one()
                    assert visible == 0
            finally:
                await other_engine.dispose()
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2317)
async def test_rollback_session_discards_everything(platform_db_url: str) -> None:
    """整体回滚：上一个用例写入的行不存在（用例间零残留）。"""
    engine = await _ensure_probe_table(platform_db_url)
    try:
        async with engine.connect() as connection:
            rows = (await connection.execute(text(f"SELECT COUNT(*) FROM {_TABLE}"))).scalar_one()
            assert rows == 0
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2533)
async def test_write_session_keeps_writes_uncommitted(platform_db_url: str) -> None:
    """写会话不提交：会话内可见，独立连接与退出后都读不到（数据不落库、可反复跑）。"""
    engine = await _ensure_probe_table(platform_db_url)
    try:
        async with write_session(engine) as session:
            await session.execute(text(f"INSERT INTO {_TABLE} VALUES (7)"))
            await session.flush()
            rows = (await session.execute(text(f"SELECT COUNT(*) FROM {_TABLE}"))).scalar_one()
            assert rows == 1

            other_engine = create_async_engine(platform_db_url)
            try:
                async with other_engine.connect() as other:
                    visible = (await other.execute(text(f"SELECT COUNT(*) FROM {_TABLE}"))).scalar_one()
                    assert visible == 0
            finally:
                await other_engine.dispose()

        async with engine.connect() as connection:
            remaining = (await connection.execute(text(f"SELECT COUNT(*) FROM {_TABLE}"))).scalar_one()
            assert remaining == 0
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
