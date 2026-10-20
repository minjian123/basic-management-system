"""基座内建 RBAC 数据范围 provider（`[data_scope].provider = "rbac"`，域 `data_scope`）。

- **输入**：请求级权限快照的 `data_scopes`（`data_source_key` / `policy_type` / `config`，由引擎计算并缓存）；
- **读**：按 `policy_type` 经策略注册表求值（核心不判策略类型），同字典类型内多规则**并集**，
  跨字典类型**合取**；非法 / 未注册策略退化为永假（从严）；
- **写**：服务层写入口显式调 `allow_write(values, scope_columns=…)`——待写值须落在同一批条件内，
  失败拒（`30001`）；`scope_columns`（数据源 → 实体列）用于把数据源维度条件落到列，未声明即拒；
- **豁免 / 未预加载**：不过滤、恒允许（由认证链与上层承担）；
- **租户边界**：条件不含 `tenant_id`；租户过滤由基座注入点 `BaseScopedRepository._tenant_condition`
  强制叠加（任何策略不得跨租户）。

本实现只消费基座快照与策略注册表，**不 import 任何服务包、不碰任何 ORM**，故落在共享基座；
四策略求值器见 `scope/policies_rbac.py`（由 `register_rbac_data_scope` 一并登记）。

**口径偏差（已登记）**：详设 §5.6 的「多策略结果 OR 合并」在本基座注入点（条件列表按 AND 合取）
下只可对**同字段**的并集做真合并（多 `IN` 合并为一个 `IN`）；不同字段 / 不同操作符的并集只能退化为
合取（从严），并上报——从严不越权，且业务维度通常单一字段。

**集合物化与大集合护栏（`04-3`）**：规则结果的 `in` 值在产出时去重物化为 `ConcurrentStableSet`
（层2 命中即同一份集合，跨用户共享）；并集合并后统一校验，任一 `in` 条件元素数超
`[data_scope].options.max_in_values`（缺省 1000）即整体退化为**永假**并上报引导（改用区域 / 匹配 /
扩展策略），保证读过滤不产出巨型 `IN` 列表——`region` / `match` 本身以 `between` / `like` 原生算子
表达，不参与该判定。写校验与读共用同一批条件：任一条件为永假即拒绝写入。

**四策略口径（`04-4`）**：`select` / `region` 产出**数据源维度**条件（`field` 留空、带
`data_source_key`），`match` 另带配置里的白名单字段；消费方按自身声明的「数据源 → 实体列」
映射翻译（`BaseScopedRepository.scope_columns`），写校验经 `allow_write(scope_columns=…)` 传入
同一份映射——读写口径一致。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping, Sequence, Set, Sized
from typing import Any, cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.config import Settings
from bms_core.core.factory import BasePluginFactory
from bms_core.core.plugin import default_plugin_registry, register_plugin
from bms_core.permission.cache import current_permission_cache_store
from bms_core.permission.snapshot import PermissionSnapshot, get_current_permission_snapshot
from bms_core.permission.version import permission_rule_key
from bms_core.scope.base import DENY_ALL_CONDITION, DataScope, ScopeCondition
from bms_core.scope.limits import DEFAULT_MAX_IN_VALUES, OPTION_MAX_IN_VALUES, data_scope_max_in_values
from bms_core.scope.policies import scope_policy
from bms_core.scope.policies_rbac import register_rbac_scope_policies

__all__ = [
    "DEFAULT_MAX_IN_VALUES",
    "OPTION_MAX_IN_VALUES",
    "RBAC_DATA_SCOPE_NAME",
    "RbacDataScope",
    "RbacDataScopeFactory",
    "data_scope_max_in_values",
    "register_rbac_data_scope",
]

_logger = logging.getLogger(__name__)

RBAC_DATA_SCOPE_NAME = "rbac"
"""RBAC 数据范围实现名（`[data_scope].provider`）。"""

_REGISTERED_REGISTRIES: ConcurrentStableList[object] = ConcurrentStableList()
"""已登记 RBAC 数据范围的注册表实例清单（按实例幂等；注册表重置后需重新登记）。"""

_UNION_OPERATOR = "in"
"""可做真并集合并的操作符（同字段多个 `in` 合并值集合）。"""

_IN_OPERATOR = "in"
"""集合物化与大集合护栏针对的操作符（`in` 的值即「值集合」）。"""

_MATCH_WILDCARD = re.compile(r"^[A-Za-z0-9_%?\u4e00-\u9fff]+$")
"""写校验用 `like` 模式允许集（与配置期口径一致，另含 SQL 通配 `%` `_`）。"""


class RbacDataScope(DataScope):
    """RBAC 数据范围：快照规则 → 读条件 / 写校验。

    实现名 `rbac` 不在类上声明 `plugin_name`（避免「导入即自动登记」与工厂重名），登记经
    `RbacDataScopeFactory`。
    """

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置（读 `[data_scope].options` 的 `max_in_values`）。
        """
        self._max_in_values = data_scope_max_in_values(settings)

    @property
    def max_in_values(self) -> int:
        """单条 `in` 条件的值元素上限（<= 0 表示不限制）。

        Returns:
            int: 阈值。
        """
        return self._max_in_values

    def read_predicate(self) -> object:
        """读过滤条件（`ScopeCondition` 列表；None 表示不过滤）。

        Returns:
            object: 条件列表；无快照 / 豁免 / 无规则时为 None。
        """
        snapshot = get_current_permission_snapshot()
        if snapshot is None or snapshot.exempt or not snapshot.data_scopes:
            return None
        return self._conditions(snapshot)

    def allow_write(
        self,
        values: ConcurrentStableDict[str, object],
        *,
        scope_columns: ConcurrentStableDict[str, str] | None = None,
    ) -> bool:
        """写校验：待写值须落在授权范围内（未涉及的条件跳过）。

        Args:
            values: 待写入字段值（实体列名 → 值）。
            scope_columns: 数据源标识 → 实体列名（写入口声明；未声明时数据源维度条件一律拒绝，
                从严不放大可写范围）。

        Returns:
            bool: 允许为 True。
        """
        snapshot = get_current_permission_snapshot()
        if snapshot is None or snapshot.exempt or not snapshot.data_scopes:
            return True
        conditions = self._conditions(snapshot)
        if _denies_all(conditions):
            return False
        for condition in conditions:
            field = _condition_column(condition, scope_columns)
            if field is None:
                return False
            if field not in values:
                continue
            if not _matches_value(values.get(field), condition):
                return False
        return True

    def _conditions(self, snapshot: PermissionSnapshot) -> ConcurrentStableList[ScopeCondition]:
        """按字典类型分组求值并做并集 / 合取整理（末段过大集合护栏）。

        Args:
            snapshot: 权限快照。

        Returns:
            ConcurrentStableList[ScopeCondition]: 作用域条件列表（AND 合取）。
        """
        grouped: ConcurrentStableDict[str, ConcurrentStableList[ScopeCondition]] = ConcurrentStableDict()
        for row in snapshot.data_scopes:
            data_source_key = str(row.get("data_source_key", ""))
            raw_policy = row.get("policy_type")
            policy_type = raw_policy if isinstance(raw_policy, str) else None
            bucket = _bucket(grouped, data_source_key)
            bucket.update(self._resolve(data_source_key, policy_type, _config_rows(row.get("config"))))
        result: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
        for key in grouped:
            bucket = grouped.get(key)
            if bucket is None:  # pragma: no cover - 遍历期键必在
                continue
            result.update(_union(key, bucket))
        return self._reject_oversized(result)

    def _reject_oversized(
        self, conditions: ConcurrentStableList[ScopeCondition]
    ) -> ConcurrentStableList[ScopeCondition]:
        """大集合护栏：任一 `in` 条件元素数超阈即整体退化为永假并上报引导。

        两处调用：**单条规则求值后**（退化结果即进层2，后续请求不再重扫巨型值列表）与
        **并集合并后**（两条各自合规的同字段 `in` 合并后仍可能超阈）。

        Args:
            conditions: 规则求值结果或并集合并后的条件列表。

        Returns:
            ConcurrentStableList[ScopeCondition]: 原条件；超阈时为单条永假条件。
        """
        if self._max_in_values <= 0:
            return conditions
        for condition in conditions:
            if condition.operator != _IN_OPERATOR:
                continue
            size = len(cast("Sized", condition.value))
            if size <= self._max_in_values:
                continue
            current_permission_cache_store().record_oversized_rule()
            _logger.warning(
                "数据范围 `in` 值数 %s 超阈值 %s：该数据范围已退化为永假，请改用区域 / 匹配 / 扩展策略",
                size,
                self._max_in_values,
            )
            denied: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
            denied.add(DENY_ALL_CONDITION)
            return denied
        return conditions

    def _resolve(
        self,
        data_source_key: str,
        policy_type: str | None,
        rows: ConcurrentStableList[ConcurrentStableDict[str, object]],
    ) -> ConcurrentStableList[ScopeCondition]:
        """单条规则的求值结果（层2 命中即复用；未命中求值后回填）。

        键按「字典类型 + 策略 + `config` 内容指纹」计算、**不含用户**——同一规则被多个用户命中时只有
        一份结果（`04-3` 在此之上加引用计数、大集合 SQL 与内存指标）；指纹不可算时**不缓存**、直接求值。

        Args:
            data_source_key: 字典类型主键（字符串化）。
            policy_type: 策略类型；None / 未注册即不产生放行。
            rows: 该条规则的 `config` 行。

        Returns:
            ConcurrentStableList[ScopeCondition]: 该条规则的条件（非法规则为永假条件）。
        """
        if policy_type is None:
            return _deny_all("规则缺少策略类型")
        policy = scope_policy(policy_type)
        if policy is None:
            return _deny_all(f"策略未注册：{policy_type}")
        store = current_permission_cache_store()
        key = permission_rule_key(data_source_key=data_source_key, policy_type=policy_type, config=rows)
        if key is not None:
            cached = store.get_rule(source=RBAC_DATA_SCOPE_NAME, rule_key=key)
            if isinstance(cached, ConcurrentStableList):
                return cast("ConcurrentStableList[ScopeCondition]", cached)
        resolved = self._reject_oversized(_materialize(policy(data_source_key, rows)))
        if key is not None:
            store.set_rule(source=RBAC_DATA_SCOPE_NAME, rule_key=key, value=resolved, elements=_rule_weight(resolved))
        return resolved


