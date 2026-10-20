"""基座内建 RBAC 数据范围 provider（`[data_scope].provider = "rbac"`，域 `data_scope`）。

- **输入**：请求级权限快照的 `data_scopes`（`data_source_key` / `policy_type` / `config`，由引擎计算并缓存）；
- **读**：按 `policy_type` 经策略注册表求值（核心不判策略类型），同字典类型内多规则**并集**，
  跨字典类型**合取**；非法 / 未注册策略退化为永假（从严）；
- **写**：服务层写入口显式调 `allow_write(values)`——待写值须落在同一批条件内，失败拒（`30001`）；
- **豁免 / 未预加载**：不过滤、恒允许（由认证链与上层承担）；
- **租户边界**：条件不含 `tenant_id`；租户过滤由基座注入点 `BaseScopedRepository._tenant_condition`
  强制叠加（任何策略不得跨租户）。

本实现只消费基座快照与策略注册表，**不 import 任何服务包、不碰任何 ORM**，故落在共享基座；
四策略求值器见 `scope/policies_rbac.py`（由 `register_rbac_data_scope` 一并登记）。

**口径偏差（已登记）**：详设 §5.6 的「多策略结果 OR 合并」在本基座注入点（条件列表按 AND 合取）
下只可对**同字段**的并集做真合并（多 `IN` 合并为一个 `IN`）；不同字段 / 不同操作符的并集只能退化为
合取（从严），并上报——从严不越权，且业务维度通常单一字段。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.factory import BasePluginFactory
from bms_core.core.plugin import default_plugin_registry, register_plugin
from bms_core.permission.cache import current_permission_cache_store
from bms_core.permission.snapshot import PermissionSnapshot, get_current_permission_snapshot
from bms_core.permission.version import permission_rule_key
from bms_core.scope.base import DataScope, ScopeCondition
from bms_core.scope.policies import scope_policy
from bms_core.scope.policies_rbac import DENY_ALL_CONDITION, register_rbac_scope_policies

_logger = logging.getLogger(__name__)

RBAC_DATA_SCOPE_NAME = "rbac"
"""RBAC 数据范围实现名（`[data_scope].provider`）。"""

_REGISTERED_REGISTRIES: ConcurrentStableList[object] = ConcurrentStableList()
"""已登记 RBAC 数据范围的注册表实例清单（按实例幂等；注册表重置后需重新登记）。"""

_UNION_OPERATOR = "in"
"""可做真并集合并的操作符（同字段多个 `in` 合并值集合）。"""

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
            settings: 应用配置（预留：后代档位的数据范围选项）。
        """
        del settings

    def read_predicate(self) -> object:
        """读过滤条件（`ScopeCondition` 列表；None 表示不过滤）。

        Returns:
            object: 条件列表；无快照 / 豁免 / 无规则时为 None。
        """
        snapshot = get_current_permission_snapshot()
        if snapshot is None or snapshot.exempt or not snapshot.data_scopes:
            return None
        return self._conditions(snapshot)

    def allow_write(self, values: ConcurrentStableDict[str, object]) -> bool:
        """写校验：待写值须落在授权范围内（未涉及的条件跳过）。

        Args:
            values: 待写入字段值（字段名 → 值）。

        Returns:
            bool: 允许为 True。
        """
        snapshot = get_current_permission_snapshot()
        if snapshot is None or snapshot.exempt or not snapshot.data_scopes:
            return True
        for condition in self._conditions(snapshot):
            if condition.field not in values:
                continue
            if not _matches_value(values.get(condition.field), condition):
                return False
        return True

    def _conditions(self, snapshot: PermissionSnapshot) -> ConcurrentStableList[ScopeCondition]:
        """按字典类型分组求值并做并集 / 合取整理。

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
        return result

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
        resolved = policy(rows)
        if key is not None:
            store.set_rule(source=RBAC_DATA_SCOPE_NAME, rule_key=key, value=resolved)
        return resolved


def _deny_all(reason: str) -> ConcurrentStableList[ScopeCondition]:
    """构造「该条不产生放行」的永假条件并上报。

    Args:
        reason: 拒绝原因（入日志）。

    Returns:
        ConcurrentStableList[ScopeCondition]: 单条永假条件。
    """
    _logger.warning("数据范围规则不产生放行：%s", reason)
    denied: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
    denied.add(DENY_ALL_CONDITION)
    return denied


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
    if len(fields) == 1 and operators == {_UNION_OPERATOR}:
        merged: ConcurrentStableList[object] = ConcurrentStableList()
        for item in bucket:
            raw = cast("Any", item.value)
            if isinstance(raw, list | tuple):
                for member in cast("Any", raw):
                    merged.add(member)
        field = next(iter(fields))
        result: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
        result.add(ScopeCondition(field, _UNION_OPERATOR, list(merged)))
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
        if isinstance(target, list | tuple | set | frozenset):
            return any(value == member for member in cast("Any", target))
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
