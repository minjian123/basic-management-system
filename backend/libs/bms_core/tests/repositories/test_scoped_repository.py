"""作用域过滤中间层测试（Kiwi 11 / 2324）：软删除 + 数据范围条件 + 数据源维度翻译。"""

from dataclasses import dataclass

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.permission.cache import current_permission_cache_store, reset_permission_cache_store
from bms_core.repositories.base_memory_repository import BaseMemoryRepository
from bms_core.repositories.base_scoped_repository import (
    _coerce,  # pyright: ignore[reportPrivateUsage]
    _compare,  # pyright: ignore[reportPrivateUsage]
    _equal,  # pyright: ignore[reportPrivateUsage]
)
from bms_core.scope.base import DataScope, ScopeCondition
from bms_core.scope.null import NullDataScope


@dataclass
class Row:
    """测试实体（含软删除与归属字段）。"""

    id: int
    name: str
    deleted_at: str | None = None
    owner_id: int = 0


class RowRepository(BaseMemoryRepository[Row]):
    """测试仓储。"""

    def _build(self, item_id: int, values: ConcurrentStableDict[str, object]) -> Row:
        return Row(
            id=item_id,
            name=str(values["name"]),
            deleted_at=values.get("deleted_at"),  # type: ignore[arg-type]
            owner_id=int(values.get("owner_id", 0)),  # type: ignore[arg-type]
        )

    def _apply(self, item: Row, values: ConcurrentStableDict[str, object]) -> Row:
        return Row(id=item.id, name=str(values["name"]), deleted_at=item.deleted_at, owner_id=item.owner_id)


class ScopedRowRepository(RowRepository):
    """暴露作用域钩子的测试仓储（`owner_id` 承载 `org_dept` 数据源）。"""

    scope_columns: ConcurrentStableDict[str, str] = ConcurrentStableDict({"org_dept": "owner_id"})

    def use_scope(self, scope: DataScope | None) -> None:
        """注入数据范围。"""
        self._apply_data_scope(scope)

    def disable_soft_delete(self) -> None:
        """关闭软删除过滤。"""
        self.soft_delete_enabled = False


class FixedScope(DataScope):
    """固定返回条件的测试数据范围。"""

    def __init__(self, condition: ScopeCondition | ConcurrentStableList[ScopeCondition]) -> None:
        self._condition = condition

    def read_predicate(self) -> object:
        """返回固定条件。"""
        return self._condition

    def allow_write(
        self,
        values: ConcurrentStableDict[str, object],
        *,
        scope_columns: ConcurrentStableDict[str, str] | None = None,
    ) -> bool:
        """恒定允许。"""
        del values, scope_columns
        return True


async def _repo_with_rows() -> ScopedRowRepository:
    repo = ScopedRowRepository()
    await repo.create(name="甲", owner_id=1)
    await repo.create(name="乙", owner_id=2)
    await repo.create(name="丙", owner_id=3)
    await repo.create(name="删", owner_id=2, deleted_at="2026-09-13")
    return repo


@pytest.mark.kiwi_id(11)
async def test_soft_delete_filters_default() -> None:
    """默认软删除过滤：已删记录不进 list/get/count。"""
    repo = await _repo_with_rows()
    assert [row.name for row in await repo.list()] == ["甲", "乙", "丙"]
    assert await repo.count() == 3
    deleted = await repo.get(4)
    assert deleted is None
    assert await repo.exists(4) is False


@pytest.mark.kiwi_id(11)
async def test_soft_delete_disabled() -> None:
    """关闭软删除过滤后包含已删记录。"""
    repo = await _repo_with_rows()
    repo.disable_soft_delete()
    assert len(await repo.list()) == 4
    assert await repo.get(4) is not None


@pytest.mark.kiwi_id(11)
async def test_default_soft_and_hard_delete_delegate_to_delete() -> None:
    """派生默认：内存基线未覆写软删 / 物理删，二者一律委托 `delete`（硬删语义）。"""
    repo = await _repo_with_rows()
    assert await repo.soft_delete(1) is True
    assert await repo.get(1) is None
    assert await repo.hard_delete(2) is True
    assert await repo.get(2) is None
    assert await repo.hard_delete(999) is False


@pytest.mark.kiwi_id(11)
async def test_scope_operators() -> None:
    """数据范围条件：eq / ne / in / like / 比较 / between / 空值 / 异常与未知。"""
    repo = await _repo_with_rows()
    repo.disable_soft_delete()

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "eq", 2)))
    assert [row.name for row in await repo.list()] == ["乙", "删"]

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "ne", 2)))
    assert [row.name for row in await repo.list()] == ["甲", "丙"]

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "in", [1, 3])))
    assert [row.name for row in await repo.list()] == ["甲", "丙"]

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "in", ConcurrentStableSet([1, 3]))))
    assert [row.name for row in await repo.list()] == ["甲", "丙"]

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "in", 2)))
    assert await repo.list() == []

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "in", "13")))
    assert await repo.list() == []

    repo.use_scope(FixedScope(ScopeCondition("name", "like", "乙")))
    assert [row.name for row in await repo.list()] == ["乙"]

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "gt", 2)))
    assert [row.name for row in await repo.list()] == ["丙"]

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "gte", 2)))
    assert [row.name for row in await repo.list()] == ["乙", "丙", "删"]

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "lt", 2)))
    assert [row.name for row in await repo.list()] == ["甲"]

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "lte", 2)))
    assert [row.name for row in await repo.list()] == ["甲", "乙", "删"]

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "between", [2, 2])))
    assert [row.name for row in await repo.list()] == ["乙", "删"]

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "between", 2)))
    assert await repo.list() == []

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "between", [1, 2, 3])))
    assert await repo.list() == []

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "gt", "x")))
    assert await repo.list() == []

    repo.use_scope(FixedScope(ScopeCondition("deleted_at", "is_null", None)))
    assert [row.name for row in await repo.list()] == ["甲", "乙", "丙"]

    repo.use_scope(FixedScope(ScopeCondition("deleted_at", "is_not_null", None)))
    assert [row.name for row in await repo.list()] == ["删"]

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "regex", 1)))
    assert await repo.list() == []

    null_scope = NullDataScope()
    repo.use_scope(null_scope)
    assert len(await repo.list()) == 4
    assert null_scope.allow_write(ConcurrentStableDict()) is True
    assert null_scope.allow_write(ConcurrentStableDict(), scope_columns=ConcurrentStableDict({"a": "b"})) is True