def _deny_all(reason: str) -> ConcurrentStableList[ScopeCondition]:
    """构造「该条不产生放行」的永假条件并上报。

    Args:
        reason: 拒绝原因（入日志）。

    Returns:
        ConcurrentStableList[ScopeCondition]: 单条永假条件。
    """
    _logger.warning("数据范围规则不产生放行：%s", reason)
    current_permission_cache_store().record_invalid_rule()
    denied: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
    denied.add(DENY_ALL_CONDITION)
    return denied


def _materialize(conditions: ConcurrentStableList[ScopeCondition]) -> ConcurrentStableList[ScopeCondition]:
    """集合物化：把 `in` 条件的值去重为 `ConcurrentStableSet`（其余条件原样保留）。

    永假条件（`DENY_ALL_CONDITION`）按同一对象保留，供写校验以「是否含永假条件」判定。

    Args:
        conditions: 策略求值器产出的条件列表。

    Returns:
        ConcurrentStableList[ScopeCondition]: 物化后的条件列表。
    """
    materialized: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
    for condition in conditions:
        if condition == DENY_ALL_CONDITION or condition.operator != _IN_OPERATOR:
            materialized.add(condition)
            continue
        materialized.add(
            ScopeCondition(
                condition.field,
                _IN_OPERATOR,
                _value_members(condition.value),
                condition.data_source_key,
            )
        )
    return materialized


