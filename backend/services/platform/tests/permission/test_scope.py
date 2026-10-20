"""平台服务数据范围用例（`04_01` 下沉后）：provider 端到端 + 装配登记。

四策略求值器与 provider 本体已下沉基座，其逐分支用例在
`libs/bms_core/tests/scope/test_policies_rbac.py`；本文件只保留平台侧需要的两件事：

1. **端到端**：按平台真实装配（`[data_scope].provider = rbac`）解析出的 provider 能把快照规则转成
   读条件、并对写值做校验；
2. **登记幂等**：`register_rbac_data_scope` 按注册表实例幂等（重复调用不重登记）。
"""

from collections.abc import Iterator
from typing import Any, cast

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.context import current_user_id
from bms_core.permission.snapshot import (
    TIER_STANDARD,
    PermissionSnapshot,
    set_current_permission_snapshot,
)
from bms_core.scope.base import ScopeCondition
from bms_core.scope.extensions import reset_data_scope_extensions, reset_scope_extension_resolvers
from bms_core.scope.policies_rbac import DENY_ALL_CONDITION, register_rbac_scope_policies
from bms_core.scope.rbac import RbacDataScope, RbacDataScopeFactory, register_rbac_data_scope


@pytest.fixture(autouse=True)
def clean_scope() -> Iterator[None]:
    """每例前后重置快照与扩展求值器（策略为进程级登记，需按需重放）。

    Yields:
        None: 用例运行期。
    """
    set_current_permission_snapshot(None)
    reset_scope_extension_resolvers()
    reset_data_scope_extensions()
    register_rbac_scope_policies()
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
    data_source_key: str | int, policy_type: str, config: ConcurrentStableList[object]
) -> ConcurrentStableDict[str, object]:
    """构造一条数据范围规则（快照载荷行）。

    Args:
        data_source_key: 数据源标识（快照载荷行合成值）。
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


def _as_conditions(predicate: object) -> ConcurrentStableList[ScopeCondition]:
    """把 provider 读条件规整为条件列表。

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


@pytest.mark.kiwi_id(2324)
def test_provider_turns_snapshot_rules_into_read_conditions() -> None:
    """端到端：快照里的 `select` 规则经平台装配的 provider 转成数据源维度 `IN` 读条件。"""
    rows: ConcurrentStableList[object] = ConcurrentStableList()
    rows.add(dict(_config(item_code="13")))
    set_current_permission_snapshot(_snapshot(_rule("org_dept", "select", rows)))
    conditions = _as_conditions(_provider().read_predicate())
    assert len(conditions) == 1
    assert conditions[0].operator == "in"
    assert conditions[0].data_source_key == "org_dept"
    assert conditions[0].field == ""
    assert set(cast("Any", conditions[0].value)) == {"13"}  # `04_03` 起 in 值为去重集合


@pytest.mark.kiwi_id(2324)
def test_provider_rejects_out_of_scope_writes() -> None:
    """端到端：写校验按同一批条件判定（传列映射放行 / 越界拒 / 未传映射即拒）。"""
    rows: ConcurrentStableList[object] = ConcurrentStableList()
    rows.add(dict(_config(item_code="13")))
    set_current_permission_snapshot(_snapshot(_rule("org_dept", "select", rows)))
    provider = _provider()
    inside: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    inside.set("dept_id", "13")
    outside: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    outside.set("dept_id", "14")
    columns: ConcurrentStableDict[str, str] = ConcurrentStableDict({"org_dept": "dept_id"})
    assert provider.allow_write(inside, scope_columns=columns) is True
    assert provider.allow_write(outside, scope_columns=columns) is False
    assert provider.allow_write(inside) is False


@pytest.mark.kiwi_id(2320)
def test_provider_denies_all_for_unregistered_policy() -> None:
    """端到端：策略未注册 → 永假条件（该条不产生放行）。"""
    rows: ConcurrentStableList[object] = ConcurrentStableList()
    rows.add(dict(_config(field="x")))
    set_current_permission_snapshot(_snapshot(_rule(1, "nope", rows)))
    assert _as_conditions(_provider().read_predicate()) == [DENY_ALL_CONDITION]


@pytest.mark.kiwi_id(2320)
def test_factory_and_registration_are_idempotent() -> None:
    """工厂：按配置构造 provider；登记按注册表实例幂等（重复调用不重登记）。"""
    settings = Settings()
    provider = RbacDataScopeFactory(settings).create()
    assert isinstance(provider, RbacDataScope)

    register_rbac_data_scope(settings)
    register_rbac_data_scope(settings)
