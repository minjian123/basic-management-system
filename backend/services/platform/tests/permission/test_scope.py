"""数据范围用例（`02_04`）：四策略条件生成 + 并集兜底 + 写校验 + 越界拒绝 + 豁免。

口径见《02_04 详细设计》§5.6：`select` / `region` / `match` / `extension` 四策略经**策略注册表**
求值（核心不判策略类型）；非法 / 未注册规则**退化为永假**（该条不产生放行）；同字典类型内多 `IN`
合并为一条（真并集），不同字段则合取（从严）；豁免 / 无快照不过滤、恒允许。
"""

from collections.abc import Iterator

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.context import current_user_id
from bms_core.permission.snapshot import (
    TIER_STANDARD,
    TIER_SYSTEM_ADMIN,
    PermissionSnapshot,
    set_current_permission_snapshot,
)
from bms_core.scope.base import ScopeCondition
from bms_core.scope.extensions import (
    DataScopeExtensionInfo,
    register_data_scope_extension,
    register_scope_extension_resolver,
    reset_data_scope_extensions,
    reset_scope_extension_resolvers,
)
from bms_platform.scope.policies import DENY_ALL_CONDITION, register_scope_policies
from bms_platform.scope.rbac import RbacDataScope

_FORM = "\u884c\u653f\u533a\u57df"


@pytest.fixture(autouse=True)
def clean_scope() -> Iterator[None]:
    """每例前后重置快照与扩展求值器（策略为进程级登记，需按需重放）。

    Yields:
        None: 用例运行期。
    """
    set_current_permission_snapshot(None)
    reset_scope_extension_resolvers()
    reset_data_scope_extensions()
    register_scope_policies()
    yield
    set_current_permission_snapshot(None)
    reset_scope_extension_resolvers()
    reset_data_scope_extensions()
    current_user_id.set(None)


def _provider() -> RbacDataScope:
    """构造数据范围 provider（本用例不依赖配置项）。

    Returns:
        RbacDataScope: provider 实例。
    """
    return RbacDataScope(Settings())


def _rule(
    dict_type_id: int, policy_type: str, config: ConcurrentStableList[object]
) -> ConcurrentStableDict[str, object]:
    """构造一条数据范围规则（快照载荷行）。

    Args:
        dict_type_id: 字典类型主键。
        policy_type: 策略类型。
        config: 策略配置行。

    Returns:
        ConcurrentStableDict[str, object]: 规则行。
    """
    row: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    row.set("dict_type_id", dict_type_id)
    row.set("policy_type", policy_type)
    row.set("config", list(config))
    return row


def _rows(*items: ConcurrentStableDict[str, object]) -> ConcurrentStableList[object]:
    """把配置项收集为列表。

    Args:
        items: 配置项。

    Returns:
        ConcurrentStableList[object]: 配置列表。
    """
    result: ConcurrentStableList[object] = ConcurrentStableList()
    for item in items:
        result.add(dict(item))
    return result


def _config(**kwargs: object) -> ConcurrentStableDict[str, object]:
    """构造一条策略配置行。

    Args:
        kwargs: 键值对。

    Returns:
        ConcurrentStableDict[str, object]: 配置行。
    """
    row: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    for key, value in kwargs.items():
        row.set(key, value)
    return row


def _snapshot(*rules: ConcurrentStableDict[str, object], tier: str = TIER_STANDARD) -> PermissionSnapshot:
    """构造带数据范围规则的快照。

    Args:
        rules: 规则行。
        tier: 主体层级。

    Returns:
        PermissionSnapshot: 快照。
    """
    collected: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    for rule in rules:
        collected.add(rule)
    return PermissionSnapshot(tier=tier, data_scopes=collected)


def test_four_policies_generate_conditions() -> None:
    """四策略条件生成：`select` → `in`、`region` → `between`、`match` → `like`（`*`→`%`）。"""
    match_rows = _rows(_config(field="code", pattern="BJ*"))
    extension_rows = _rows(_config(key="dept_subtree"))
    register_data_scope_extension(
        DataScopeExtensionInfo(key="dept_subtree", label="\u672c\u90e8\u95e8\u53ca\u4e0b\u7ea7")
    )
    register_scope_extension_resolver("dept_subtree", lambda rows: _cond_list(ScopeCondition("dept_id", "in", [1, 2])))
    select_rows = _rows(_config(field="area_code", values=["13"]))
    region_rows = _rows(_config(field="area_code", start="110000", end="119999"))
    snapshot = _snapshot(
        _rule(1, "select", select_rows),
        _rule(2, "region", region_rows),
        _rule(3, "match", match_rows),
        _rule(4, "extension", extension_rows),
    )
    set_current_permission_snapshot(snapshot)
    predicate = _provider().read_predicate()
    conditions = _as_conditions(predicate)
    assert [item.operator for item in conditions] == ["in", "between", "like", "in"]
    assert conditions[0].value == ["13"]
    assert conditions[1].value == ("110000", "119999")
    assert conditions[2].value == "BJ%"
    assert conditions[3].field == "dept_id"


