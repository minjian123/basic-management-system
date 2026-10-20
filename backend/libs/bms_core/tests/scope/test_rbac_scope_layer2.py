"""数据范围层2（规则物化缓存）用例（`04_02`，Kiwi 2321）。

口径见详细设计 §5.3：规则求值结果按「字典类型 + 策略 + `config` 内容指纹」键控、**不含用户**，
同一规则被多个用户命中时只求值一次；非法 / 未注册规则仍退化为永假（该条不产生放行）；
指纹不可算（含不可序列化对象）时退化为「不缓存、直接求值」，不影响正确性。

本套另含**真实行形态**回归：引擎产出的 `config` 行是基座集合类（`ConcurrentStableDict`），
按 `Mapping` 协议判定——若按内建 `dict` 判定会被静默丢弃，读过滤与写校验随之失效。
"""

from collections.abc import Iterator
from typing import Any, cast

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.permission.cache import (
    OPTION_RULE_CACHE_MAX_ELEMENTS,
    configure_permission_cache_store,
    current_permission_cache_store,
    reset_permission_cache_store,
)
from bms_core.permission.snapshot import TIER_STANDARD, PermissionSnapshot, set_current_permission_snapshot
from bms_core.scope.base import ScopeCondition
from bms_core.scope.policies import register_scope_policy, reset_scope_policies
from bms_core.scope.policies_rbac import register_rbac_scope_policies
from bms_core.scope.rbac import RbacDataScope


def _config(**kwargs: object) -> ConcurrentStableDict[str, object]:
    """构造一条策略配置行（基座集合类，与真实链路同形态）。

    Args:
        kwargs: 键值对。

    Returns:
        ConcurrentStableDict[str, object]: 配置行。
    """
    row: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    for key, value in kwargs.items():
        row.set(key, value)
    return row


def _rule(
    *, config: object, data_source_key: str = "1", policy_type: str = "select"
) -> ConcurrentStableDict[str, object]:
    """构造一条数据范围规则行（真实快照形态）。

    Args:
        config: 规则行集合（`ConcurrentStableList`）。
        data_source_key: 字典类型。
        policy_type: 策略类型。

    Returns:
        ConcurrentStableDict[str, object]: 规则行。
    """
    row: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    row.set("data_source_key", data_source_key)
    row.set("policy_type", policy_type)
    row.set("config", config)
    return row


def _snapshot(*rules: ConcurrentStableDict[str, object]) -> PermissionSnapshot:
    """构造快照。

    Args:
        *rules: 规则行。

    Returns:
        PermissionSnapshot: 快照。
    """
    collected: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    for rule in rules:
        collected.add(rule)
    return PermissionSnapshot(tier=TIER_STANDARD, data_scopes=collected)


def _provider() -> RbacDataScope:
    """构造数据范围 provider。

    Returns:
        RbacDataScope: provider 实例。
    """
    return RbacDataScope(Settings())


@pytest.fixture(autouse=True)
def clean_layer2() -> Iterator[None]:
    """每例复位策略注册表、快照上下文与进程级三层缓存仓。

    Yields:
        None: 用例运行期。
    """
    reset_scope_policies()
    register_rbac_scope_policies()
    set_current_permission_snapshot(None)
    reset_permission_cache_store()
    yield
    set_current_permission_snapshot(None)
    reset_permission_cache_store()
    reset_scope_policies()


@pytest.mark.kiwi_id(2324)
def test_mapping_rows_from_engine_produce_conditions() -> None:
    """真实行形态：`config` 行是 `ConcurrentStableDict`，读条件必须产生（否则读过滤静默失效）。"""
    rows: ConcurrentStableList[object] = ConcurrentStableList()
    rows.add(_config(item_code="13"))
    rows.add(_config(item_code="14"))
    set_current_permission_snapshot(_snapshot(_rule(config=rows)))
    predicate = _provider().read_predicate()
    assert predicate is not None
    conditions = cast("ConcurrentStableList[ScopeCondition]", predicate)
    assert len(conditions) == 1
    assert conditions[0].operator == "in"
    assert set(cast("Any", conditions[0].value)) == {"13", "14"}  # `04_03` 起 in 值为去重集合


@pytest.mark.kiwi_id(2324)
def test_rule_result_is_shared_across_users() -> None:
    """按规则共享：同一规则被两个用户命中时策略只求值一次（键不含用户）。"""
    calls: ConcurrentStableList[int] = ConcurrentStableList()

    def _counting(
        data_source_key: str,
        config: ConcurrentStableList[ConcurrentStableDict[str, object]],
    ) -> ConcurrentStableList[ScopeCondition]:
        """计数求值器。

        Args:
            data_source_key: 数据源标识（忽略）。
            config: 规则行（忽略）。

        Returns:
            ConcurrentStableList[ScopeCondition]: 单条条件。
        """
        del data_source_key, config
        calls.add(1)
        result: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
        result.add(ScopeCondition("code", "in", ["001"]))
        return result

    reset_scope_policies()
    register_scope_policy("counted", _counting)

    rows: ConcurrentStableList[object] = ConcurrentStableList()
    rows.add(_config(field="code"))
    rule = _rule(config=rows, policy_type="counted")
    provider = _provider()

    set_current_permission_snapshot(_snapshot(rule))
    first = cast("ConcurrentStableList[ScopeCondition]", provider.read_predicate())
    set_current_permission_snapshot(_snapshot(rule))
    second = cast("ConcurrentStableList[ScopeCondition]", provider.read_predicate())

    assert len(calls) == 1
    assert first[0].value == second[0].value


