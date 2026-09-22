"""repositories 层作用域过滤中间层：软删除 + 数据范围 + 租户条件统一。

- 继承契约层 `BaseRepository`，为内存基线与数据库实现提供统一作用域过滤。
- 内存基线按 `ScopeCondition` 过滤；DB 实现回补时把条件拼入 WHERE。
- 租户条件（第二层隔离）：模型含 `tenant_id` 列时由具体仓储置 `tenant_scoped=True`，
  上下文租户有主键时强制注入，物理库隔离（第一层）之外的兜底口径。
"""

import operator
from abc import ABC
from collections.abc import Callable, Iterable, Sequence
from typing import Any, cast

from app.db.tenant import current_tenant_context
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
    """作用域过滤中间层：软删除 + 数据范围 + 租户条件。"""

    soft_delete_enabled: bool = True
    tenant_scoped: bool = False
    """模型含 `tenant_id` 列时置 True（同库多租户 / 平台侧租户维度表），强制注入租户条件。"""

    def _scope_conditions(self, *, include_soft_delete: bool = True) -> list[ScopeCondition]:
        """作用域条件（软删除 → 数据范围 → 租户）。

        Args:
            include_soft_delete: 是否包含软删除过滤（物理删除出口需穿透已软删行时为 False）。

        Returns:
            list[ScopeCondition]: 过滤条件列表。
        """
        conditions: list[ScopeCondition] = []
        if self.soft_delete_enabled and include_soft_delete:
            conditions.append(ScopeCondition("deleted_at", "is_null", None))
        if self._data_scope is not None:
            predicate = self._data_scope.read_predicate()
            if isinstance(predicate, ScopeCondition):
                conditions.append(predicate)
            elif isinstance(predicate, list):
                members = cast("list[object]", predicate)
                conditions.extend(item for item in members if isinstance(item, ScopeCondition))
        tenant = self._tenant_condition()
        if tenant is not None:
            conditions.append(tenant)
        return conditions

    def _tenant_condition(self) -> ScopeCondition | None:
        """租户强制过滤条件（未启用租户隔离 / 上下文无主键时返回 None）。

        Returns:
            ScopeCondition | None: `tenant_id = <当前租户主键>` 条件。
        """
        if not self.tenant_scoped:
            return None
        tenant_id = current_tenant_context().tenant_id
        if tenant_id is None:
            return None
        return ScopeCondition("tenant_id", "eq", tenant_id)

    async def soft_delete(self, item_id: int) -> bool:
        """软删除记录（派生默认：委托 `delete`）。

        数据库实现覆写为置 `deleted_at`；内存基线为测试替身、实体无软删除字段，
        保持 `delete` 的硬删语义（差异在实现侧注明）。

        Args:
            item_id: 记录 ID。

        Returns:
            bool: 删除成功 True；不存在（或不在作用域）False。
        """
        return await self.delete(item_id)

    async def hard_delete(self, item_id: int) -> bool:
        """物理删除记录（派生默认：委托 `delete`；数据库实现覆写为真实删除）。

        Args:
            item_id: 记录 ID。

        Returns:
            bool: 删除成功 True；不存在（或不在作用域）False。
        """
        return await self.delete(item_id)

    def _matches_scope(self, item: ModelT) -> bool:
        """实体是否满足全部作用域条件。

        Args:
            item: 实体对象。

        Returns:
            bool: 满足 True。
        """
        return all(_match(item, condition) for condition in self._scope_conditions())
