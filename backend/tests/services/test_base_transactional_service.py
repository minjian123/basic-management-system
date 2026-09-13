"""BaseTransactionalService 事务边界测试（Kiwi 12）。"""

from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass

import pytest

from app.core.base import BaseObject
from app.core.exceptions import NotFoundError
from app.db.unit_of_work import NullUnitOfWork
from app.repositories.base_memory_repository import BaseMemoryRepository
from app.services.base_service import BaseService
from app.services.base_transactional_service import BaseTransactionalService


@dataclass
class Item:
    """测试实体。"""

    id: int
    name: str


class ItemRepository(BaseMemoryRepository[Item]):
    """测试仓储：只实现构造钩子。"""

    def _build(self, item_id: int, values: dict[str, object]) -> Item:
        return Item(id=item_id, name=str(values["name"]))

    def _apply(self, item: Item, values: dict[str, object]) -> Item:
        return Item(id=item.id, name=str(values["name"]))


class CountingUnitOfWork(NullUnitOfWork):
    """记录事务开启次数的工作单元（测试用）。"""

    def __init__(self) -> None:
        self.begins = 0

    def begin(self) -> AbstractContextManager[None]:
        """记录一次开启并返回无副作用上下文。"""
        self.begins += 1
        return nullcontext()


@pytest.mark.kiwi_id(12)
def test_transaction_wraps_writes_only() -> None:
    """事务：写操作进入工作单元；只读不进入；缺失分支在事务内抛错。"""
    uow = CountingUnitOfWork()
    service = BaseTransactionalService(ItemRepository(), uow)

    service.create(name="甲")
    assert uow.begins == 1

    service.list()
    service.get(1)
    service.exists(1)
    service.count()
    assert uow.begins == 1

    assert service.update(1, name="乙").name == "乙"
    assert uow.begins == 2
    service.delete(1)
    assert uow.begins == 3

    with pytest.raises(NotFoundError):
        service.update(999, name="丙")
    with pytest.raises(NotFoundError):
        service.delete(999)
    assert uow.begins == 5


@pytest.mark.kiwi_id(12)
def test_inheritance_chain() -> None:
    """继承链：BaseTransactionalService → BaseService → BaseObject。"""
    assert issubclass(BaseTransactionalService, BaseService)
    assert issubclass(BaseTransactionalService, BaseObject)

    from app.services.demo_service import DemoService

    assert issubclass(DemoService, BaseTransactionalService)


@pytest.mark.kiwi_id(12)
def test_default_unit_of_work_is_noop() -> None:
    """未注入工作单元时默认空实现，写操作正常。"""
    service = BaseTransactionalService(ItemRepository())
    assert service.create(name="甲").name == "甲"