def _rule_weight(conditions: ConcurrentStableList[ScopeCondition]) -> int:
    """规则承载的**值元素总数**（`in` 集合大小 / `between` 计 2 / 标量计 1）。

    Args:
        conditions: 规则求值结果。

    Returns:
        int: 元素总数（层2 元素预算与内存度量的计量口径）。
    """
    total = 0
    for condition in conditions:
        total += len(cast("Sized", condition.value)) if _is_members(condition.value) else 1
    return total


def _is_members(value: object) -> bool:
    """值是否为「元素容器」（集合或序列；字符串 / 字节不算）。

    Args:
        value: 条件值。

    Returns:
        bool: 是元素容器为 True。
    """
    return isinstance(value, Set) or (isinstance(value, Sequence) and not isinstance(value, str | bytes))


def _value_members(value: object) -> ConcurrentStableSet[object]:
    """取条件值里的元素集合（非容器即空集）。

    Args:
        value: 条件值。

    Returns:
        ConcurrentStableSet[object]: 去重后的元素集合。
    """
    members: ConcurrentStableSet[object] = ConcurrentStableSet()
    if _is_members(value):
        for member in cast("Iterable[object]", value):
            members.add(member)
    return members


def _condition_column(condition: ScopeCondition, scope_columns: ConcurrentStableDict[str, str] | None) -> str | None:
    """把条件翻译到实体列名（数据源维度条件按声明的映射翻译）。

    Args:
        condition: 作用域条件。
        scope_columns: 数据源标识 → 实体列名（None 表示未声明）。

    Returns:
        str | None: 实体列名；数据源维度条件既无映射又无字段时返回 None（调用方按永假处置）。
    """
    data_source_key = condition.data_source_key
    if data_source_key is None:
        return condition.field
    mapped = None if scope_columns is None else scope_columns.get(data_source_key)
    if mapped is not None:
        return mapped
    if condition.field:
        return condition.field
    _logger.warning("数据范围规则不产生放行：数据源 %s 未声明实体列映射", data_source_key)
    current_permission_cache_store().record_invalid_rule()
    return None


