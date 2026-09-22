"""BaseService 通用行为与不存在语义测试（Kiwi 12，异步）；keyset 游标分页见 Kiwi 1078。"""

from dataclasses import dataclass

import pytest

from bms_core.core.exceptions import NotFoundError, ParamError
from bms_core.repositories.base_memory_repository import BaseMemoryRepository
from bms_core.schemas.pagination import BaseCursorQuery
from bms_core.services.base_service import BaseService


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


def _service() -> BaseService[Item]:
    return BaseService(ItemRepository())


@pytest.mark.kiwi_id(12)
async def test_create_list_exists_count_delegate() -> None:
    """create/list/exists/count 转发仓储。"""
    service = _service()
    await service.create(name="甲")
    assert [item.name for item in await service.list()] == ["甲"]
    assert await service.exists(1) is True
    assert await service.exists(999) is False
    assert await service.count() == 1


@pytest.mark.kiwi_id(12)
async def test_get_success_and_missing_raises_not_found() -> None:
    """get 命中返回记录；不存在抛 NotFoundError。"""
    service = _service()
    await service.create(name="甲")
    assert (await service.get(1)).name == "甲"
    with pytest.raises(NotFoundError):
        await service.get(999)


@pytest.mark.kiwi_id(12)
async def test_update_success_and_missing_raises_not_found() -> None:
    """update 更新成功；不存在抛 NotFoundError。"""
    service = _service()
    await service.create(name="甲")
    assert (await service.update(1, name="乙")).name == "乙"
    with pytest.raises(NotFoundError):
        await service.update(999, name="丙")


@pytest.mark.kiwi_id(12)
async def test_delete_success_and_missing_raises_not_found() -> None:
    """delete 删除成功；不存在抛 NotFoundError。"""
    service = _service()
    await service.create(name="甲")
    await service.delete(1)
    assert await service.count() == 0
    with pytest.raises(NotFoundError):
        await service.delete(999)


@pytest.mark.kiwi_id(1078)
async def test_cursor_page_keyset_next_cursor() -> None:
    """cursor_page：keyset 逐批取完（`next_cursor` / `has_more`），末页游标为 None；非法游标拒绝。"""
    service = _service()
    for index in range(5):
        await service.create(name=f"n{index}")

    first = await service.cursor_page(BaseCursorQuery(limit=2))
    assert [item.name for item in first.list] == ["n0", "n1"]
    assert first.has_more is True
    assert first.next_cursor is not None

    second = await service.cursor_page(BaseCursorQuery(limit=2, cursor=first.next_cursor))
    assert [item.name for item in second.list] == ["n2", "n3"]

    third = await service.cursor_page(BaseCursorQuery(limit=2, cursor=second.next_cursor))
    assert [item.name for item in third.list] == ["n4"]
    assert third.next_cursor is None
    assert third.has_more is False

    with pytest.raises(ParamError):
        await service.cursor_page(BaseCursorQuery(limit=2, cursor="broken"))


@pytest.mark.kiwi_id(12)
def test_demo_service_inherits_base() -> None:
    """demo 服务继承 BaseService（继承约定生效）。"""
    from bms_platform.services.demo_service import DemoService

    assert issubclass(DemoService, BaseService)
