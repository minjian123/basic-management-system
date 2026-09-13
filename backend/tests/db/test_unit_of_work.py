"""工作单元实现测试（Kiwi 12 / 25）：空实现与数据库实现。"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.base import BaseObject
from app.db.unit_of_work import DbUnitOfWork, NullUnitOfWork, UnitOfWork


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


@pytest.mark.kiwi_id(25)
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
