"""平台服务：数据范围四策略求值器（`select` / `region` / `match` / `extension`）。

口径（《02_04 详细设计》§5.6）：

| 策略 | `config` 行 | 读时条件 |
| --- | --- | --- |
| `select` | `{"field": 列, "values": [值…]}` | 该列 `IN (...)` |
| `region` | `{"field": 列, "start": 起, "end": 止}` | 该列 `BETWEEN 起 止` |
| `match` | `{"field": 列, "pattern": 通配}` | 该列 `LIKE`（`*`→`%`、`?`→`_`） |
| `extension` | `{"key": 扩展键, "params": {…}}` | 经扩展求值器（未注册即拒） |

**非法 / 未注册规则一律退化为「永假条件」**（`DENY_ALL_CONDITION`）——「该条不产生放行」，
确保不因规则异常或策略缺失而放大可见 / 可写范围；同时经 `logging` 上报，便于配置期排查。

越界拒绝的判定（运行期兜底，配置期另在 `02_03` 拦）：
- `region`：缺 `start` / `end`，或 `start > end`；
- `match`：通配符仅允许 `*` `?`，其余允许中英文 / 数字 / 下划线，出现其它字符即拒。
"""

from __future__ import annotations

import logging
import re
from typing import Any, cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.scope.base import ScopeCondition
from bms_core.scope.extensions import scope_extension_resolver
from bms_core.scope.policies import register_scope_policy

_logger = logging.getLogger(__name__)

POLICY_SELECT = "select"
POLICY_REGION = "region"
POLICY_MATCH = "match"
POLICY_EXTENSION = "extension"

DENY_ALL_CONDITION = ScopeCondition("id", "in", [])
"""永假条件（「该条不产生放行」的载体：`id ∈ ∅`）。"""

_MATCH_PATTERN = re.compile(r"^[A-Za-z0-9_*?\u4e00-\u9fff]+$")
"""`match` 模式允许集：中英文 / 数字 / 下划线 / `*` / `?`（越界即拒）。"""

_FIELD_CHARS = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
"""字段名允许集（防注入：仅标识符形态）。"""


def _deny(reason: str) -> ConcurrentStableList[ScopeCondition]:
    """构造「不产生放行」结果并上报。

    Args:
        reason: 拒绝原因（入日志）。

    Returns:
        ConcurrentStableList[ScopeCondition]: 单条永假条件。
    """
    _logger.warning("数据范围规则不产生放行：%s", reason)
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


def resolve_select(
    config: ConcurrentStableList[ConcurrentStableDict[str, object]],
) -> ConcurrentStableList[ScopeCondition]:
    """数据选择策略：勾选字典值集合 → 该列 `IN (...)`。

    Args:
        config: 规则行（`field` + `values`）。

    Returns:
        ConcurrentStableList[ScopeCondition]: 条件列表（空 `values` 即永假）。
    """
    conditions: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
    for row in config:
        field = _read_field(row)
        raw = cast("Any", row.get("values"))
        if field is None or not isinstance(raw, list | tuple):
            return _deny(f"select 规则非法：{dict(row)}")
        values: ConcurrentStableList[object] = ConcurrentStableList()
        for item in cast("Any", raw):
            values.add(item)
        if not values:
            return _deny(f"select 规则未勾选任何值：{field}")
        conditions.add(ScopeCondition(field, "in", list(values)))
    return conditions


def resolve_region(
    config: ConcurrentStableList[ConcurrentStableDict[str, object]],
) -> ConcurrentStableList[ScopeCondition]:
    """数据区域策略：开始 / 结束值 → 该列区间条件（起 > 止即拒）。

    Args:
        config: 规则行（`field` + `start` + `end`）。

    Returns:
        ConcurrentStableList[ScopeCondition]: 条件列表。
    """
    conditions: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
    for row in config:
        field = _read_field(row)
        start = row.get("start")
        end = row.get("end")
        if field is None or start is None or end is None:
            return _deny(f"region 规则缺项：{dict(row)}")
        try:
            invalid = cast("Any", start) > cast("Any", end)
        except TypeError:
            return _deny(f"region 规则起止不可比：{dict(row)}")
        if invalid:
            return _deny(f"region 规则起值大于止值：{field}")
        conditions.add(ScopeCondition(field, "between", (start, end)))
    return conditions


def resolve_match(
    config: ConcurrentStableList[ConcurrentStableDict[str, object]],
) -> ConcurrentStableList[ScopeCondition]:
    """数据匹配策略：字段 + 通配符 → `LIKE`（`*`→`%`、`?`→`_`；越界字符即拒）。

    Args:
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
        conditions.add(ScopeCondition(field, "like", pattern.replace("*", "%").replace("?", "_")))
    return conditions


def resolve_extension(
    config: ConcurrentStableList[ConcurrentStableDict[str, object]],
) -> ConcurrentStableList[ScopeCondition]:
    """扩展权限策略：逐行交扩展求值器（未注册 / 无求值器即拒）。

    Args:
        config: 规则行（`key` + 可选 `params`）。

    Returns:
        ConcurrentStableList[ScopeCondition]: 条件列表。
    """
    conditions: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
    for row in config:
        key = row.get("key")
        if not isinstance(key, str) or not key:
            return _deny(f"extension 规则缺 key：{dict(row)}")
        resolver = scope_extension_resolver(key)
        if resolver is None:
            return _deny(f"extension 未注册求值器：{key}")
        rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
        rows.add(row)
        resolved = resolver(rows)
        if not resolved:
            return _deny(f"extension 求值结果为空：{key}")
        conditions.update(resolved)
    return conditions


def register_scope_policies() -> None:
    """登记四策略求值器（装配期调用；后代可登记同名策略覆盖）。"""
    register_scope_policy(POLICY_SELECT, resolve_select)
    register_scope_policy(POLICY_REGION, resolve_region)
    register_scope_policy(POLICY_MATCH, resolve_match)
    register_scope_policy(POLICY_EXTENSION, resolve_extension)
