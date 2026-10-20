"""repositories 层作用域过滤中间层：软删除 + 数据范围 + 租户条件统一。

- 继承契约层 `BaseRepository`，为内存基线与数据库实现提供统一作用域过滤。
- 内存基线按 `ScopeCondition` 过滤；DB 实现把条件拼入 WHERE。
- 租户条件（第二层隔离）：模型含 `tenant_id` 列时由具体仓储置 `tenant_scoped=True`，
  上下文租户有主键时强制注入，物理库隔离（第一层）之外的兜底口径。

**数据源维度条件翻译（`04-4`）**：`select` / `region` 的条件带 `data_source_key` 且 `field` 为空，
由本表声明的 `scope_columns`（数据源标识 → 实体列名）翻译成列条件；未声明且无 `field` 可回落时
该条件退化为**永假**（`DENY_ALL_CONDITION`）并上报 + 计数——从严不放大可见范围。
"""

import logging
import operator
import re
from abc import ABC
from collections.abc import Callable, Iterable, Sequence, Set
from dataclasses import replace
from typing import Any, cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.tenant import current_tenant_context
from bms_core.permission.cache import current_permission_cache_store
from bms_core.repositories.base_repository import BaseRepository
from bms_core.scope.base import DENY_ALL_CONDITION, ScopeCondition

_logger = logging.getLogger(__name__)

_COMPARATORS: ConcurrentStableDict[str, Callable[[Any, Any], bool]] = ConcurrentStableDict(
    {
        "gt": operator.gt,
        "gte": operator.ge,
        "lt": operator.lt,
        "lte": operator.le,
    }
)


def _coerce(target: object, sample: object) -> object:
    """把目标值按实体值的类型归一（整数 / 浮点字符串互转；不可转即原样返回）。

    数据权限的集合值来自字典项（字符串），业务列可能是 BIGINT——不归一会「配了却过滤不到」；
    归一失败（如 `"abc"` → int）保持原值，由比较返回不命中（等价于该值不在范围内）。

    Args:
        target: 目标值（区间端点 / 集合成员）。
        sample: 实体字段值（类型参照）。

    Returns:
        object: 归一后的目标值；无法归一时返回原对象。
    """
    if isinstance(sample, bool) or isinstance(target, bool):
        return target
    if not isinstance(target, str):
        return target
    try:
        if isinstance(sample, int):
            return int(target)
        if isinstance(sample, float):
            return float(target)
    except ValueError:
        return target
    return target


