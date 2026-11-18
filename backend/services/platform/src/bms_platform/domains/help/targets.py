"""帮助文章目标（锚点）校验：目标类型 ↔ 锚点节点类型（08_03 / 12_01 共用）。

- 装载器（`package_spec.py`）与后台维护入口（`services/maintenance.py`）共用本模块，避免两套映射；
- 本模块只做**形态与类型匹配**；错误类型由调用方决定（装载器 `HelpPackageInvalidError` /
  维护面 `HelpArticleContentInvalidError`）；
- 存在性校验（锚点是否登记）由 `target_problem` 统一判定，缺失 / 类型不符分别给出可读原因。
"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableFrozenDict, ConcurrentStableFrozenList
from bms_core.core.exceptions import MenuHelpKeyInvalidError
from bms_core.help.anchors import HelpAnchorKind, validate_help_key
from bms_core.help.values import (
    TARGET_TYPE_ACTION,
    TARGET_TYPE_FIELD,
    TARGET_TYPE_FORM,
    TARGET_TYPE_GLOBAL,
    TARGET_TYPE_MODULE,
    TARGET_TYPES,
)

__all__ = [
    "TARGET_ANCHOR_KINDS",
    "allowed_anchor_kinds",
    "is_known_target_type",
    "target_key_matches",
    "target_problem",
]

TARGET_ANCHOR_KINDS: ConcurrentStableFrozenDict[str, ConcurrentStableFrozenList[HelpAnchorKind]] = (
    ConcurrentStableFrozenDict(
        {
            TARGET_TYPE_MODULE: ConcurrentStableFrozenList((HelpAnchorKind.MENU,)),
            TARGET_TYPE_FORM: ConcurrentStableFrozenList((HelpAnchorKind.FORM,)),
            TARGET_TYPE_FIELD: ConcurrentStableFrozenList((HelpAnchorKind.FIELD,)),
            TARGET_TYPE_ACTION: ConcurrentStableFrozenList((HelpAnchorKind.BUTTON, HelpAnchorKind.ACTION)),
        }
    )
)
"""目标类型 → 允许的锚点节点类型（`global` 不引用锚点，不在表内）。"""


def is_known_target_type(target_type: str) -> bool:
    """目标类型是否在值域内（含 `global`）。

    Args:
        target_type: 目标类型。

    Returns:
        bool: 合法为 True。
    """
    return target_type in TARGET_TYPES


def allowed_anchor_kinds(target_type: str) -> ConcurrentStableFrozenList[HelpAnchorKind] | None:
    """取目标类型允许的锚点节点类型。

    Args:
        target_type: 目标类型。

    Returns:
        ConcurrentStableFrozenList[HelpAnchorKind] | None: 允许类型；`global` 或未知类型为 None。
    """
    return TARGET_ANCHOR_KINDS.get(target_type)


def target_key_matches(target_type: str, key: str) -> bool:
    """判断锚点键形态是否与目标类型匹配（不含存在性）。

    Args:
        target_type: 目标类型（非 `global`）。
        key: 锚点键。

    Returns:
        bool: 至少一种允许的节点类型通过形态校验为 True。
    """
    kinds = allowed_anchor_kinds(target_type)
    if kinds is None or not key.strip():
        return False
    for kind in kinds:
        try:
            validate_help_key(key, kind=kind)
            return True
        except MenuHelpKeyInvalidError:
            continue
    return False


def target_problem(
    target_type: str,
    target_key: str,
    anchors: ConcurrentStableFrozenDict[str, HelpAnchorKind],
) -> str | None:
    """检查目标是否可解析（存在性 + 类型匹配）。

    Args:
        target_type: 目标类型。
        target_key: 锚点键（`global` 为空串）。
        anchors: 锚点值 → 节点类型。

    Returns:
        str | None: 问题描述；可解析返回 None。
    """
    if target_type == TARGET_TYPE_GLOBAL:
        return None
    entry_kind = anchors.get(target_key)
    if entry_kind is None:
        return f"锚点不存在 {target_type}:{target_key}"
    kinds = allowed_anchor_kinds(target_type)
    if kinds is None or entry_kind not in kinds:
        return f"锚点类型不匹配 {target_type}:{target_key}（实际 {entry_kind.value}）"
    return None
