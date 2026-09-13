"""BaseRepository 通用行为测试（Kiwi 11）。"""

from dataclasses import dataclass

import pytest

from app.repositories.base_db_repository import BaseDbRepository
from app.repositories.base_repository import BaseRepository


@dataclass
class Item:
    """测试实体。"""

    id: int
    name: str


class ItemRepository(BaseRepository[Item]):
    """测试仓储：只实现构造钩子，通用流程走基类。"""

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


class DbItemRepository(BaseDbRepository[Item]):
    """测试用：暴露数据库骨架的占位方法（含内存构造钩子）。"""

    def build(self, item_id: int, values: dict[str, object]) -> Item:
        """暴露内存构造钩子（测试用）。"""
        return self._build(item_id, values)

    def apply(self, item: Item, values: dict[str, object]) -> Item:
        """暴露内存更新钩子（测试用）。"""
        return self._apply(item, values)


@pytest.mark.kiwi_id(11)
def test_create_assigns_incrementing_id() -> None:
    """create 依次分配自增 ID。"""
    repo = ItemRepository()
    first = repo.create(name="甲")
    second = repo.create(name="乙")
    assert (first.id, second.id) == (1, 2)


@pytest.mark.kiwi_id(11)
def test_list_returns_items_sorted_by_id() -> None:
    """list 按 ID 升序返回。"""
    repo = ItemRepository()
    repo.create(name="甲")
    repo.create(name="乙")
    assert [item.name for item in repo.list()] == ["甲", "乙"]


@pytest.mark.kiwi_id(11)
def test_get_and_derived_methods() -> None:
    """get 命中/缺失与 exists/count 派生方法。"""
    repo = ItemRepository()
    repo.create(name="甲")
    assert repo.get(1) is not None
    assert repo.get(999) is None
    assert repo.exists(1) is True
    assert repo.exists(999) is False
    assert repo.count() == 1


@pytest.mark.kiwi_id(11)
def test_update_success_and_missing_returns_none() -> None:
    """update 更新成功；不存在返回 None。"""
    repo = ItemRepository()
    repo.create(name="甲")
    updated = repo.update(1, name="乙")
    assert updated is not None
    assert updated.name == "乙"
    assert repo.get(1) == updated
    assert repo.update(999, name="丙") is None


@pytest.mark.kiwi_id(11)
def test_delete_success_and_missing_returns_false() -> None:
    """delete 删除成功；不存在返回 False。"""
    repo = ItemRepository()
    repo.create(name="甲")
    assert repo.delete(1) is True
    assert repo.count() == 0
    assert repo.delete(999) is False


@pytest.mark.kiwi_id(11)
def test_demo_repository_inherits_base() -> None:
    """demo 仓库继承 BaseRepository（继承约定生效）。"""
    from app.repositories.demo_repository import DemoRepository

    assert issubclass(DemoRepository, BaseRepository)


@pytest.mark.kiwi_id(11)
def test_routing_hooks_default_to_single_source() -> None:
    """路由钩子占位：单源同源、不路由（原表名）。"""
    repo = ItemRepository()
    assert repo.binding(read_only=False) == "default"
    assert repo.binding(read_only=True) == "default"
    assert repo.shard("sys_demo") == "sys_demo"


@pytest.mark.kiwi_id(11)
def test_db_repository_is_placeholder() -> None:
    """数据库实现骨架：继承 BaseRepository，方法占位抛错、不连库。"""
    assert issubclass(BaseDbRepository, BaseRepository)
    skeleton = DbItemRepository()
    with pytest.raises(NotImplementedError):
        skeleton.build(1, {"name": "甲"})
    with pytest.raises(NotImplementedError):
        skeleton.apply(Item(id=1, name="甲"), {"name": "乙"})
    with pytest.raises(NotImplementedError):
        skeleton.list()
    with pytest.raises(NotImplementedError):
        skeleton.get(1)
    with pytest.raises(NotImplementedError):
        skeleton.count()
    with pytest.raises(NotImplementedError):
        skeleton.create(name="甲")
    with pytest.raises(NotImplementedError):
        skeleton.update(1, name="乙")
    with pytest.raises(NotImplementedError):
        skeleton.delete(1)
    with pytest.raises(NotImplementedError):
        skeleton.exists(1)
