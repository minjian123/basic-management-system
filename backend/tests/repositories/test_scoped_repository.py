"""作用域过滤中间层测试（Kiwi 11）：软删除 + 数据范围条件。"""

from dataclasses import dataclass

import pytest

from app.repositories.base_memory_repository import BaseMemoryRepository
from app.scope.base import DataScope, NullDataScope, ScopeCondition


@dataclass
class Row:
    """测试实体（含软删除与归属字段）。"""

    id: int
    name: str
    deleted_at: str | None = None
    owner_id: int = 0


class RowRepository(BaseMemoryRepository[Row]):
    """测试仓储。"""

    def _build(self, item_id: int, values: dict[str, object]) -> Row:
        return Row(
            id=item_id,
            name=str(values["name"]),
            deleted_at=values.get("deleted_at"),  # type: ignore[arg-type]
            owner_id=int(values.get("owner_id", 0)),  # type: ignore[arg-type]
        )

    def _apply(self, item: Row, values: dict[str, object]) -> Row:
        return Row(id=item.id, name=str(values["name"]), deleted_at=item.deleted_at, owner_id=item.owner_id)


class ScopedRowRepository(RowRepository):
    """暴露作用域钩子的测试仓储。"""

    def use_scope(self, scope: DataScope | None) -> None:
        """注入数据范围。"""
        self._apply_data_scope(scope)

    def disable_soft_delete(self) -> None:
        """关闭软删除过滤。"""
        self.soft_delete_enabled = False


class FixedScope(DataScope):
    """固定返回单个条件的测试数据范围。"""

    def __init__(self, condition: ScopeCondition) -> None:
        self._condition = condition

    def read_predicate(self) -> object:
        """返回固定条件。"""
        return self._condition

    def allow_write(self, values: dict[str, object]) -> bool:
        """恒定允许。"""
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
async def test_scope_operators() -> None:
    """数据范围条件：eq / ne / in / is_null / is_not_null / 未知操作符。"""
    repo = await _repo_with_rows()
    repo.disable_soft_delete()

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "eq", 2)))
    assert [row.name for row in await repo.list()] == ["乙", "删"]

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "ne", 2)))
    assert [row.name for row in await repo.list()] == ["甲", "丙"]

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "in", [1, 3])))
    assert [row.name for row in await repo.list()] == ["甲", "丙"]

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "in", 2)))
    assert await repo.list() == []

    repo.use_scope(FixedScope(ScopeCondition("deleted_at", "is_null", None)))
    assert [row.name for row in await repo.list()] == ["甲", "乙", "丙"]

    repo.use_scope(FixedScope(ScopeCondition("deleted_at", "is_not_null", None)))
    assert [row.name for row in await repo.list()] == ["删"]

    repo.use_scope(FixedScope(ScopeCondition("owner_id", "gt", 1)))
    assert await repo.list() == []

    repo.use_scope(NullDataScope())
    assert len(await repo.list()) == 4
