"""工作单元实现测试（Kiwi 12 / 25 / 984）：空实现与数据库实现。"""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.base import BaseObject
from bms_core.db.null import NullUnitOfWork
from bms_core.db.unit_of_work import DbUnitOfWork, UnitOfWork


@pytest.mark.kiwi_id(12)
def test_unit_of_work_inherits_base_object() -> None:
    """工作单元纳入 L0 继承体系。"""
    assert issubclass(UnitOfWork, BaseObject)
    assert issubclass(NullUnitOfWork, BaseObject)


@pytest.mark.kiwi_id(12)
async def test_null_unit_of_work_is_noop() -> None:
    """空工作单元：begin 无副作用，commit/rollback 无操作，session 为 None。"""
    uow = NullUnitOfWork()
    assert isinstance(uow, UnitOfWork)
    async with uow.begin():
        pass
    assert await uow.commit() is None
    assert await uow.rollback() is None
    assert uow.session is None


@pytest.mark.kiwi_id(36)
async def test_db_unit_of_work_uses_session() -> None:
    """数据库工作单元：会话可解析、事务边界可开关。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        uow = DbUnitOfWork(session)
        assert isinstance(uow.session, AsyncSession)
        async with uow.begin():
            assert (await session.execute(text("SELECT 1"))).scalar() == 1
        await uow.commit()
        await uow.rollback()
    await engine.dispose()


@pytest.mark.kiwi_id(984)
async def test_db_unit_of_work_commit_and_rollback(tmp_path: Path) -> None:
    """数据库工作单元事务：`begin` 上下文提交生效，`rollback` 回滚未提交写入。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'uow.db'}")
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, value TEXT)"))
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        uow = DbUnitOfWork(session)
        async with uow.begin():
            await session.execute(text("INSERT INTO t (value) VALUES ('committed')"))
    async with factory() as session:
        uow = DbUnitOfWork(session)
        await session.execute(text("INSERT INTO t (value) VALUES ('rolled-back')"))
        await uow.rollback()

    async with factory() as session:
        rows = (await session.execute(text("SELECT value FROM t"))).scalars().all()
    assert list(rows) == ["committed"]
    await engine.dispose()
