"""数据范围四策略与 provider 用例（`04_4` 口径收口）：数据源维度条件 + 并集兜底 + 读写校验 + 永假上报。

口径见《04_4 详细设计》§5.3 / §5.4：

1. **`config` 按表文件**：`select` 行 `item_code`（兼容 `itemCode`）、`region` 行 `start` / `end`、
   `match` 行 `field` + `pattern`、`extension` 行 `key` + `params`；
2. **数据源维度条件**：`select` / `region` 的 `field` 留空、带 `data_source_key`；`match` 另带白名单字段；
3. **非法 / 未注册规则**：退化为永假（该条不产生放行）+ 日志 + `invalid_rule_rejections` 计数；
4. **并集**：同数据源 + 同字段 + 同操作符的 `in` 合并为一条，其余退化合取并上报；
5. **写校验**：按 `scope_columns` 把数据源维度条件翻译到列，未声明即拒；永假即拒。
"""

from collections.abc import Iterator
from typing import Any, cast

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.context import current_user_id
from bms_core.permission.cache import current_permission_cache_store, reset_permission_cache_store
from bms_core.permission.snapshot import (
    TIER_STANDARD,
    TIER_SYSTEM_ADMIN,
    PermissionSnapshot,
    set_current_permission_snapshot,
)
from bms_core.scope.base import DENY_ALL_CONDITION, ScopeCondition
from bms_core.scope.extensions import (
    DataScopeExtensionInfo,
    register_data_scope_extension,
    register_scope_extension_resolver,
    reset_data_scope_extensions,
    reset_scope_extension_resolvers,
)
from bms_core.scope.limits import DEFAULT_MAX_IN_VALUES, OPTION_MAX_IN_VALUES, data_scope_max_in_values
from bms_core.scope.policies import register_scope_policy
from bms_core.scope.policies_rbac import (
    register_rbac_scope_policies,
    resolve_extension,
    resolve_match,
    resolve_region,
    resolve_select,
)
from bms_core.scope.rbac import (
    RbacDataScope,
    RbacDataScopeFactory,
    _condition_column,  # pyright: ignore[reportPrivateUsage]
    _like_match,  # pyright: ignore[reportPrivateUsage]
    _matches_value,  # pyright: ignore[reportPrivateUsage]
    _union,  # pyright: ignore[reportPrivateUsage]
    _value_members,  # pyright: ignore[reportPrivateUsage]
    register_rbac_data_scope,
)

_ROWS = ConcurrentStableList[ConcurrentStableDict[str, object]]
"""规则行列表类型（与本模块策略签名一致）。"""


@pytest.fixture(autouse=True)
def clean_scope() -> Iterator[None]:
    """每例前后重置快照、扩展求值器与进程级缓存仓（策略为进程级登记，需按需重放）。

    Yields:
        None: 用例运行期。
    """
    set_current_permission_snapshot(None)
    reset_scope_extension_resolvers()
    reset_data_scope_extensions()
    reset_permission_cache_store()
    register_rbac_scope_policies()
    yield
    set_current_permission_snapshot(None)
    reset_scope_extension_resolvers()
    reset_data_scope_extensions()
    reset_permission_cache_store()
    current_user_id.set(None)


def _provider() -> RbacDataScope:
    """构造数据范围 provider（缺省阈值）。

    Returns:
        RbacDataScope: provider 实例。
    """
    return RbacDataScope(Settings())


def _with_threshold(threshold: int) -> Settings:
    """构造带阈值的应用配置。

    Args:
        threshold: `[data_scope].options.max_in_values`。

    Returns:
        Settings: 应用配置。
    """
    settings = Settings()
    settings.data_scope.options.set(OPTION_MAX_IN_VALUES, threshold)
    return settings


def _rule(
    data_source_key: str, policy_type: str, config: ConcurrentStableList[object]
) -> ConcurrentStableDict[str, object]:
    """构造一条数据范围规则（快照载荷行）。

    Args:
        data_source_key: 数据源标识。
        policy_type: 策略类型。
        config: 策略配置行。

    Returns:
        ConcurrentStableDict[str, object]: 规则行。
    """
    row: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    row.set("data_source_key", data_source_key)
    row.set("policy_type", policy_type)
    row.set("config", list(config))
    return row