def _denies_all(conditions: ConcurrentStableList[ScopeCondition]) -> bool:
    """条件列表是否含永假条件（「不产生放行」）。

    Args:
        conditions: 作用域条件列表。

    Returns:
        bool: 含永假条件为 True。
    """
    return any(condition == DENY_ALL_CONDITION for condition in conditions)


def _config_rows(raw: object) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """把规则行的 `config` 规整为保序映射列表。

    按 `Sequence` / `Mapping` **协议**判定（`StableJson` 读回的是基座集合类，不是内建 `list` / `dict`；
    与 `04_01` 实施记录 §3.4 同口径），避免真实链路规则被静默丢弃。

    Args:
        raw: 原始 `config`。

    Returns:
        ConcurrentStableList[ConcurrentStableDict[str, object]]: 规则行列表。
    """
    rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        return rows
    for item in cast("Sequence[object]", raw):
        if not isinstance(item, Mapping):
            continue
        stable: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        for key, value in cast("Mapping[object, object]", item).items():
            stable.set(str(key), value)
        rows.add(stable)
    return rows


def _bucket(
    grouped: ConcurrentStableDict[str, ConcurrentStableList[ScopeCondition]], data_source_key: str
) -> ConcurrentStableList[ScopeCondition]:
    """取（或新建）字典类型的条件桶。

    Args:
        grouped: 分组表。
        data_source_key: 字典类型主键（字符串化）。

    Returns:
        ConcurrentStableList[ScopeCondition]: 该字典类型的条件桶。
    """
    bucket = grouped.get(data_source_key)
    if bucket is None:
        created: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
        grouped.set(data_source_key, created)
        return created
    return bucket


