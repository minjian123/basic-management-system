"""`SyncSession` 绑定既有连接的**保存点语义**用例（强一致专项 05_07 / Kiwi 2271）。

背景：XA 分支执行时业务写必须落在**已开启的两阶段分支事务**内。若会话以默认模式绑定该连接，
服务层的 `UnitOfWork.begin()` 会抛「A transaction is already begun on this Session」，
且其 `commit()` 会连带结束外层分支使其无法 `PREPARE`。

故 `SyncSession(engine, bind=connection)` 采用 `join_transaction_mode="create_savepoint"`：
会话内 `begin / commit` 收敛为 **SAVEPOINT**，外层两阶段事务保持打开、仍可 `prepare`。
"""

import asyncio

import pytest
from sqlalchemy import create_engine, text

from bms_core.db.sync import SyncSession


@pytest.mark.kiwi_id(2271)
async def test_bound_sync_session_uses_savepoint_and_keeps_outer_txn() -> None:
    """绑定连接时：会话内 `begin` 不冲突（SAVEPOINT）、`commit` 不结束外层事务、写入对外层可见。"""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    try:
        with engine.connect() as connection:
            outer = connection.begin()
            session = SyncSession(engine, bind=connection)

            # 与生产同一顺序：先开事务（此处收敛为 SAVEPOINT）再写
            async with session.begin():
                await session.execute(text("CREATE TABLE probe (id INTEGER)"))
                await session.execute(text("INSERT INTO probe (id) VALUES (1)"))
            await session.close()

            # 外层事务仍在（会话内的 begin/commit 只作用于 SAVEPOINT，未连带提交外层）
            assert connection.in_transaction() is True
            # 写入在**同一连接的外层事务**内可见（未被保存点回滚、也未另开事务）
            count = await asyncio.to_thread(connection.execute, text("SELECT COUNT(*) FROM probe"))
            assert count.scalar_one() == 1

            outer.commit()
    finally:
        engine.dispose()


@pytest.mark.kiwi_id(2271)
async def test_bound_sync_session_rollback_keeps_outer_txn_open() -> None:
    """绑定连接时：会话内回滚（SAVEPOINT 回滚）不结束外层事务，外层仍可继续使用并提交。"""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    try:
        with engine.connect() as connection:
            outer = connection.begin()
            session = SyncSession(engine, bind=connection)

            await session.execute(text("CREATE TABLE probe (id INTEGER)"))
            await session.rollback()
            await session.close()

            assert connection.in_transaction() is True
            outer.commit()
    finally:
        engine.dispose()
