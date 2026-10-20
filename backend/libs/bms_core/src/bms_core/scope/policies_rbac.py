"""数据范围四策略求值器（域 `data_scope`，`rbac` 实现内置）。

口径（`04-4` 按《数据库设计 · sys_data_scope》表文件收口，`config` 结构与条件语义一一对齐）：

| 策略 | `config` 行（事实源口径） | 读时条件 |
| --- | --- | --- |
| `select` | `{"item_code": 条目 value}` | 数据源维度 `in`（值集合；`field` 留空） |
| `region` | `{"start": 起, "end": 止}` | 数据源维度 `between`（起 ≤ 止；`field` 留空） |
| `match` | `{"field": 白名单字段, "pattern": 通配}` | `like`（`*`→`%`、`?`→`_`；带数据源标识） |
| `extension` | `{"key": 扩展键, "params": {…}}` | 经扩展求值器（未注册即拒）直接返回的条件集合 |

**数据源维度**：前三者的条件都带 `ScopeCondition.data_source_key`，消费方按自身声明的
「数据源 → 实体列」映射翻译成列条件；`match` 另带配置里的白名单字段（映射存在时以映射为准）。

**非法 / 未注册规则一律退化为「永假条件」**（`DENY_ALL_CONDITION`）——「该条不产生放行」，
确保不因规则异常或策略缺失而放大可见 / 可写范围；同时经 `logging` 上报并累加非法规则计数。

越界拒绝的判定（运行期兜底，配置期另在角色管理侧拦）：
- `select`：`item_code` 缺失（兼容 `itemCode`）/ 非字符串 / 空串；
- `region`：缺 `start` / `end`，或 `start > end`，或起止不可比；
- `match`：`field` 非标识符形态；通配符仅允许 `*` `?`，其余允许中英文 / 数字 / 下划线；
- `extension`：缺 `key`、未注册求值器、求值结果为空。
"""

from __future__ import annotations

import logging
import re
from typing import Any, cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.permission.cache import current_permission_cache_store
from bms_core.scope.base import DENY_ALL_CONDITION, ScopeCondition
from bms_core.scope.extensions import scope_extension_resolver
from bms_core.scope.policies import register_scope_policy

__all__ = [
    "DENY_ALL_CONDITION",
    "POLICY_EXTENSION",
    "POLICY_MATCH",
    "POLICY_REGION",
    "POLICY_SELECT",
    "register_rbac_scope_policies",
    "resolve_extension",
    "resolve_match",
    "resolve_region",
    "resolve_select",
]

_logger = logging.getLogger(__name__)

POLICY_SELECT = "select"
POLICY_REGION = "region"
POLICY_MATCH = "match"
POLICY_EXTENSION = "extension"

_RowList = ConcurrentStableList[ConcurrentStableDict[str, object]]
"""规则行列表（`config` 规整后的形态）。"""

_ItemCode = str
"""字典项取值（条目 `value`，字符串）。"""

_MATCH_PATTERN = re.compile(r"^[A-Za-z0-9_*?\u4e00-\u9fff]+$")
"""`match` 模式允许集：中英文 / 数字 / 下划线 / `*` / `?`（越界即拒）。"""

_FIELD_CHARS = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
"""字段名允许集（防注入：仅标识符形态）。"""


def _deny(reason: str) -> ConcurrentStableList[ScopeCondition]:
    """构造「不产生放行」结果并上报（记日志 + 计数非法规则）。

    Args:
        reason: 拒绝原因（入日志）。

    Returns:
        ConcurrentStableList[ScopeCondition]: 单条永假条件。
    """
    _logger.warning("数据范围规则不产生放行：%s", reason)
    current_permission_cache_store().record_invalid_rule()
    result: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
    result.add(DENY_ALL_CONDITION)
    return result


def _read_field(row: ConcurrentStableDict[str, object]) -> str | None:
    """取规则行里的字段名（非标识符形态即拒）。

    Args:
        row: 规则行。

    Returns:
        str | None: 字段名；非法为 None。
    """
    raw = row.get("field")
    if not isinstance(raw, str) or not _FIELD_CHARS.match(raw):
        return None
    return raw


def _read_item_code(row: ConcurrentStableDict[str, object]) -> _ItemCode | None:
    """取勾选值（表文件键 `item_code`，兼容前端历史键 `itemCode`）。

    Args:
        row: 规则行。

    Returns:
        str | None: 非空字符串为取值；缺失 / 类型不符 / 空串为 None。
    """
    for key in ("item_code", "itemCode"):
        raw = row.get(key)
        if isinstance(raw, str) and raw:
            return raw
    return None