def _union(data_source_key: str, bucket: ConcurrentStableList[ScopeCondition]) -> ConcurrentStableList[ScopeCondition]:
    """同字典类型内并集整理：同字段同操作符可合并（`in` 值集合并），否则退化合取并上报。

    Args:
        data_source_key: 字典类型主键（上报用）。
        bucket: 该字典类型的条件桶。

    Returns:
        ConcurrentStableList[ScopeCondition]: 整理后的条件。
    """
    if len(bucket) <= 1:
        return bucket
    fields = {item.field for item in bucket}
    operators = {item.operator for item in bucket}
    sources = {item.data_source_key for item in bucket}
    if len(fields) == 1 and len(sources) == 1 and operators == {_UNION_OPERATOR}:
        merged: ConcurrentStableSet[object] = ConcurrentStableSet()
        for item in bucket:
            merged.update(_value_members(item.value))
        field = next(iter(fields))
        source = next(iter(sources))
        result: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
        result.add(ScopeCondition(field, _UNION_OPERATOR, merged, source))
        return result
    _logger.warning("数据范围并集退化为合取（从严）：字典 %s，字段 %s，操作符 %s", data_source_key, fields, operators)
    return bucket


def _like_match(value: object, pattern: object) -> bool:
    """写校验用 LIKE 判定（`%` 任意串 / `_` 单字符；无通配按子串）。

    Args:
        value: 待写值。
        pattern: 模式。

    Returns:
        bool: 命中 True。
    """
    if not isinstance(value, str) or not isinstance(pattern, str):
        return False
    if _MATCH_WILDCARD.match(pattern) is None:
        return False
    if "%" not in pattern and "_" not in pattern:
        return pattern in value
    parts: ConcurrentStableList[str] = ConcurrentStableList()
    for char in pattern:
        if char == "%":
            parts.add(".*")
        elif char == "_":
            parts.add(".")
        else:
            parts.add(re.escape(char))
    return re.fullmatch("".join(parts), value) is not None


def _matches_value(value: object, condition: ScopeCondition) -> bool:
    """单个条件对「字段值」的判定（写校验用；类型不匹配即 False）。

    Args:
        value: 待写字段值。
        condition: 作用域条件。

    Returns:
        bool: 满足 True。
    """
    operator = condition.operator
    target = condition.value
    if operator == "is_null":
        return value is None
    if operator == "is_not_null":
        return value is not None
    if operator == "eq":
        return bool(value == target)
    if operator == "ne":
        return bool(value != target)
    if operator == "in":
        if _is_members(target):
            return any(value == member for member in cast("Iterable[object]", target))
        return False
    if operator == "like":
        return _like_match(value, target)
    if operator == "between":
        if not isinstance(target, list | tuple) or len(cast("Any", target)) != 2:
            return False
        low, high = cast("Any", target)
        try:
            return bool(cast("Any", value) >= low and cast("Any", value) <= high)
        except TypeError:
            return False
    try:
        if operator == "gt":
            return bool(cast("Any", value) > cast("Any", target))
        if operator == "gte":
            return bool(cast("Any", value) >= cast("Any", target))
        if operator == "lt":
            return bool(cast("Any", value) < cast("Any", target))
        if operator == "lte":
            return bool(cast("Any", value) <= cast("Any", target))
    except TypeError:
        return False
    return False


class RbacDataScopeFactory(BasePluginFactory[RbacDataScope]):
    """RBAC 数据范围工厂（装配期登记 `[data_scope].provider = "rbac"`）。"""

    plugin_key: str = "data_scope"
    plugin_name: str = RBAC_DATA_SCOPE_NAME

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置。必填（同仓工厂约定：零参工厂会被自动登记）。
        """
        self._settings = settings

    def create(self, options: object = None) -> RbacDataScope:
        """构造数据范围 provider。

        Args:
            options: 未使用。

        Returns:
            RbacDataScope: provider 实例。
        """
        del options
        return RbacDataScope(self._settings)


def register_rbac_data_scope(settings: Settings) -> None:
    """登记 RBAC 数据范围实现与四策略求值器（须在建注册表之前；按注册表实例幂等）。

    Args:
        settings: 应用配置。
    """
    registry = default_plugin_registry()
    if any(item is registry for item in _REGISTERED_REGISTRIES):
        return
    register_rbac_scope_policies()
    register_plugin("data_scope", RBAC_DATA_SCOPE_NAME, RbacDataScopeFactory(settings))
    _REGISTERED_REGISTRIES.add(registry)