@pytest.mark.kiwi_id(2324)
def test_illegal_rule_still_denies_all_and_is_cached() -> None:
    """非法规则：永假条件（该条不产生放行），且结果可复用。"""
    rows: ConcurrentStableList[object] = ConcurrentStableList()
    rows.add(_config(item_code=""))
    set_current_permission_snapshot(_snapshot(_rule(config=rows)))
    provider = _provider()
    first = cast("ConcurrentStableList[ScopeCondition]", provider.read_predicate())
    second = cast("ConcurrentStableList[ScopeCondition]", provider.read_predicate())
    assert [(item.field, item.operator, list(cast("Any", item.value))) for item in first] == [("id", "in", [])]
    assert first[0].field == second[0].field


@pytest.mark.kiwi_id(2324)
def test_unregistered_policy_denies_without_cache() -> None:
    """策略未注册：直接永假（不进层2，避免把「配置错」缓存成长期结论）。"""
    rows: ConcurrentStableList[object] = ConcurrentStableList()
    rows.add(_config(field="code"))
    set_current_permission_snapshot(_snapshot(_rule(config=rows, policy_type="nope")))
    conditions = cast("ConcurrentStableList[ScopeCondition]", _provider().read_predicate())
    assert [(item.field, item.operator) for item in conditions] == [("id", "in")]
    assert current_permission_cache_store().stats()["rule_items"] == 0


@pytest.mark.kiwi_id(2324)
def test_uncacheable_config_falls_back_to_direct_evaluation() -> None:
    """指纹不可算（含集合等非序列值）：不缓存、直接求值，结果仍正确。"""
    rows: ConcurrentStableList[object] = ConcurrentStableList()
    rows.add(_config(item_code="001", extra={1, 2}))
    set_current_permission_snapshot(_snapshot(_rule(config=rows)))
    conditions = cast("ConcurrentStableList[ScopeCondition]", _provider().read_predicate())
    assert len(conditions) == 1
    assert conditions[0].operator == "in"
    assert current_permission_cache_store().stats()["rule_items"] == 0


@pytest.mark.kiwi_id(2324)
def test_rule_cache_budget_eviction_falls_back_to_recompute() -> None:
    """元素预算淘汰后：该规则下次命中重新求值（不返回空、不报错）。"""
    calls: ConcurrentStableList[int] = ConcurrentStableList()

    def _counting(
        data_source_key: str,
        config: ConcurrentStableList[ConcurrentStableDict[str, object]],
    ) -> ConcurrentStableList[ScopeCondition]:
        """计数求值器。

        Args:
            data_source_key: 数据源标识（忽略）。
            config: 规则行（忽略）。

        Returns:
            ConcurrentStableList[ScopeCondition]: 单条条件。
        """
        del data_source_key, config
        calls.add(1)
        result: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
        result.add(ScopeCondition("code", "in", ["001"]))
        return result

    reset_scope_policies()
    register_scope_policy("counted", _counting)
    store = configure_permission_cache_store({OPTION_RULE_CACHE_MAX_ELEMENTS: 1})

    rows: ConcurrentStableList[object] = ConcurrentStableList()
    rows.add(_config(any="v"))
    rule = _rule(config=rows, policy_type="counted")
    big_rows: ConcurrentStableList[object] = ConcurrentStableList()
    big_rows.add(_config(any="v"))
    big_rows.add(_config(other="v"))
    big_rule = _rule(config=big_rows, policy_type="counted", data_source_key="2")
    provider = _provider()

    set_current_permission_snapshot(_snapshot(rule))
    provider.read_predicate()
    assert store.stats()["rule_elements"] == 1

    set_current_permission_snapshot(_snapshot(big_rule))
    provider.read_predicate()
    assert store.stats()["rule_elements"] <= 1

    set_current_permission_snapshot(_snapshot(rule))
    conditions = cast("ConcurrentStableList[ScopeCondition]", provider.read_predicate())
    assert len(calls) == 3
    assert conditions[0].operator == "in"


@pytest.mark.kiwi_id(2324)
def test_missing_policy_type_denies_all() -> None:
    """规则缺策略类型（非字符串）：按永假处置（该条不产生放行）。"""
    rule: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    rule.set("data_source_key", "1")
    rule.set("policy_type", 123)
    rule.set("config", ConcurrentStableList())
    set_current_permission_snapshot(_snapshot(rule))
    conditions = cast("ConcurrentStableList[ScopeCondition]", _provider().read_predicate())
    assert [(item.field, item.operator) for item in conditions] == [("id", "in")]


@pytest.mark.kiwi_id(2324)
def test_non_sequence_config_denies_all() -> None:
    """`config` 非序列：按空规则处理，`select` 无值即永假（不抛错、不放大范围）。"""
    rule: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    rule.set("data_source_key", "1")
    rule.set("policy_type", "select")
    rule.set("config", "not-a-list")
    set_current_permission_snapshot(_snapshot(rule))
    conditions = cast("ConcurrentStableList[ScopeCondition]", _provider().read_predicate())
    assert [(item.field, item.operator) for item in conditions] == [("id", "in")]