def _compare(value: object, target: object, op: str) -> bool:
    """按比较操作符比较（类型不匹配时双向归一后重试；仍不匹配返回 False）。

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
    candidates: ConcurrentStableList[tuple[object, object]] = ConcurrentStableList(
        (
            (value, target),
            (value, _coerce(target, value)),
            (_coerce(value, target), target),
        )
    )
    for left, right in candidates:
        try:
            return bool(func(left, right))
        except TypeError:
            continue
    return False


def _equal(value: object, target: object) -> bool:
    """等值判定（类型不匹配时双向归一后重试：字符串 ↔ 数值）。

    Args:
        value: 实体字段值。
        target: 目标值（集合成员）。

    Returns:
        bool: 相等 True。
    """
    if value == target:
        return True
    if isinstance(value, bool) or isinstance(target, bool):
        return False
    if isinstance(value, int | float) and isinstance(target, str):
        coerced = _coerce(target, value)
        return coerced is not target and coerced == value
    if isinstance(target, int | float) and isinstance(value, str):
        coerced_value = _coerce(value, target)
        return coerced_value is not value and coerced_value == target
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
    sequence = cast("list[object] | tuple[object, ...]", target)
    if len(sequence) != 2:
        return False
    return _compare(value, sequence[0], "gte") and _compare(value, sequence[1], "lte")


def _like_regex(pattern: str) -> str:
    """SQL LIKE 模式转正则（`%` → `.*`、`_` → `.`；其余字符转义）。

    Args:
        pattern: LIKE 模式（含 `%` / `_`）。

    Returns:
        str: 等价正则（用于 `fullmatch`）。
    """
    parts: ConcurrentStableList[str] = ConcurrentStableList()
    for char in pattern:
        if char == "%":
            parts.add(".*")
        elif char == "_":
            parts.add(".")
        else:
            parts.add(re.escape(char))
    return "".join(parts)


def _like(value: object, target: object) -> bool:
    """LIKE 判定：模式含通配符（`%` / `_`）时按通配匹配，否则按子串（向后兼容）。

    通配模式与数据库实现的 SQL `LIKE` 同义（`%` 任意串、`_` 单字符），故内存基线与库实现
    对同一 `ScopeCondition` 得出一致结果；不含通配符的模式保持既有「子串包含」语义。

    Args:
        value: 实体字段值。
        target: LIKE 模式（`ScopeCondition.value`）。

    Returns:
        bool: 命中 True。
    """
    if not isinstance(target, str) or not isinstance(value, str):
        return False
    if "%" not in target and "_" not in target:
        return target in value
    return re.fullmatch(_like_regex(target), value) is not None


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
        return _equal(value, target)
    if op == "ne":
        return not _equal(value, target)
    if op == "in":
        if isinstance(target, Sequence | Set) and not isinstance(target, str | bytes):
            return any(_equal(value, member) for member in cast("Iterable[object]", target))
        return False
    if op == "like":
        return _like(value, target)
    if op == "between":
        return _between(value, target)
    return _compare(value, target, op)


class BaseScopedRepository[ModelT](BaseRepository[ModelT], ABC):
    """作用域过滤中间层：软删除 + 数据范围 + 租户条件。"""

    soft_delete_enabled: bool = True
    tenant_scoped: bool = False
    """模型含 `tenant_id` 列时置 True（同库多租户 / 平台侧租户维度表），强制注入租户条件。"""

    scope_columns: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    """数据源标识 → 本表实体列名（数据范围条件翻译用；空 = 未声明，数据源维度条件即永假）。"""

    def _scope_conditions(self, *, include_soft_delete: bool = True) -> ConcurrentStableList[ScopeCondition]:
        """作用域条件（软删除 → 数据范围 → 租户）。

        Args:
            include_soft_delete: 是否包含软删除过滤（物理删除出口需穿透已软删行时为 False）。

        Returns:
            ConcurrentStableList[ScopeCondition]: 过滤条件列表（数据源维度条件已翻译为列条件）。
        """
        conditions: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
        if self.soft_delete_enabled and include_soft_delete:
            conditions.add(ScopeCondition("deleted_at", "is_null", None))
        if self._data_scope is not None:
            predicate = self._data_scope.read_predicate()
            if isinstance(predicate, ScopeCondition):
                conditions.update(self._translate_scope((predicate,)))
            elif isinstance(predicate, (list, ConcurrentStableList)):
                members = cast("Iterable[object]", predicate)
                conditions.update(self._translate_scope(item for item in members if isinstance(item, ScopeCondition)))
        tenant = self._tenant_condition()
        if tenant is not None:
            conditions.add(tenant)
        return conditions

    def _translate_scope(self, conditions: Iterable[ScopeCondition]) -> ConcurrentStableList[ScopeCondition]:
        """把数据范围条件翻译到实体列（数据源维度条件按 `scope_columns` 声明）。

        未声明映射且条件无 `field` 可回落时，整批退化为单条永假条件（从严）+ 上报 + 计数。

        Args:
            conditions: 数据范围 provider 产出的条件。

        Returns:
            ConcurrentStableList[ScopeCondition]: 可落列的条件列表（或单条永假）。
        """
        translated: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
        for condition in conditions:
            column = self._scope_column(condition)
            if column is None:
                denied: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
                denied.add(DENY_ALL_CONDITION)
                return denied
            translated.add(replace(condition, field=column))
        return translated

    def _scope_column(self, condition: ScopeCondition) -> str | None:
        """把单条条件翻译为实体列名。

        映射优先（`match` 的白名单字段也一并被覆盖）；无映射时回落 `field` 原名；两者皆无返回 None。

        Args:
            condition: 数据范围条件。

        Returns:
            str | None: 实体列名；无法落列返回 None。
        """
        data_source_key = condition.data_source_key
        if data_source_key is None:
            return condition.field
        mapped = self.scope_columns.get(data_source_key)
        if mapped is not None:
            return mapped
        if condition.field:
            return condition.field
        _logger.warning("数据范围规则不产生放行：%s 未声明实体列映射（scope_columns）", data_source_key)
        current_permission_cache_store().record_invalid_rule()
        return None

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
