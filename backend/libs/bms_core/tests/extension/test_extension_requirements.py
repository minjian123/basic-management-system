"""扩展点声明与装配校验（07D 需求 02-1 公共机制）：纯逻辑用例。

覆盖详细设计 §1.5 用例：
- 声明的三项形态校验（扩展点键 / 实现名 / 执行序）；
- 必需缺失即拒启（一次性汇总全部缺失项）；可选缺失按声明跳过并返回生效清单；
- 生效清单保持声明顺序；按扩展点键筛选后按 `(order, 声明序)` 排序。
"""

from __future__ import annotations

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import PluginError
from bms_core.core.plugin import PluginImpl
from bms_core.extension import (
    RESOURCE_ACL_KEY,
    SCOPE_RULE_KEY,
    ExtensionRequirement,
    requirements_by_key,
    verify_extension_requirements,
)

pytestmark = pytest.mark.kiwi_id(2450)


def _snapshot(*entries: tuple[str, str]) -> ConcurrentStableDict[str, ConcurrentStableDict[str, PluginImpl]]:
    """构造插件注册表快照（只关心是否存在，不关心实现内容）。

    Args:
        *entries: `(plugin_key, plugin_name)` 组合。

    Returns:
        ConcurrentStableDict[str, ConcurrentStableDict[str, PluginImpl]]: 两级映射快照。
    """
    snapshot: ConcurrentStableDict[str, ConcurrentStableDict[str, PluginImpl]] = ConcurrentStableDict()
    for plugin_key, plugin_name in entries:
        bucket = snapshot.get(plugin_key)
        if bucket is None:
            bucket = ConcurrentStableDict[str, PluginImpl]()
            snapshot.set(plugin_key, bucket)
        bucket.set(plugin_name, object)  # type: ignore[arg-type]
    return snapshot


def test_requirement_rejects_unknown_key() -> None:
    """扩展点键必须在已知集合内（写错键名 = 配置错，装配期即拒）。"""
    with pytest.raises(PluginError, match="扩展点键未知"):
        ExtensionRequirement(plugin_key="unknown_key", plugin_name="demo")


def test_requirement_rejects_bad_name() -> None:
    """实现名须为小写标识符（可点分）。"""
    with pytest.raises(PluginError, match="实现名形态非法"):
        ExtensionRequirement(plugin_key=SCOPE_RULE_KEY, plugin_name="Demo.Rule")


def test_requirement_rejects_order_out_of_range() -> None:
    """执行序越界即拒（0~999）。"""
    with pytest.raises(PluginError, match="执行序越界"):
        ExtensionRequirement(plugin_key=SCOPE_RULE_KEY, plugin_name="demo", order=1000)


def test_missing_required_raises_with_all_entries() -> None:
    """必需项缺失一次性汇总（不在第一个缺失处中断）。"""
    requirements = ConcurrentStableList(
        (
            ExtensionRequirement(plugin_key=SCOPE_RULE_KEY, plugin_name="demo.rule"),
            ExtensionRequirement(plugin_key=RESOURCE_ACL_KEY, plugin_name="demo.acl"),
        )
    )
    with pytest.raises(PluginError) as excinfo:
        verify_extension_requirements(requirements, snapshot=_snapshot(), product_label="demo")
    message = str(excinfo.value)
    assert "demo｜" in message
    assert "scope_rule:demo.rule" in message
    assert "resource_acl:demo.acl" in message


def test_optional_missing_is_skipped() -> None:
    """可选项缺失不阻塞启动，且不出现在生效清单。"""
    requirements = ConcurrentStableList(
        (
            ExtensionRequirement(plugin_key=SCOPE_RULE_KEY, plugin_name="demo.rule", required=False),
            ExtensionRequirement(plugin_key=RESOURCE_ACL_KEY, plugin_name="demo.acl"),
        )
    )
    effective = verify_extension_requirements(requirements, snapshot=_snapshot((RESOURCE_ACL_KEY, "demo.acl")))
    assert [item.plugin_name for item in effective] == ["demo.acl"]


def test_effective_keeps_declaration_order() -> None:
    """生效清单保持声明顺序（同 order 时声明序即执行序）。"""
    requirements = ConcurrentStableList(
        (
            ExtensionRequirement(plugin_key=SCOPE_RULE_KEY, plugin_name="b.rule"),
            ExtensionRequirement(plugin_key=SCOPE_RULE_KEY, plugin_name="a.rule"),
        )
    )
    effective = verify_extension_requirements(
        requirements,
        snapshot=_snapshot((SCOPE_RULE_KEY, "a.rule"), (SCOPE_RULE_KEY, "b.rule")),
    )
    assert [item.plugin_name for item in effective] == ["b.rule", "a.rule"]


def test_requirements_by_key_orders_by_order_then_declaration() -> None:
    """按扩展点键筛选后按 `(order, 声明序)` 排序。"""
    requirements = ConcurrentStableList(
        (
            ExtensionRequirement(plugin_key=SCOPE_RULE_KEY, plugin_name="late", order=200),
            ExtensionRequirement(plugin_key=RESOURCE_ACL_KEY, plugin_name="acl"),
            ExtensionRequirement(plugin_key=SCOPE_RULE_KEY, plugin_name="early", order=10),
            ExtensionRequirement(plugin_key=SCOPE_RULE_KEY, plugin_name="middle", order=10),
        )
    )
    ordered = requirements_by_key(requirements, SCOPE_RULE_KEY)
    assert [item.plugin_name for item in ordered] == ["early", "middle", "late"]
