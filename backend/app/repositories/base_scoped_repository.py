"""repositories 层作用域过滤中间层：软删除 + 数据范围条件统一。

- 继承契约层 `BaseRepository`，为内存基线与数据库实现提供统一作用域过滤。
- 内存基线按 `ScopeCondition` 过滤；DB 实现回补时把条件拼入 WHERE。
"""

from abc import ABC
from collections.abc import Iterable
from typing import cast

from app.repositories.base_repository import BaseRepository
from app.scope.base import ScopeCondition


def _match(item: object, condition: ScopeCondition) -> bool:
    """判断实体是否满足单个作用域条件。

    Args:
        item: 实体对象。
        condition: 作用域条件。

    Returns:
        bool: 满足 True。
    """
    value = getattr(item, condition.field, None)
    if condition.operator == "is_null":
        return value is None
    if condition.operator == "is_not_null":
        return value is not None
    if condition.operator == "eq":
        return bool(value == condition.value)
    if condition.operator == "ne":
        return bool(value != condition.value)
    if condition.operator == "in":
        container = condition.value
        if isinstance(container, (list, set, frozenset, tuple)):
            return any(value == member for member in cast("Iterable[object]", container))
        return False
    return False


class BaseScopedRepository[ModelT](BaseRepository[ModelT], ABC):
    """作用域过滤中间层：软删除 + 数据范围条件。"""

    soft_delete_enabled: bool = True

    def _scope_conditions(self) -> list[ScopeCondition]:
        """作用域条件（软删除 + 数据范围）。

        Returns:
            list[ScopeCondition]: 过滤条件列表。
        """
        conditions: list[ScopeCondition] = []
        if self.soft_delete_enabled:
            conditions.append(ScopeCondition("deleted_at", "is_null", None))
        if self._data_scope is not None:
            predicate = self._data_scope.read_predicate()
            if isinstance(predicate, ScopeCondition):
                conditions.append(predicate)
        return conditions

    def _matches_scope(self, item: ModelT) -> bool:
        """实体是否满足全部作用域条件。

        Args:
            item: 实体对象。

        Returns:
            bool: 满足 True。
        """
        return all(_match(item, condition) for condition in self._scope_conditions())
