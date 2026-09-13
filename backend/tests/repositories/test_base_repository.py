"""仓储基类测试（Kiwi 11）：契约 / 内存基线 / DB 骨架（异步）；排序契约见 Kiwi 29。"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

import pytest

from app.core.base import BaseObject
from app.repositories.base_db_repository import BaseDbRepository
from app.repositories.base_memory_repository import BaseMemoryRepository
from app.repositories.base_repository import BaseRepository
from app.schemas.pagination import BaseCursorQuery, BasePageQuery
from app.schemas.sorting import SortDirection, SortSpec


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


@dataclass
class SortableItem:
    """带可排序字段的测试实体。"""

    id: int
    name: str
    rank: int | None = None


class SortableRepository(BaseMemoryRepository[SortableItem]):
    """测试仓储：声明白名单（name / rank）。"""

    sortable_fields = frozenset({"name", "rank"})

    def _build(self, item_id: int, values: dict[str, object]) -> SortableItem:
        return SortableItem(item_id, str(values["name"]), cast("int | None", values.get("rank")))

    def _apply(self, item: SortableItem, values: dict[str, object]) -> SortableItem:
        rank = cast("int | None", values.get("rank", item.rank))
        return SortableItem(item.id, str(values.get("name", item.name)), rank)

    def resolve_sort(self, query: BasePageQuery) -> list[SortSpec]:
        """暴露排序解析钩子（测试用）。"""
        return self._resolve_sort(query)


class SortableDbRepository(BaseDbRepository[SortableItem]):
    """测试用 DB 骨架：暴露排序语句钩子。"""

    def apply_sort[StatementT](self, statement: StatementT, sort: Sequence[SortSpec]) -> StatementT:
        """暴露 `_apply_sort` 钩子（测试用）。"""
        return self._apply_sort(statement, sort)


@dataclass
class MixedItem:
    """混合类型字段实体（验证排序兜底不抛错）。"""

    id: int
    value: object | None = None


class MixedRepository(BaseMemoryRepository[MixedItem]):
    """测试仓储：混合类型字段 value。"""

    sortable_fields = frozenset({"value"})

    def _build(self, item_id: int, values: dict[str, object]) -> MixedItem:
        return MixedItem(item_id, values.get("value"))

    def _apply(self, item: MixedItem, values: dict[str, object]) -> MixedItem:
        return MixedItem(item.id, values.get("value", item.value))


@pytest.mark.kiwi_id(29)
async def test_memory_list_sorts_single_field_both_directions() -> None:
    """内存基线支持单字段升序 / 降序排序。"""
    repo = SortableRepository()
    await repo.create(name="乙", rank=2)
    await repo.create(name="甲", rank=1)
    asc = await repo.list(sort=[SortSpec(field="rank", direction=SortDirection.ASC)])
    desc = await repo.list(sort=[SortSpec(field="rank", direction=SortDirection.DESC)])
    assert [item.name for item in asc] == ["甲", "乙"]
    assert [item.name for item in desc] == ["乙", "甲"]


@pytest.mark.kiwi_id(29)
async def test_memory_list_sorts_multi_key_and_keeps_default_order() -> None:
    """多键排序主次键生效；不传 sort 保持 ID 升序（既有行为回归）。"""
    repo = SortableRepository()
    await repo.create(name="b", rank=1)
    await repo.create(name="a", rank=1)
    await repo.create(name="c", rank=0)
    specs = [
        SortSpec(field="rank", direction=SortDirection.ASC),
        SortSpec(field="name", direction=SortDirection.ASC),
    ]
    assert [item.name for item in await repo.list(sort=specs)] == ["c", "a", "b"]
    assert [item.id for item in await repo.list()] == [1, 2, 3]


@pytest.mark.kiwi_id(29)
async def test_memory_list_handles_none_values_by_direction() -> None:
    """空值参与比较：升序末尾 / 降序首位。"""
    repo = SortableRepository()
    await repo.create(name="甲", rank=2)
    await repo.create(name="乙")
    asc = await repo.list(sort=[SortSpec(field="rank", direction=SortDirection.ASC)])
    desc = await repo.list(sort=[SortSpec(field="rank", direction=SortDirection.DESC)])
    assert [item.name for item in asc] == ["甲", "乙"]
    assert [item.name for item in desc] == ["乙", "甲"]


@pytest.mark.kiwi_id(29)
async def test_memory_sort_tolerates_mixed_types() -> None:
    """类型混合按分桶兜底比较（数值 → 字符串 → 空值），不抛 TypeError。"""
    repo = MixedRepository()
    await repo.create(value="字")
    await repo.create(value=3)
    await repo.create(value=None)
    result = await repo.list(sort=[SortSpec(field="value", direction=SortDirection.ASC)])
    assert [item.value for item in result] == [3, "字", None]


@pytest.mark.kiwi_id(29)
async def test_sort_whitelist_default_and_call_override() -> None:
    """类属性白名单为默认；未声明字段被忽略；`specs(whitelist=...)` 可按调用覆盖。"""
    repo = SortableRepository()
    await repo.create(name="乙", rank=1)
    await repo.create(name="甲", rank=2)

    assert [spec.field for spec in repo.resolve_sort(BasePageQuery(order_by="name", order=["asc"]))] == ["name"]
    ignored = await repo.list(sort=repo.resolve_sort(BasePageQuery(order_by="id")))
    assert [item.id for item in ignored] == [1, 2]
    overridden = await repo.list(sort=BasePageQuery(order_by="id", order=["desc"]).specs({"id"}))
    assert [item.id for item in overridden] == [2, 1]


@pytest.mark.kiwi_id(29)
async def test_pagination_queries_carry_sort() -> None:
    """分页请求携带排序：list_page / list_cursor 返回有序结果。"""
    repo = SortableRepository()
    await repo.create(name="甲", rank=2)
    await repo.create(name="乙", rank=1)
    page = await repo.list_page(BasePageQuery(page=1, size=10, order_by="rank", order=["asc"]))
    cursor = await repo.list_cursor(BaseCursorQuery(limit=1, order_by="rank", order=["desc"]))
    assert [item.name for item in page] == ["乙", "甲"]
    assert [item.name for item in cursor] == ["甲"]


@pytest.mark.kiwi_id(29)
async def test_db_repository_sort_placeholder() -> None:
    """DB 侧：list(sort=...) 占位抛错；`_apply_sort` 占位原样返回语句（不连库）。"""
    skeleton = SortableDbRepository()
    with pytest.raises(NotImplementedError):
        await skeleton.list(sort=[SortSpec(field="rank")])
    statement = object()
    assert skeleton.apply_sort(statement, [SortSpec(field="rank")]) is statement
