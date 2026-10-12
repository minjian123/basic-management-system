"""数据范围策略注册表用例（Kiwi 2176）：登记 / 取用 / 保序清单 / 清空隔离。

核心只做「查表 + 求值 + 兜底」——策略类型判定归各实现侧登记，故本用例只覆盖注册表自身语义。
"""

from collections.abc import Iterator

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.scope.base import ScopeCondition
from bms_core.scope.policies import (
    register_scope_policy,
    registered_scope_policy_types,
    reset_scope_policies,
    scope_policy,
)


def _policy(config: ConcurrentStableList[ConcurrentStableDict[str, object]]) -> ConcurrentStableList[ScopeCondition]:
    """占位求值器：忽略配置，返回单一恒真条件。

    Args:
        config: 规则配置行。

    Returns:
        ConcurrentStableList[ScopeCondition]: 作用域条件列表。
    """
    del config
    return ConcurrentStableList([ScopeCondition(field="id", operator="is_not_null")])


@pytest.fixture(autouse=True)
def _clean_policies() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """每例前后清空注册表（进程级登记，防跨用例串扰）。

    Yields:
        None: 用例运行期。
    """
    reset_scope_policies()
    yield
    reset_scope_policies()


@pytest.mark.kiwi_id(2176)
def test_register_and_lookup_policy() -> None:
    """登记后可取用；未登记返回 None（调用方按永假处置）。"""
    assert scope_policy("select") is None

    register_scope_policy("select", _policy)

    assert scope_policy("select") is _policy
    assert scope_policy("region") is None


@pytest.mark.kiwi_id(2176)
def test_register_overrides_same_type() -> None:
    """同 key 重复登记：以后登记者为准（装配 / 导入期幂等重放）。"""

    def _other(config: ConcurrentStableList[ConcurrentStableDict[str, object]]) -> ConcurrentStableList[ScopeCondition]:
        """另一求值器替身。"""
        del config
        return ConcurrentStableList()

    register_scope_policy("match", _policy)
    register_scope_policy("match", _other)

    assert scope_policy("match") is _other
    assert registered_scope_policy_types() == ("match",)


@pytest.mark.kiwi_id(2176)
def test_registered_types_preserve_insertion_order() -> None:
    """类型清单按登记顺序输出（登记顺序即输出顺序）。"""
    register_scope_policy("select", _policy)
    register_scope_policy("region", _policy)
    register_scope_policy("extension", _policy)

    assert registered_scope_policy_types() == ("select", "region", "extension")


@pytest.mark.kiwi_id(2176)
def test_reset_clears_registry() -> None:
    """清空注册表：类型清单归零、取用回落 None；空表上重复清空不报错。"""
    register_scope_policy("select", _policy)
    register_scope_policy("region", _policy)

    reset_scope_policies()

    assert registered_scope_policy_types() == ()
    assert scope_policy("select") is None

    reset_scope_policies()
