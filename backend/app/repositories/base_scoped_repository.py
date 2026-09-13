"""repositories 层作用域过滤中间层：软删除 + 数据范围条件统一。

- 继承契约层 `BaseRepository`，为内存基线与数据库实现提供统一作用域过滤。
- 内存基线按 `ScopeCondition` 过滤；DB 实现回补时把条件拼入 WHERE。
"""

import operator
from abc import ABC
from collections.abc import Callable, Iterable, Sequence
from typing import Any, cast

from app.repositories.base_repository import BaseRepository
from app.scope.base import ScopeCondition

_COMPARATORS: dict[str, Callable[[Any, Any], bool]] = {
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
}


def _compare(value: object, target: object, op: str) -> bool:
    """按比较操作符比较（类型不匹配返回 False）。

    Args:
        value: 实体字段值。
        target: 目标值。
        op: `gt` / `gte` / `lt` / `lte`。

    Returns:
        bool: 比较结果。
    """
    func = _COMPARATORS.get(op)
    if func is None:
        return False
    try:
        return func(value, target)
    except TypeError:
        return False


def _between(value: object, target: object) -> bool:
    """区间判定：`target` 为 `(low, high)`。

    Args:
        value: 实体字段值。
        target: 区间（两元素）。

    Returns:
        bool: 落在区间内 True。
    """
    if not isinstance(target, (list, tuple)):
        return False
    sequence = cast("Sequence[object]", target)
    if len(sequence) != 2:
        return False
    return _compare(value, sequence[0], "gte") and _compare(value, sequence[1], "lte")


def _match(item: object, condition: ScopeCondition) -> bool:
    """判断实体是否满足单个作用域条件。

    Args:
        item: 实体对象。
        condition: 作用域条件。

    Returns:
        bool: 满足 True。
    """
    value = getattr(item, condition.field, None)
    op = condition.operator
    target = condition.value
    if op == "is_null":
        return value is None
    if op == "is_not_null":
        return value is not None
    if op == "eq":
        return bool(value == target)
    if op == "ne":
        return bool(value != target)
    if op == "in":
        if isinstance(target, (list, set, frozenset, tuple)):
            return any(value == member for member in cast("Iterable[object]", target))
        return False
    if op == "like":
        return isinstance(target, str) and isinstance(value, str) and target in value
    if op == "between":
        return _between(value, target)
    return _compare(value, target, op)


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
            elif isinstance(predicate, list):
                members = cast("list[object]", predicate)
                conditions.extend(item for item in members if isinstance(item, ScopeCondition))
        return conditions

    def _matches_scope(self, item: ModelT) -> bool:
        """实体是否满足全部作用域条件。

        Args:
            item: 实体对象。

        Returns:
            bool: 满足 True。
        """
        return all(_match(item, condition) for condition in self._scope_conditions())
