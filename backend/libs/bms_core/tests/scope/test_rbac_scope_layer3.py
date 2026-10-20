"""数据范围集合物化与大集合护栏用例（`04_03`，Kiwi 2323）。

口径见详细设计 §5.2：

1. **集合去重物化**：`in` 条件的值在产出时物化为 `ConcurrentStableSet`（层2 命中即同一份集合）；
2. **按规则共享**：同一规则被 N 个快照命中只求值一次，层2 条目 / 元素 / 估算字节不随用户数增长；
3. **大集合护栏**：并集合并后任一 `in` 条件元素数超 `[data_scope].options.max_in_values` 即整体
   退化为永假并上报引导；`region` / `match` 不参与判定；超阈结果进层2（不重复重扫巨型值列表）；
4. **写校验一致**：任一条件为永假即拒绝写入。
"""

from collections.abc import Iterator
from typing import Any, cast

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.permission.cache import (
    RULE_ELEMENT_BYTES,
    RULE_ENTRY_OVERHEAD_BYTES,
    current_permission_cache_store,
    reset_permission_cache_store,
)
from bms_core.permission.snapshot import TIER_STANDARD, PermissionSnapshot, set_current_permission_snapshot
from bms_core.scope.base import ScopeCondition
from bms_core.scope.policies import register_scope_policy, reset_scope_policies
from bms_core.scope.policies_rbac import DENY_ALL_CONDITION, register_rbac_scope_policies
from bms_core.scope.rbac import DEFAULT_MAX_IN_VALUES, OPTION_MAX_IN_VALUES, RbacDataScope

_SOURCE = "test_source"
"""快照来源标识（用例直接写进程级缓存仓时使用）。"""


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


def _rows(*rows: ConcurrentStableDict[str, object]) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """把配置行收成规则行列表。

    Args:
        *rows: 配置行。

    Returns:
        ConcurrentStableList[ConcurrentStableDict[str, object]]: 规则行列表。
    """
    collected: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    for row in rows:
        collected.add(row)
    return collected


def _snapshot(*rules: ConcurrentStableDict[str, object]) -> PermissionSnapshot:
    """构造快照。

    Args:
        *rules: 规则行。

    Returns:
        PermissionSnapshot: 快照。
    """
    return PermissionSnapshot(tier=TIER_STANDARD, data_scopes=_rows(*rules))


def _provider(settings: Settings | None = None) -> RbacDataScope:
    """构造数据范围 provider。

    Args:
        settings: 应用配置（缺省取缺省配置）。

    Returns:
        RbacDataScope: provider 实例。
    """
    return RbacDataScope(settings if settings is not None else Settings())


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


def _conditions(predicate: object) -> ConcurrentStableList[ScopeCondition]:
    """把读条件规整为条件列表。

    Args:
        predicate: `read_predicate()` 返回值。

    Returns:
        ConcurrentStableList[ScopeCondition]: 条件列表。
    """
    result: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
    if predicate is None:
        return result
    for item in cast("Any", predicate):
        result.add(cast("ScopeCondition", item))
    return result


def _counting_policy(calls: ConcurrentStableList[int]) -> Any:
    """构造计数求值器（记录被调用次数）。

    Args:
        calls: 调用计数容器。

    Returns:
        Any: 求值器。
    """

    def _policy(
        data_source_key: str,
        config: ConcurrentStableList[ConcurrentStableDict[str, object]],
    ) -> ConcurrentStableList[ScopeCondition]:
        """按配置行数产出条件（记录一次调用）。

        Args:
            data_source_key: 数据源标识（忽略）。
            config: 规则行。

        Returns:
            ConcurrentStableList[ScopeCondition]: 单条条件。
        """
        del data_source_key
        calls.add(len(config))
        result: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
        result.add(ScopeCondition("code", "in", ["001", "002"]))
        return result

    return _policy


@pytest.fixture(autouse=True)
def clean_state() -> Iterator[None]:
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
def test_in_values_materialized_as_deduplicated_set() -> None:
    """集合物化：`select` 值去重为集合（重复值不重复计入元素数）。"""
    rule = _rule(config=_rows(_config(item_code="13"), _config(item_code="13"), _config(item_code="14")))
    set_current_permission_snapshot(_snapshot(rule))
    conditions = _conditions(_provider().read_predicate())
    assert len(conditions) == 1
    assert set(cast("Any", conditions[0].value)) == {"13", "14"}
    assert current_permission_cache_store().stats()["rule_elements"] == 2


@pytest.mark.kiwi_id(2324)
def test_rule_shared_across_snapshots_single_materialization() -> None:
    """按规则共享：三个用户命中同一规则只求值一次，层2 只有一份且内存不随用户数增长。"""
    calls: ConcurrentStableList[int] = ConcurrentStableList()
    reset_scope_policies()
    register_scope_policy("counted", _counting_policy(calls))
    rule = _rule(config=_rows(_config(any="v")), policy_type="counted")
    provider = _provider()
    store = current_permission_cache_store()
    for user_id in (1, 2, 3):
        store.set_snapshot(source=_SOURCE, tenant_id="1001", user_id=user_id, version=1, value=_snapshot(rule))

    results: ConcurrentStableList[ScopeCondition] = ConcurrentStableList()
    for _ in range(3):
        set_current_permission_snapshot(_snapshot(rule))
        results.add(_conditions(provider.read_predicate())[0])

    stats = store.stats()
    assert len(calls) == 1  # 同一规则只求值一次
    assert stats["rule_items"] == 1
    assert stats["rule_elements"] == 2
    assert stats["rule_estimated_bytes"] == RULE_ENTRY_OVERHEAD_BYTES + 2 * RULE_ELEMENT_BYTES
    assert stats["rule_refs"] == 1  # 三条快照共用一条规则
    assert results[1] is results[0]  # 命中即同一份集合（未按用户复制）


