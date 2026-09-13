"""工作单元占位实现测试（Kiwi 12）。"""

import pytest

from app.core.base import BaseObject
from app.db.unit_of_work import NullUnitOfWork, UnitOfWork


@pytest.mark.kiwi_id(12)
def test_unit_of_work_inherits_base_object() -> None:
    """工作单元纳入 L0 继承体系。"""
    assert issubclass(UnitOfWork, BaseObject)
    assert issubclass(NullUnitOfWork, BaseObject)


@pytest.mark.kiwi_id(12)
def test_null_unit_of_work_is_noop() -> None:
    """空工作单元：begin 无副作用，commit/rollback 无操作，session 为 None。"""
    uow = NullUnitOfWork()
    assert isinstance(uow, UnitOfWork)
    with uow.begin():
        pass
    assert uow.commit() is None
    assert uow.rollback() is None
    assert uow.session is None
