"""BaseTransactionalService 事务边界测试（Kiwi 12，异步）。"""

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
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


@asynccontextmanager
async def _noop() -> AsyncGenerator[None]:
    """无副作用异步事务上下文。"""
    yield


class CountingUnitOfWork(NullUnitOfWork):
    """记录事务开启次数的工作单元（测试用）。"""

    def __init__(self) -> None:
        self.begins = 0

    def begin(self) -> AbstractAsyncContextManager[object]:
        """记录一次开启并返回无副作用上下文。"""
        self.begins += 1
        return _noop()


@pytest.mark.kiwi_id(12)
async def test_transaction_wraps_writes_only() -> None:
    """事务：写操作进入工作单元；只读不进入；缺失分支在事务内抛错。"""
    uow = CountingUnitOfWork()
    service = BaseTransactionalService(ItemRepository(), uow)

    await service.create(name="甲")
    assert uow.begins == 1

    await service.list()
    await service.get(1)
    await service.exists(1)
    await service.count()
    assert uow.begins == 1

    assert (await service.update(1, name="乙")).name == "乙"
    assert uow.begins == 2
    await service.delete(1)
    assert uow.begins == 3

    with pytest.raises(NotFoundError):
        await service.update(999, name="丙")
    with pytest.raises(NotFoundError):
        await service.delete(999)
    assert uow.begins == 5


@pytest.mark.kiwi_id(12)
def test_inheritance_chain() -> None:
    """继承链：BaseTransactionalService → BaseService → BaseObject。"""
    assert issubclass(BaseTransactionalService, BaseService)
    assert issubclass(BaseTransactionalService, BaseObject)

    from app.services.demo_service import DemoService

    assert issubclass(DemoService, BaseTransactionalService)


@pytest.mark.kiwi_id(12)
async def test_default_unit_of_work_is_noop() -> None:
    """未注入工作单元时默认空实现，写操作正常。"""
    service = BaseTransactionalService(ItemRepository())
    assert (await service.create(name="甲")).name == "甲"
