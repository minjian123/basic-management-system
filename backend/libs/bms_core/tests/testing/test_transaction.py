"""测试公共基座：回滚事务夹具（Kiwi 2317）。

覆盖：用例内写 / 提交对同会话可见；独立连接看不到未提交数据；用例结束后整体撤销。

注：探针表在夹具外先建好（SQLite 的 DDL 会隐式提交外层事务，不能用 CREATE TABLE 验证回滚）。
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from bms_core.testing import rollback_session
from bms_core.testing import transaction as transaction_module

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


@pytest.mark.kiwi_id(2317)
def test_needs_explicit_begin_by_dialect() -> None:
    """方言判定：只有 SQLite 需要显式 BEGIN。"""
    assert transaction_module.needs_explicit_begin("sqlite")
    assert not transaction_module.needs_explicit_begin("postgresql")


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
async def test_rollback_session_without_explicit_begin(platform_db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """非 SQLite 方言：不执行显式 BEGIN（三库 / PG / MySQL 路径不受影响）。"""

    def _no_begin(name: str) -> bool:
        """固定返回 False（模拟非 SQLite 方言）。

        Args:
            name: 方言名（忽略）。

        Returns:
            bool: 固定 False。
        """
        return False

    monkeypatch.setattr(transaction_module, "needs_explicit_begin", _no_begin)
    engine = create_async_engine(platform_db_url)
    try:
        async with rollback_session(engine) as session:
            assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
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
