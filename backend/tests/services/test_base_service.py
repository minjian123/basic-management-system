"""BaseService 通用行为与不存在语义测试（Kiwi 12）。"""

from contextlib import AbstractContextManager
from dataclasses import dataclass

import pytest

from app.core.exceptions import NotFoundError
from app.repositories.base_repository import BaseRepository
from app.services.base_service import BaseService


@dataclass
class Item:
    """测试实体。"""

    id: int
    name: str


class ItemRepository(BaseRepository[Item]):
    """测试仓储：只实现构造钩子。"""

    def _build(self, item_id: int, values: dict[str, object]) -> Item:
        return Item(id=item_id, name=str(values["name"]))

    def _apply(self, item: Item, values: dict[str, object]) -> Item:
        return Item(id=item.id, name=str(values["name"]))


def _service() -> BaseService[Item]:
    return BaseService(ItemRepository())


class SpyService(BaseService[Item]):
    """测试服务：记录事务钩子进入次数。"""

    def __init__(self, repository: ItemRepository) -> None:
        super().__init__(repository)
        self.transactions = 0

    def _transaction(self) -> AbstractContextManager[None]:
        """覆写事务钩子以计数（其余行为不变）。"""
        self.transactions += 1
        return super()._transaction()


@pytest.mark.kiwi_id(12)
def test_create_list_exists_count_delegate() -> None:
    """create/list/exists/count 转发仓储。"""
    service = _service()
    service.create(name="甲")
    assert [item.name for item in service.list()] == ["甲"]
    assert service.exists(1) is True
    assert service.exists(999) is False
    assert service.count() == 1


@pytest.mark.kiwi_id(12)
def test_get_success_and_missing_raises_not_found() -> None:
    """get 命中返回记录；不存在抛 NotFoundError。"""
    service = _service()
    service.create(name="甲")
    assert service.get(1).name == "甲"
    with pytest.raises(NotFoundError):
        service.get(999)


@pytest.mark.kiwi_id(12)
def test_update_success_and_missing_raises_not_found() -> None:
    """update 更新成功；不存在抛 NotFoundError。"""
    service = _service()
    service.create(name="甲")
    assert service.update(1, name="乙").name == "乙"
    with pytest.raises(NotFoundError):
        service.update(999, name="丙")


@pytest.mark.kiwi_id(12)
def test_delete_success_and_missing_raises_not_found() -> None:
    """delete 删除成功；不存在抛 NotFoundError。"""
    service = _service()
    service.create(name="甲")
    service.delete(1)
    assert service.count() == 0
    with pytest.raises(NotFoundError):
        service.delete(999)


@pytest.mark.kiwi_id(12)
def test_demo_service_inherits_base() -> None:
    """demo 服务继承 BaseService（继承约定生效）。"""
    from app.services.demo_service import DemoService

    assert issubclass(DemoService, BaseService)


@pytest.mark.kiwi_id(12)
def test_transaction_hook_wraps_writes_only() -> None:
    """事务钩子：写操作进入事务；只读不进入；缺失分支同样在事务内抛错。"""
    service = SpyService(ItemRepository())
    service.create(name="甲")
    assert service.transactions == 1

    service.list()
    service.get(1)
    service.exists(1)
    service.count()
    assert service.transactions == 1

    assert service.update(1, name="乙").name == "乙"
    assert service.transactions == 2
    service.delete(1)
    assert service.transactions == 3

    with pytest.raises(NotFoundError):
        service.update(999, name="丙")
    with pytest.raises(NotFoundError):
        service.delete(999)
    assert service.transactions == 5