@pytest.mark.kiwi_id(2324)
def test_oversized_in_denies_all_with_guidance(caplog: pytest.LogCaptureFixture) -> None:
    """大集合：值数超阈 → 整体永假 + 引导日志 + 计数；退化结果进层2（不重复重扫巨型值列表）。"""
    rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    for index in range(DEFAULT_MAX_IN_VALUES + 1):
        rows.add(_config(item_code=str(index)))
    rule = _rule(config=rows)
    set_current_permission_snapshot(_snapshot(rule))
    provider = _provider()

    with caplog.at_level("WARNING"):
        first = _conditions(provider.read_predicate())
    second = _conditions(provider.read_predicate())

    assert first == [DENY_ALL_CONDITION]
    assert second == [DENY_ALL_CONDITION]
    assert "改用区域 / 匹配 / 扩展策略" in caplog.text
    stats = current_permission_cache_store().stats()
    assert stats["oversized_rejections"] == 1  # 退化结果进层2，第二次命中不再重判
    assert stats["rule_items"] == 1
    assert stats["rule_elements"] == 0  # 缓存的永假结果不再承载巨型值列表


@pytest.mark.kiwi_id(2324)
def test_threshold_comes_from_data_scope_options() -> None:
    """阈值可配：`[data_scope].options.max_in_values` 生效；非正值视为不限制。

    阈值不入规则指纹（改配置需重启并重建缓存仓），故每组阈值前复位进程级缓存仓。
    """
    rule = _rule(config=_rows(_config(item_code="13"), _config(item_code="14"), _config(item_code="15")))
    set_current_permission_snapshot(_snapshot(rule))

    strict = _provider(_with_threshold(2))
    assert _conditions(strict.read_predicate()) == [DENY_ALL_CONDITION]
    assert strict.max_in_values == 2

    reset_permission_cache_store()
    loose = _provider(_with_threshold(3))
    assert len(_conditions(loose.read_predicate())) == 1

    reset_permission_cache_store()
    unlimited = _provider(_with_threshold(0))
    assert set(cast("Any", _conditions(unlimited.read_predicate())[0].value)) == {"13", "14", "15"}


@pytest.mark.kiwi_id(2324)
def test_region_and_match_not_subject_to_threshold() -> None:
    """区域 / 匹配：以 SQL 原生算子表达、不枚举，不参与大集合判定。"""
    region = _rule(
        config=_rows(_config(start="110000", end="119999")),
        data_source_key="2",
        policy_type="region",
    )
    match = _rule(config=_rows(_config(field="code", pattern="BJ*")), data_source_key="3", policy_type="match")
    set_current_permission_snapshot(_snapshot(region, match))
    conditions = _conditions(_provider(_with_threshold(1)).read_predicate())
    assert [(item.operator, item.value) for item in conditions] == [
        ("between", ("110000", "119999")),
        ("like", "BJ%"),
    ]


@pytest.mark.kiwi_id(2324)
def test_union_merge_over_threshold_denies() -> None:
    """合并后超阈：两条各自合规的同数据源 `in` 合并超阈即整体永假（判定在合并之后）。"""
    first = _rule(config=_rows(_config(item_code="13"), _config(item_code="14")))
    second = _rule(config=_rows(_config(item_code="15"), _config(item_code="16")))
    set_current_permission_snapshot(_snapshot(first, second))

    merged = _conditions(_provider(_with_threshold(3)).read_predicate())
    assert merged == [DENY_ALL_CONDITION]
    assert set(cast("Any", _conditions(_provider(_with_threshold(4)).read_predicate())[0].value)) == {
        "13",
        "14",
        "15",
        "16",
    }


@pytest.mark.kiwi_id(2324)
def test_allow_write_denies_on_deny_all() -> None:
    """写校验：非法规则与超阈退化同样拒绝写入（读写口径一致）。"""
    illegal = _rule(config=_rows(_config(item_code="")))
    set_current_permission_snapshot(_snapshot(illegal))
    values: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    values.set("area_code", "13")
    columns: ConcurrentStableDict[str, str] = ConcurrentStableDict({"1": "area_code", "2": "area_code"})
    assert _provider().allow_write(values, scope_columns=columns) is False

    oversized = _rule(
        config=_rows(
            _config(item_code="13"),
            _config(item_code="14"),
            _config(item_code="15"),
        ),
        data_source_key="2",
    )
    set_current_permission_snapshot(_snapshot(oversized))
    assert _provider(_with_threshold(2)).allow_write(values, scope_columns=columns) is False