def resolve_select(data_source_key: str, config: _RowList) -> ConcurrentStableList[ScopeCondition]:
    """数据选择策略：勾选字典项取值 → 数据源维度 `in` 集合。

    Args:
        data_source_key: 数据源标识（条件所属数据源）。
        config: 规则行（`item_code`，兼容 `itemCode`）。

    Returns:
        ConcurrentStableList[ScopeCondition]: 条件列表（任一行非法或全空即永假）。
    """
    values: ConcurrentStableSet[object] = ConcurrentStableSet()
    for row in config:
        item = _read_item_code(row)
        if item is None:
            return _deny(f"select 规则非法（缺 item_code 或非字符串）：{dict(row)}")
        values.add(item)
    if not values:
        return _deny(f"select 规则未勾选任何值：{data_source_key}")
    conditions: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
    conditions.add(ScopeCondition("", "in", values, data_source_key))
    return conditions


def resolve_region(data_source_key: str, config: _RowList) -> ConcurrentStableList[ScopeCondition]:
    """数据区域策略：开始 / 结束值 → 数据源维度区间条件（起 > 止即拒）。

    Args:
        data_source_key: 数据源标识（条件所属数据源）。
        config: 规则行（`start` + `end`）。

    Returns:
        ConcurrentStableList[ScopeCondition]: 条件列表。
    """
    conditions: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
    for row in config:
        start = row.get("start")
        end = row.get("end")
        if start is None or end is None:
            return _deny(f"region 规则缺项：{dict(row)}")
        try:
            invalid = cast("Any", start) > cast("Any", end)
        except TypeError:
            return _deny(f"region 规则起止不可比：{dict(row)}")
        if invalid:
            return _deny(f"region 规则起值大于止值：{data_source_key}")
        conditions.add(ScopeCondition("", "between", (start, end), data_source_key))
    return conditions


def resolve_match(data_source_key: str, config: _RowList) -> ConcurrentStableList[ScopeCondition]:
    """数据匹配策略：白名单字段 + 通配符 → `LIKE`（`*`→`%`、`?`→`_`；越界字符即拒）。

    Args:
        data_source_key: 数据源标识（条件所属数据源）。
        config: 规则行（`field` + `pattern`）。

    Returns:
        ConcurrentStableList[ScopeCondition]: 条件列表。
    """
    conditions: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
    for row in config:
        field = _read_field(row)
        pattern = row.get("pattern")
        if field is None or not isinstance(pattern, str) or not pattern:
            return _deny(f"match 规则缺项：{dict(row)}")
        if _MATCH_PATTERN.match(pattern) is None:
            return _deny(f"match 通配符越界：{pattern}")
        conditions.add(ScopeCondition(field, "like", pattern.replace("*", "%").replace("?", "_"), data_source_key))
    return conditions


def resolve_extension(data_source_key: str, config: _RowList) -> ConcurrentStableList[ScopeCondition]:
    """扩展权限策略：同一 `key` 的配置行聚合后交扩展求值器（未注册 / 空结果即拒）。

    Args:
        data_source_key: 数据源标识（条件所属数据源）。
        config: 规则行（`key` + 可选 `params`）。

    Returns:
        ConcurrentStableList[ScopeCondition]: 条件列表。
    """
    grouped: ConcurrentStableDict[str, _RowList] = ConcurrentStableDict()
    for row in config:
        key = row.get("key")
        if not isinstance(key, str) or not key:
            return _deny(f"extension 规则缺 key：{dict(row)}")
        bucket = grouped.get(key)
        if bucket is None:
            created: _RowList = ConcurrentStableList()
            grouped.set(key, created)
            bucket = created
        bucket.add(row)
    conditions: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
    for key in grouped:
        rows = grouped.get(key)
        if rows is None:  # pragma: no cover - 遍历期键必在
            continue
        resolver = scope_extension_resolver(key)
        if resolver is None:
            return _deny(f"extension 未注册求值器：{key}")
        resolved = resolver(data_source_key, rows)
        if not resolved:
            return _deny(f"extension 求值结果为空：{key}")
        conditions.update(resolved)
    return conditions


def register_rbac_scope_policies() -> None:
    """登记四策略求值器（`rbac` 数据范围实现内置；后代可登记同名策略覆盖）。"""
    register_scope_policy(POLICY_SELECT, resolve_select)
    register_scope_policy(POLICY_REGION, resolve_region)
    register_scope_policy(POLICY_MATCH, resolve_match)
    register_scope_policy(POLICY_EXTENSION, resolve_extension)
