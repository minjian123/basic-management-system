"""仓储基类测试（Kiwi 11）：契约 / 内存基线 / DB 骨架（异步）。"""

from dataclasses import dataclass

import pytest

from app.core.base import BaseObject
from app.repositories.base_db_repository import BaseDbRepository
from app.repositories.base_memory_repository import BaseMemoryRepository
from app.repositories.base_repository import BaseRepository


@dataclass
class Item:
    """测试实体。"""

    id: int
    name: str


class ItemRepository(BaseMemoryRepository[Item]):
    """测试仓储：只实现内存构造钩子。"""

    def _build(self, item_id: int, values: dict[str, object]) -> Item:
        return Item(id=item_id, name=str(values["name"]))

    def _apply(self, item: Item, values: dict[str, object]) -> Item:
        return Item(id=item.id, name=str(values["name"]))

    def binding(self, *, read_only: bool) -> str:
        """暴露数据源绑定钩子（测试用）。"""
        return self._resolve_binding(read_only=read_only)

    def shard(self, logical_table: str) -> str:
        """暴露分片路由钩子（测试用）。"""
        return self._resolve_shard(logical_table)


def _repo() -> ItemRepository:
    return ItemRepository()


@pytest.mark.kiwi_id(11)
async def test_create_assigns_incrementing_id() -> None:
    """create 依次分配自增 ID。"""
    repo = _repo()
    first = await repo.create(name="甲")
    second = await repo.create(name="乙")
    assert (first.id, second.id) == (1, 2)


@pytest.mark.kiwi_id(11)
async def test_list_returns_items_sorted_by_id() -> None:
    """list 按 ID 升序返回。"""
    repo = _repo()
    await repo.create(name="甲")
    await repo.create(name="乙")
    assert [item.name for item in await repo.list()] == ["甲", "乙"]


@pytest.mark.kiwi_id(11)
async def test_get_and_derived_methods() -> None:
    """get 命中/缺失与 exists/count 派生方法。"""
    repo = _repo()
    await repo.create(name="甲")
    assert await repo.get(1) is not None
    assert await repo.get(999) is None
    assert await repo.exists(1) is True
    assert await repo.exists(999) is False
    assert await repo.count() == 1


@pytest.mark.kiwi_id(11)
async def test_update_success_and_missing_returns_none() -> None:
    """update 更新成功；不存在返回 None。"""
    repo = _repo()
    await repo.create(name="甲")
    updated = await repo.update(1, name="乙")
    assert updated is not None
    assert updated.name == "乙"
    assert await repo.get(1) == updated
    assert await repo.update(999, name="丙") is None


@pytest.mark.kiwi_id(11)
async def test_delete_success_and_missing_returns_false() -> None:
    """delete 删除成功；不存在返回 False。"""
    repo = _repo()
    await repo.create(name="甲")
    assert await repo.delete(1) is True
    assert await repo.count() == 0
    assert await repo.delete(999) is False


@pytest.mark.kiwi_id(11)
def test_routing_hooks_default_to_single_source() -> None:
    """路由钩子占位：单源同源、不路由（原表名）。"""
    repo = _repo()
    assert repo.binding(read_only=False) == "default"
    assert repo.binding(read_only=True) == "default"
    assert repo.shard("sys_demo") == "sys_demo"


@pytest.mark.kiwi_id(11)
def test_inheritance_chain() -> None:
    """继承链：内存基线 / DB 骨架 → 契约 → BaseObject。"""
    assert issubclass(BaseRepository, BaseObject)
    assert issubclass(BaseMemoryRepository, BaseRepository)
    assert issubclass(BaseDbRepository, BaseRepository)
    assert issubclass(ItemRepository, BaseMemoryRepository)

    from app.repositories.demo_repository import DemoRepository

    assert issubclass(DemoRepository, BaseMemoryRepository)


@pytest.mark.kiwi_id(11)
async def test_db_repository_is_placeholder() -> None:
    """数据库实现骨架：CRUD 占位抛错、不连库；exists 经派生链。"""
    skeleton = BaseDbRepository[Item]()
    with pytest.raises(NotImplementedError):
        await skeleton.list()
    with pytest.raises(NotImplementedError):
        await skeleton.get(1)
    with pytest.raises(NotImplementedError):
        await skeleton.count()
    with pytest.raises(NotImplementedError):
        await skeleton.create(name="甲")
    with pytest.raises(NotImplementedError):
        await skeleton.update(1, name="乙")
    with pytest.raises(NotImplementedError):
        await skeleton.delete(1)
    with pytest.raises(NotImplementedError):
        await skeleton.exists(1)