def _rows(*items: ConcurrentStableDict[str, object]) -> ConcurrentStableList[object]:
    """把配置项收集为列表（内建 dict 形态，与 JSON 读回等价）。

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


def _config_list(*rows: ConcurrentStableDict[str, object]) -> _ROWS:
    """把配置行收成基座集合类列表（策略求值器入参形态）。

    Args:
        *rows: 配置行。

    Returns:
        _ROWS: 配置行列表。
    """
    collected: _ROWS = ConcurrentStableList()
    for row in rows:
        collected.add(row)
    return collected


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


def _conditions(predicate: object) -> ConcurrentStableList[ScopeCondition]:
    """把 `read_predicate()` 结果规整为条件列表。

    Args:
        predicate: 读过滤条件。

    Returns:
        ConcurrentStableList[ScopeCondition]: 条件列表。
    """
    result: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
    if isinstance(predicate, ConcurrentStableList):
        for item in cast("Any", predicate):
            if isinstance(item, ScopeCondition):
                result.add(item)
    if isinstance(predicate, ScopeCondition):
        result.add(predicate)
    return result


def _values(*items: object) -> ConcurrentStableDict[str, object]:
    """构造写校验待写值。

    Args:
        items: 键值对（`列名` / 值 交替）。

    Returns:
        ConcurrentStableDict[str, object]: 待写值。
    """
    result: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    for index in range(0, len(items), 2):
        result.set(str(items[index]), items[index + 1])
    return result


@pytest.mark.kiwi_id(2324)
def test_select_yields_data_source_dimension_in_set() -> None:
    """`select`：`item_code`（兼容 `itemCode`）去重为数据源维度 `in` 集合，`field` 留空。"""
    config = _config_list(_config(item_code="13"), _config(itemCode="13"), _config(item_code="14"))
    conditions = resolve_select("org_dept", config)
    assert len(conditions) == 1
    condition = next(iter(conditions))
    assert (condition.field, condition.operator, condition.data_source_key) == ("", "in", "org_dept")
    assert set(cast("Any", condition.value)) == {"13", "14"}


@pytest.mark.kiwi_id(2324)
def test_select_denies_missing_or_non_string_item_code_and_empty() -> None:
    """`select`：缺 `item_code` / 含非字符串 / 未勾选任何值 → 永假。"""
    assert resolve_select("k", _config_list(_config(field="code"))) == [DENY_ALL_CONDITION]
    assert resolve_select("k", _config_list(_config(item_code=13))) == [DENY_ALL_CONDITION]
    assert resolve_select("k", _config_list(_config(item_code=""))) == [DENY_ALL_CONDITION]
    assert resolve_select("k", _config_list()) == [DENY_ALL_CONDITION]


@pytest.mark.kiwi_id(2324)
def test_region_yields_between_without_field() -> None:
    """`region`：`start` / `end` → 数据源维度 `between`（`field` 留空、不枚举）。"""
    conditions = resolve_region("area", _config_list(_config(start="110000", end="119999")))
    condition = next(iter(conditions))
    assert (condition.field, condition.operator, condition.value, condition.data_source_key) == (
        "",
        "between",
        ("110000", "119999"),
        "area",
    )


@pytest.mark.kiwi_id(2324)
def test_region_denies_missing_incomparable_and_inverted() -> None:
    """`region`：缺起止 / 起止不可比 / 起 > 止 → 永假。"""
    assert resolve_region("k", _config_list(_config(start="a"))) == [DENY_ALL_CONDITION]
    assert resolve_region("k", _config_list(_config(start="a", end=1))) == [DENY_ALL_CONDITION]
    assert resolve_region("k", _config_list(_config(start="119999", end="110000"))) == [DENY_ALL_CONDITION]


@pytest.mark.kiwi_id(2324)
def test_match_keeps_whitelist_field_and_carries_data_source() -> None:
    """`match`：保留白名单字段与 `like` 值转换，条件带数据源标识。"""
    conditions = resolve_match("org_dept", _config_list(_config(field="code", pattern="BJ*?")))
    condition = next(iter(conditions))
    assert (condition.field, condition.operator, condition.value, condition.data_source_key) == (
        "code",
        "like",
        "BJ%_",
        "org_dept",
    )


@pytest.mark.kiwi_id(2324)
def test_match_denies_missing_or_illegal_rows() -> None:
    """`match`：字段非法 / `pattern` 非字符串 / 空串 / 通配符越界 → 永假。"""
    assert resolve_match("k", _config_list(_config(pattern="a*"))) == [DENY_ALL_CONDITION]
    assert resolve_match("k", _config_list(_config(field="1bad", pattern="a*"))) == [DENY_ALL_CONDITION]
    assert resolve_match("k", _config_list(_config(field="code", pattern=1))) == [DENY_ALL_CONDITION]
    assert resolve_match("k", _config_list(_config(field="code", pattern=""))) == [DENY_ALL_CONDITION]
    assert resolve_match("k", _config_list(_config(field="code", pattern="a;drop"))) == [DENY_ALL_CONDITION]


@pytest.mark.kiwi_id(2324)
def test_extension_aggregates_all_rows_of_one_key() -> None:
    """`extension`：同一 `key` 的多行聚合一次调用，求值器直接返回条件集合。"""
    calls: ConcurrentStableList[tuple[str, int]] = ConcurrentStableList()
    register_data_scope_extension(DataScopeExtensionInfo(key="dept_subtree", label="本部门及下级"))

    def _resolver(ds: str, rows: _ROWS) -> ConcurrentStableList[ScopeCondition]:
        """扩展求值器替身（记录调用入参，返回固定条件）。

        Args:
            ds: 数据源标识。
            rows: 该 key 的配置行。

        Returns:
            ConcurrentStableList[ScopeCondition]: 条件列表。
        """
        calls.add((ds, len(rows)))
        result: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
        result.add(ScopeCondition("dept_id", "in", [1, 2]))
        return result

    register_scope_extension_resolver("dept_subtree", _resolver)
    config = _config_list(_config(key="dept_subtree", params={"a": 1}), _config(key="dept_subtree", params={"b": 2}))
    conditions = resolve_extension("org_dept", config)
    assert [(item.field, item.operator) for item in conditions] == [("dept_id", "in")]
    assert len(calls) == 1
    assert calls[0] == ("org_dept", 2)


@pytest.mark.kiwi_id(2324)
def test_extension_denies_missing_key_unregistered_and_empty_result() -> None:
    """`extension`：缺 `key` / `key` 非字符串 / 未注册求值器 / 求值结果为空 → 永假。"""
    assert resolve_extension("k", _config_list(_config(params={}))) == [DENY_ALL_CONDITION]
    assert resolve_extension("k", _config_list(_config(key=1))) == [DENY_ALL_CONDITION]
    assert resolve_extension("k", _config_list(_config(key="missing"))) == [DENY_ALL_CONDITION]

    def _empty(ds: str, rows: _ROWS) -> ConcurrentStableList[ScopeCondition]:
        """空结果求值器（覆盖「返回空即永假」分支）。

        Args:
            ds: 数据源标识（忽略）。
            rows: 配置行（忽略）。

        Returns:
            ConcurrentStableList[ScopeCondition]: 空列表。
        """
        del ds, rows
        return ConcurrentStableList()

    register_scope_extension_resolver("empty_ext", _empty)
    assert resolve_extension("k", _config_list(_config(key="empty_ext"))) == [DENY_ALL_CONDITION]


@pytest.mark.kiwi_id(2324)
def test_four_policies_produce_conditions_through_provider() -> None:
    """四策略并集：`select` → `in`、`region` → `between`、`match` → `like`、`extension` → 自有条件。"""
    register_scope_extension_resolver("dept_subtree", lambda ds, _rows_arg: _ext_conditions(ds))
    register_data_scope_extension(DataScopeExtensionInfo(key="dept_subtree", label="本部门及下级"))
    snapshot = _snapshot(
        _rule("org_dept", "select", _rows(_config(item_code="13"))),
        _rule("area", "region", _rows(_config(start="110000", end="119999"))),
        _rule("role", "match", _rows(_config(field="code", pattern="BJ*"))),
        _rule("post", "extension", _rows(_config(key="dept_subtree"))),
    )
    set_current_permission_snapshot(snapshot)
    conditions = _conditions(_provider().read_predicate())
    assert [item.operator for item in conditions] == ["in", "between", "like", "in"]
    assert set(cast("Any", conditions[0].value)) == {"13"}
    assert conditions[1].value == ("110000", "119999")
    assert conditions[2].value == "BJ%"
    assert conditions[3].field == "dept_id"


def _ext_conditions(data_source_key: str) -> ConcurrentStableList[ScopeCondition]:
    """构造扩展求值结果（测试替身）。

    Args:
        data_source_key: 数据源标识（并入条件）。

    Returns:
        ConcurrentStableList[ScopeCondition]: 单条条件。
    """
    result: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
    result.add(ScopeCondition("dept_id", "in", [1, 2], data_source_key))
    return result


@pytest.mark.kiwi_id(2324)
def test_same_source_in_conditions_merge_as_union() -> None:
    """并集兜底：同数据源同字段的多个 `in` 合并为一条（真并集）。"""
    first = _rows(_config(item_code="13"), _config(item_code="14"))
    second = _rows(_config(item_code="15"))
    set_current_permission_snapshot(_snapshot(_rule("org_dept", "select", first), _rule("org_dept", "select", second)))
    conditions = _conditions(_provider().read_predicate())
    assert len(conditions) == 1
    assert conditions[0].operator == "in"
    assert sorted(cast("Any", conditions[0].value)) == ["13", "14", "15"]
    assert conditions[0].data_source_key == "org_dept"


def test_union_falls_back_when_field_or_source_differs() -> None:
    """并集整理：字段不同 / 数据源不同 → 退化为合取（从严）。"""
    merged = _union(
        "k",
        ConcurrentStableList(
            [
                ScopeCondition("", "in", ["1"], "org_dept"),
                ScopeCondition("code", "in", ["2"], "org_dept"),
            ]
        ),
    )
    assert [(item.field, item.operator) for item in merged] == [("", "in"), ("code", "in")]

    crossed = _union(
        "k",
        ConcurrentStableList(
            [
                ScopeCondition("", "in", ["1"], "org_dept"),
                ScopeCondition("", "in", ["2"], "org_user"),
            ]
        ),
    )
    assert [item.data_source_key for item in crossed] == ["org_dept", "org_user"]

    single = _union("k", ConcurrentStableList([ScopeCondition("", "in", ["1"], "org_dept")]))
    assert [item.field for item in single] == [""]

    assert list(_value_members("not-a-container")) == []


@pytest.mark.kiwi_id(2324)
def test_illegal_rules_increment_invalid_counter(caplog: pytest.LogCaptureFixture) -> None:
    """非法规则：永假 + warning + `invalid_rule_rejections` 计数；快照重置后计数不丢。"""
    set_current_permission_snapshot(_snapshot(_rule("k", "select", _rows(_config(field="code")))))
    with caplog.at_level("WARNING"):
        assert _conditions(_provider().read_predicate()) == [DENY_ALL_CONDITION]
    assert "不产生放行" in caplog.text
    stats = current_permission_cache_store().stats()
    assert stats["invalid_rule_rejections"] >= 1

    set_current_permission_snapshot(_snapshot(_rule("k", "nope", _rows(_config(field="x")))))
    assert _conditions(_provider().read_predicate()) == [DENY_ALL_CONDITION]
    assert current_permission_cache_store().stats()["invalid_rule_rejections"] == stats["invalid_rule_rejections"] + 1


@pytest.mark.kiwi_id(2324)
def test_unregistered_policy_and_missing_type_deny_all() -> None:
    """策略未注册 / 缺策略类型 → 永假（该条不产生放行）。"""
    set_current_permission_snapshot(_snapshot(_rule("k", "nope", _rows(_config(field="x")))))
    assert _conditions(_provider().read_predicate()) == [DENY_ALL_CONDITION]
    rule: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    rule.set("data_source_key", "k")
    rule.set("policy_type", 123)
    rule.set("config", ConcurrentStableList())
    set_current_permission_snapshot(_snapshot(rule))
    assert _conditions(_provider().read_predicate()) == [DENY_ALL_CONDITION]


@pytest.mark.kiwi_id(2324)
def test_allow_write_translates_data_source_conditions() -> None:
    """写校验：按 `scope_columns` 翻译数据源维度条件（范围内放行、越界拒、未涉及列跳过）。"""
    set_current_permission_snapshot(_snapshot(_rule("org_dept", "select", _rows(_config(item_code="13")))))
    provider = _provider()
    columns: ConcurrentStableDict[str, str] = ConcurrentStableDict({"org_dept": "dept_id"})
    assert provider.allow_write(_values("dept_id", "13"), scope_columns=columns) is True
    assert provider.allow_write(_values("dept_id", "14"), scope_columns=columns) is False
    assert provider.allow_write(_values("name", "改名"), scope_columns=columns) is True


@pytest.mark.kiwi_id(2324)
def test_allow_write_denies_when_source_column_unmapped() -> None:
    """写校验：数据源维度条件无映射且无字段可回落 → 拒绝写入（并计数）。"""
    set_current_permission_snapshot(_snapshot(_rule("org_dept", "select", _rows(_config(item_code="13")))))
    provider = _provider()
    assert provider.allow_write(_values("dept_id", "13")) is False
    assert provider.allow_write(_values("dept_id", "13"), scope_columns=ConcurrentStableDict()) is False
    assert current_permission_cache_store().stats()["invalid_rule_rejections"] >= 1


@pytest.mark.kiwi_id(2324)
def test_allow_write_falls_back_to_match_field_without_mapping() -> None:
    """写校验：`match` 条件无映射时回落白名单字段原名；有映射时以映射列为准。"""
    set_current_permission_snapshot(_snapshot(_rule("role", "match", _rows(_config(field="code", pattern="BJ*")))))
    provider = _provider()
    assert provider.allow_write(_values("code", "BJ-01")) is True
    assert provider.allow_write(_values("code", "SH-01")) is False
    assert (
        provider.allow_write(_values("code", "SH-01"), scope_columns=ConcurrentStableDict({"role": "role_code"}))
        is True
    )


@pytest.mark.kiwi_id(2324)
def test_allow_write_denies_on_deny_all_and_passes_through() -> None:
    """写校验：永假条件一律拒；豁免 / 无快照 / 无规则恒允许。"""
    set_current_permission_snapshot(_snapshot(_rule("k", "select", _rows(_config(field="code")))))
    provider = _provider()
    assert provider.allow_write(_values("code", "x"), scope_columns=ConcurrentStableDict({"k": "code"})) is False

    set_current_permission_snapshot(
        _snapshot(_rule("k", "select", _rows(_config(item_code="1"))), tier=TIER_SYSTEM_ADMIN)
    )
    assert provider.allow_write(_values("code", "x")) is True
    set_current_permission_snapshot(None)
    assert provider.allow_write(_values("code", "x")) is True
    set_current_permission_snapshot(PermissionSnapshot(tier=TIER_STANDARD))
    assert provider.allow_write(_values("code", "x")) is True


@pytest.mark.kiwi_id(2324)
def test_exempt_and_absent_snapshot_do_not_filter() -> None:
    """豁免层级与未预加载：读不过滤。"""
    set_current_permission_snapshot(
        _snapshot(_rule("k", "select", _rows(_config(item_code="13"))), tier=TIER_SYSTEM_ADMIN)
    )
    assert _provider().read_predicate() is None
    set_current_permission_snapshot(None)
    assert _provider().read_predicate() is None


def test_condition_column_translation_branches() -> None:
    """条件 → 列翻译：非数据源维度原样、映射优先、无映射回落字段、两者皆无即 None + 计数。"""
    assert _condition_column(ScopeCondition("code", "eq", "x"), ConcurrentStableDict({"code": "other"})) == "code"
    assert (
        _condition_column(ScopeCondition("", "in", [], "org_dept"), ConcurrentStableDict({"org_dept": "dept_id"}))
        == "dept_id"
    )
    assert _condition_column(ScopeCondition("code", "like", "a%", "role"), None) == "code"
    before = current_permission_cache_store().stats()["invalid_rule_rejections"]
    assert _condition_column(ScopeCondition("", "in", [], "org_dept"), None) is None
    assert current_permission_cache_store().stats()["invalid_rule_rejections"] == before + 1


def test_threshold_reads_from_settings() -> None:
    """阈值同源读取：`[data_scope].options.max_in_values` 生效，缺省 1000。"""
    assert data_scope_max_in_values(Settings()) == DEFAULT_MAX_IN_VALUES
    assert data_scope_max_in_values(_with_threshold(5)) == 5


def test_factory_and_registration_are_idempotent() -> None:
    """工厂：按配置构造 provider；登记按注册表实例幂等（重复调用不重登记）。"""
    settings = Settings()
    assert isinstance(RbacDataScopeFactory(settings).create(), RbacDataScope)
    register_rbac_data_scope(settings)
    register_rbac_data_scope(settings)


def test_non_sequence_config_denies_and_non_mapping_rows_are_skipped() -> None:
    """规则载荷形态：`config` 非序列按空规则处理（`select` 无值即永假）；序列内非对象项跳过。"""
    non_sequence: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    non_sequence.set("data_source_key", "1")
    non_sequence.set("policy_type", "select")
    non_sequence.set("config", None)
    set_current_permission_snapshot(_snapshot(non_sequence))
    assert _conditions(_provider().read_predicate()) == [DENY_ALL_CONDITION]

    rows = _rows(_config(item_code="13"))
    rows.add("not-a-mapping")
    mixed: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    mixed.set("data_source_key", "k")
    mixed.set("policy_type", "select")
    mixed.set("config", list(rows))
    set_current_permission_snapshot(_snapshot(mixed))
    mixed_conditions = _conditions(_provider().read_predicate())
    assert [(item.operator, item.data_source_key) for item in mixed_conditions] == [("in", "k")]


def test_like_match_handles_wildcards_and_rejects_invalid() -> None:
    """写校验 LIKE：子串 / `%` / `_` 命中；非字符串与越界模式拒。"""
    assert _like_match("BJ-01", "BJ") is True
    assert _like_match("BJ-01", "bj") is False
    assert _like_match("BJ-01", "BJ%") is True
    assert _like_match("BJ-01", "BJ_01") is True
    assert _like_match("BJ-01", "BJ;drop") is False
    assert _like_match(1, "BJ") is False
    assert _like_match("BJ", 1) is False


def test_matches_value_covers_all_operators() -> None:
    """写校验判定：11 种操作符逐一覆盖（含类型不匹配与未知操作符）。"""
    assert _matches_value(None, ScopeCondition("a", "is_null", None)) is True
    assert _matches_value("x", ScopeCondition("a", "is_null", None)) is False
    assert _matches_value("x", ScopeCondition("a", "is_not_null", None)) is True
    assert _matches_value(1, ScopeCondition("a", "eq", 1)) is True
    assert _matches_value(1, ScopeCondition("a", "ne", 2)) is True
    assert _matches_value("x", ScopeCondition("a", "in", ["x", "y"])) is True
    assert _matches_value("z", ScopeCondition("a", "in", ["x"])) is False
    assert _matches_value("x", ScopeCondition("a", "in", "x")) is False
    assert _matches_value("BJ", ScopeCondition("a", "like", "B%")) is True
    assert _matches_value(5, ScopeCondition("a", "between", [1, 10])) is True
    assert _matches_value(5, ScopeCondition("a", "between", [1])) is False
    assert _matches_value("x", ScopeCondition("a", "between", [1, 2])) is False
    assert _matches_value(5, ScopeCondition("a", "gt", 1)) is True
    assert _matches_value(5, ScopeCondition("a", "gte", 5)) is True
    assert _matches_value(5, ScopeCondition("a", "lt", 6)) is True
    assert _matches_value(5, ScopeCondition("a", "lte", 5)) is True
    assert _matches_value("x", ScopeCondition("a", "gt", 1)) is False
    assert _matches_value(1, ScopeCondition("a", "unknown", 1)) is False


def test_custom_policy_receives_data_source_key() -> None:
    """求值器签名：自定义策略收到数据源标识（后代接缝）。"""
    seen: ConcurrentStableList[str] = ConcurrentStableList()

    def _policy(ds: str, rows: _ROWS) -> ConcurrentStableList[ScopeCondition]:
        """自定义策略（记录数据源标识）。

        Args:
            ds: 数据源标识。
            rows: 配置行（忽略）。

        Returns:
            ConcurrentStableList[ScopeCondition]: 单条条件。
        """
        del rows
        seen.add(ds)
        result: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
        result.add(ScopeCondition("code", "in", ["x"], ds))
        return result

    register_scope_policy("custom", _policy)
    set_current_permission_snapshot(_snapshot(_rule("org_dept", "custom", _rows(_config(any="v")))))
    conditions = _conditions(_provider().read_predicate())
    assert list(seen) == ["org_dept"]
    assert conditions[0].data_source_key == "org_dept"
