"""帮助文章目标校验：类型映射 / 形态 / 存在性（12_01）。"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableFrozenDict
from bms_core.help.anchors import HelpAnchorKind
from bms_core.help.values import (
    TARGET_TYPE_ACTION,
    TARGET_TYPE_FIELD,
    TARGET_TYPE_FORM,
    TARGET_TYPE_GLOBAL,
    TARGET_TYPE_MODULE,
)
from bms_platform.domains.help.targets import (
    TARGET_ANCHOR_KINDS,
    allowed_anchor_kinds,
    is_known_target_type,
    target_key_matches,
    target_problem,
)


def test_target_type_domain() -> None:
    """目标类型值域判定（含 global；未知类型拒绝）。"""
    assert is_known_target_type(TARGET_TYPE_GLOBAL) is True
    assert is_known_target_type(TARGET_TYPE_MODULE) is True
    assert is_known_target_type("unknown") is False
    assert allowed_anchor_kinds(TARGET_TYPE_GLOBAL) is None
    assert allowed_anchor_kinds("unknown") is None
    assert list(allowed_anchor_kinds(TARGET_TYPE_ACTION) or []) == [HelpAnchorKind.BUTTON, HelpAnchorKind.ACTION]
    assert TARGET_TYPE_MODULE in TARGET_ANCHOR_KINDS


def test_target_key_shape() -> None:
    """锚点形态与目标类型匹配（按钮 / 动作码两种动作目标均可）。"""
    assert target_key_matches(TARGET_TYPE_MODULE, "platform:sys:::") is True
    assert target_key_matches(TARGET_TYPE_FORM, "platform:sys:user::") is True
    assert target_key_matches(TARGET_TYPE_FIELD, "platform:sys:user:username:") is True
    assert target_key_matches(TARGET_TYPE_ACTION, "platform:sys:user::create") is True
    assert target_key_matches(TARGET_TYPE_ACTION, "platform::::create") is True
    assert target_key_matches(TARGET_TYPE_MODULE, "platform:sys:user:username:") is False
    assert target_key_matches(TARGET_TYPE_MODULE, "") is False
    assert target_key_matches("unknown", "platform:sys:::") is False


def test_target_problem_by_anchor_map() -> None:
    """存在性 / 类型匹配：全局恒可解析；缺失与类型不符给出原因。"""
    anchors: ConcurrentStableFrozenDict[str, HelpAnchorKind] = ConcurrentStableFrozenDict(
        {
            "platform:sys:::": HelpAnchorKind.MENU,
            "platform:sys:user::": HelpAnchorKind.FORM,
            "platform:sys:user::create": HelpAnchorKind.BUTTON,
        }
    )
    assert target_problem(TARGET_TYPE_GLOBAL, "", anchors) is None
    assert target_problem(TARGET_TYPE_MODULE, "platform:sys:::", anchors) is None
    assert target_problem(TARGET_TYPE_FORM, "platform:sys:user::", anchors) is None
    assert target_problem(TARGET_TYPE_ACTION, "platform:sys:user::create", anchors) is None
    missing = target_problem(TARGET_TYPE_FIELD, "platform:sys:user:username:", anchors)
    assert missing is not None and "不存在" in missing
    mismatch = target_problem(TARGET_TYPE_FORM, "platform:sys:::", anchors)
    assert mismatch is not None and "类型不匹配" in mismatch
    unknown_kind = target_problem(TARGET_TYPE_ACTION, "platform:sys:user::", anchors)
    assert unknown_kind is not None and "类型不匹配" in unknown_kind