@pytest.mark.kiwi_id(11)
async def test_like_wildcards_and_non_string_values() -> None:
    """LIKE 判定：通配符模式（`%` / `_`）与数据库同义；非字符串取值恒不命中。"""
    repo = await _repo_with_rows()

    repo.use_scope(FixedScope(ScopeCondition("name", "like", "乙%")))
    assert [row.name for row in await repo.list()] == ["乙"]

    repo.use_scope(FixedScope(ScopeCondition("name", "like", "__")))
    assert await repo.list() == []

    repo.use_scope(FixedScope(ScopeCondition("name", "like", 1)))
    assert await repo.list() == []


@pytest.mark.kiwi_id(11)
async def test_scope_condition_list_and_write_scope() -> None:
    """条件列表（AND）；越权 / 已删记录不可改删。"""
    repo = ScopedRowRepository()
    repo.disable_soft_delete()
    await repo.create(name="甲", owner_id=1)
    await repo.create(name="乙", owner_id=2)
    await repo.create(name="删", owner_id=2, deleted_at="2026-09-13")

    repo.use_scope(
        FixedScope(ConcurrentStableList([ScopeCondition("owner_id", "eq", 2), ScopeCondition("name", "eq", "乙")]))
    )
    assert [row.name for row in await repo.list()] == ["乙"]

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "eq", 1)))
    assert await repo.update(2, name="越权") is None
    assert await repo.delete(2) is False
    assert await repo.update(1, name="甲改") is not None
    assert await repo.delete(1) is True

    repo.use_scope(None)
    repo.soft_delete_enabled = True
    assert await repo.delete(3) is False


class UnmappedRowRepository(ScopedRowRepository):
    """未声明数据源映射的仓储（数据源维度条件应退化为永假）。"""

    scope_columns: ConcurrentStableDict[str, str] = ConcurrentStableDict()


@pytest.mark.kiwi_id(2324)
async def test_data_source_conditions_translate_and_coerce() -> None:
    """数据源维度条件：按 `scope_columns` 翻译列，集合值按实体值类型归一（`"1"` ↔ `1`）。"""
    repo = await _repo_with_rows()
    repo.disable_soft_delete()

    repo.use_scope(FixedScope(ScopeCondition("", "in", ["1", "2"], "org_dept")))
    assert [row.name for row in await repo.list()] == ["甲", "乙", "删"]

    repo.use_scope(FixedScope(ScopeCondition("", "between", ("2", "3"), "org_dept")))
    assert [row.name for row in await repo.list()] == ["乙", "丙", "删"]


@pytest.mark.kiwi_id(2324)
async def test_unmapped_data_source_condition_denies_all() -> None:
    """未声明映射且无字段可回落：整批退化为永假（查不到数据）+ 计数。"""
    reset_permission_cache_store()
    repo = UnmappedRowRepository()
    await repo.create(name="甲", owner_id=1)
    repo.use_scope(FixedScope(ScopeCondition("", "in", ["1"], "org_dept")))
    assert await repo.list() == []
    assert current_permission_cache_store().stats()["invalid_rule_rejections"] == 1


@pytest.mark.kiwi_id(2324)
async def test_unmapped_condition_falls_back_to_field() -> None:
    """未声明映射但条件带字段（`match`）：回落字段原名过滤。"""
    repo = UnmappedRowRepository()
    await repo.create(name="乙", owner_id=2)
    repo.use_scope(FixedScope(ScopeCondition("name", "like", "乙", "org_dept")))
    assert [row.name for row in await repo.list()] == ["乙"]


def test_coerce_equal_and_compare_helpers() -> None:
    """类型归一与等值 / 比较：字符串 ↔ 数值互转，不可转即不命中。"""
    assert _coerce("5", 1) == 5
    assert _coerce("x", 1) == "x"
    assert _coerce("1.5", 1.5) == 1.5
    assert _coerce("x", 1.5) == "x"
    assert _coerce("5", True) == "5"
    assert _coerce(True, 1) is True
    assert _coerce(5, "s") == 5
    assert _coerce("5", None) == "5"

    assert _equal(1, "1") is True
    assert _equal("1", 1) is True
    assert _equal(1, "x") is False
    assert _equal(True, "True") is False
    assert _equal("x", "y") is False

    assert _compare(3, "2", "gt") is True
    assert _compare("3", 2, "gt") is True
    assert _compare(3, "x", "gt") is False
    assert _compare(3, 2, "nope") is False