def test_same_field_in_conditions_merge_as_union() -> None:
    """并集兜底：同字典类型同字段的多个 `IN` 合并为一条（真并集）。"""
    first = _rows(_config(field="area_code", values=["13", "14"]))
    second = _rows(_config(field="area_code", values=["15"]))
    set_current_permission_snapshot(_snapshot(_rule(1, "select", first), _rule(1, "select", second)))
    conditions = _as_conditions(_provider().read_predicate())
    assert len(conditions) == 1
    assert conditions[0].operator == "in"
    assert sorted(conditions[0].value) == ["13", "14", "15"]


def test_illegal_and_unregistered_rules_deny_all() -> None:
    """越界 / 未注册规则退化为永假：region 起大于止、match 通配符越界、策略未注册、扩展未注册。"""
    bad_region = _rows(_config(field="area_code", start="119999", end="110000"))
    bad_match = _rows(_config(field="code", pattern="BJ;drop"))
    set_current_permission_snapshot(_snapshot(_rule(1, "region", bad_region)))
    assert _as_conditions(_provider().read_predicate()) == [DENY_ALL_CONDITION]
    set_current_permission_snapshot(_snapshot(_rule(2, "match", bad_match)))
    assert _as_conditions(_provider().read_predicate()) == [DENY_ALL_CONDITION]
    set_current_permission_snapshot(_snapshot(_rule(3, "nope", _rows(_config(field="x")))))
    assert _as_conditions(_provider().read_predicate()) == [DENY_ALL_CONDITION]
    set_current_permission_snapshot(_snapshot(_rule(4, "extension", _rows(_config(key="unknown_ext")))))
    assert _as_conditions(_provider().read_predicate()) == [DENY_ALL_CONDITION]


def test_allow_write_rejects_out_of_scope_values() -> None:
    """写校验：范围内的值放行、越界值拒、未涉及字段跳过。"""
    rows = _rows(_config(field="area_code", values=["13"]))
    set_current_permission_snapshot(_snapshot(_rule(1, "select", rows)))
    provider = _provider()
    inside: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    inside.set("area_code", "13")
    outside: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    outside.set("area_code", "14")
    untouched: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    untouched.set("name", "\u6539\u540d")
    assert provider.allow_write(inside) is True
    assert provider.allow_write(outside) is False
    assert provider.allow_write(untouched) is True


def test_exempt_and_absent_snapshot_do_not_filter() -> None:
    """豁免层级与未预加载：不过滤、恒允许（由认证链与上层承担）。"""
    rows = _rows(_config(field="area_code", values=["13"]))
    set_current_permission_snapshot(_snapshot(_rule(1, "select", rows), tier=TIER_SYSTEM_ADMIN))
    provider = _provider()
    assert provider.read_predicate() is None
    values: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    values.set("area_code", "99")
    assert provider.allow_write(values) is True
    set_current_permission_snapshot(None)
    assert provider.read_predicate() is None
    assert provider.allow_write(values) is True


def _cond_list(*items: ScopeCondition) -> ConcurrentStableList[ScopeCondition]:
    """收集条件为列表（扩展求值器测试替身用）。

    Args:
        items: 条件。

    Returns:
        ConcurrentStableList[ScopeCondition]: 条件列表。
    """
    result: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
    for item in items:
        result.add(item)
    return result


def _as_conditions(predicate: object) -> ConcurrentStableList[ScopeCondition]:
    """把 `read_predicate()` 结果规整为条件列表。

    Args:
        predicate: 读过滤条件。

    Returns:
        ConcurrentStableList[ScopeCondition]: 条件列表。
    """
    result: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
    if isinstance(predicate, ConcurrentStableList):
        for item in predicate:
            if isinstance(item, ScopeCondition):
                result.add(item)
    if isinstance(predicate, ScopeCondition):
        result.add(predicate)
    return result
