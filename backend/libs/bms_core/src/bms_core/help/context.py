"""帮助五级解析链：候选构建与解析编排（08_02）。

口径（详细设计 §5.1）：

- 顺序「字段 → 动作（按钮 → 动作码兜底）→ 表单 → 模块 → 全局」，逐级降级；
- **字段 / 动作 / 表单**按元数据自然键定位（表单自然键 = 业务码 `sys_business.code`），
  取该行的 `help_key`；**模块**无自然键列，按菜单锚点第 2 段匹配；
- 某级锚点未登记（`NULL`）或元数据行停用 / 软删 → 索引中无该项，天然降级；
- 同一 `help_key` 只保留首次出现；末项恒为全局级（无锚点），由内容侧按 `target_type=global` 取文章。

本模块不碰数据库：索引由 `bms_core/repositories/help_anchor.py` 归集、`bms_core/help/index.py` 缓存，
内容由 `bms_core/help/content.py` 的端口按候选顺序解析。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from fastapi import Request

from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.objects import BaseValueObject
from bms_core.help.anchors import PLATFORM_PRODUCT_KEY
from bms_core.help.content import (
    BaseHelpContentResolver,
    HelpAnchorCandidate,
    HelpContentQuery,
    HelpContentResult,
    HelpLevel,
)
from bms_core.help.index import HelpAnchorIndex, HelpMenuAnchor

__all__ = ["HelpContextInput", "build_help_candidates", "has_anchor", "resolve_help_context"]


@dataclass(frozen=True)
class HelpContextInput(BaseValueObject):
    """解析上下文入参（均为可选；全空时只走全局级）。

    Attributes:
        product_key: 产品段（仅模块级消歧用）。
        module_key: 模块键（菜单锚点第 2 段）。
        form_key: 表单键（业务码）。
        field_key: 字段键（需同时给 `form_key`）。
        action_code: 动作码或完整权限码（`业务码:动作码`）。
    """

    product_key: str | None = None
    module_key: str | None = None
    form_key: str | None = None
    field_key: str | None = None
    action_code: str | None = None

    @classmethod
    def of(
        cls,
        *,
        product_key: str | None = None,
        module_key: str | None = None,
        form_key: str | None = None,
        field_key: str | None = None,
        action_code: str | None = None,
    ) -> HelpContextInput:
        """归一下录入参（去首尾空白；空串视为未提供）。

        Args:
            product_key: 产品段。
            module_key: 模块键。
            form_key: 表单键。
            field_key: 字段键。
            action_code: 动作码或完整权限码。

        Returns:
            HelpContextInput: 归一后的入参。
        """
        return cls(
            product_key=_clean(product_key),
            module_key=_clean(module_key),
            form_key=_clean(form_key),
            field_key=_clean(field_key),
            action_code=_clean(action_code),
        )


def build_help_candidates(
    index: HelpAnchorIndex, context: HelpContextInput
) -> ConcurrentStableList[HelpAnchorCandidate]:
    """按五级顺序构建候选（同一锚点只保留首次出现；末项恒为全局级）。

    Args:
        index: 锚点索引。
        context: 解析上下文入参。

    Returns:
        ConcurrentStableList[HelpAnchorCandidate]: 有序候选（首项最贴近当前上下文）。
    """
    candidates: ConcurrentStableList[HelpAnchorCandidate] = ConcurrentStableList()
    seen: ConcurrentStableSet[str] = ConcurrentStableSet()

    def add(level: HelpLevel, help_key: str | None) -> None:
        """追加候选（空锚点与重复锚点跳过）。

        Args:
            level: 解析层级。
            help_key: 锚点值。
        """
        if help_key is None or help_key in seen:
            return
        seen.add(help_key)
        candidates.add(HelpAnchorCandidate(level=level, help_key=help_key))

    if context.form_key is not None and context.field_key is not None:
        add(HelpLevel.FIELD, index.fields.get((context.form_key, context.field_key)))

    if context.action_code is not None:
        business, action = _action_target(context)
        if business is not None:
            add(HelpLevel.ACTION, index.buttons.get((business, action)))
        add(HelpLevel.ACTION, index.actions.get(action))

    if context.form_key is not None:
        add(HelpLevel.FORM, index.forms.get(context.form_key))

    if context.module_key is not None:
        for menu in _module_anchors(index, context.module_key, context.product_key):
            add(HelpLevel.MODULE, menu.help_key)

    candidates.add(HelpAnchorCandidate(level=HelpLevel.GLOBAL, help_key=None))
    return candidates


def has_anchor(candidates: ConcurrentStableList[HelpAnchorCandidate]) -> bool:
    """候选链中是否含已登记锚点（全局级不算锚点）。

    页面内帮助按钮显隐用「元数据是否登记锚点」判定（登记了就有入口，文章缺省提示「暂无帮助」），
    与命中判据 `matched` 分开：`anchor_found=True / matched=False` 即「有锚点无文章」。

    Args:
        candidates: 有序候选（首项最贴近当前上下文；末项恒为全局级）。

    Returns:
        bool: 除全局级外存在任一锚点即 True。
    """
    return any(candidate.help_key is not None for candidate in candidates)


async def resolve_help_context(
    *,
    index: HelpAnchorIndex,
    context: HelpContextInput,
    locale: str,
    resolver: BaseHelpContentResolver,
    request: Request | None = None,
    candidates: ConcurrentStableList[HelpAnchorCandidate] | None = None,
) -> HelpContentResult:
    """按候选链向内容侧解析（未命中返回空结果，不是错误）。

    Args:
        index: 锚点索引。
        context: 解析上下文入参。
        locale: 请求语言标识。
        resolver: 内容侧解析实现。
        request: 当前请求（透传给实现；可空）。
        candidates: 已构建的候选链（调用方需同时判定 `anchor_found` 时传入，避免重复构建）；
            未传则按索引与上下文现构建。

    Returns:
        HelpContentResult: 解析结果。
    """
    ordered = build_help_candidates(index, context) if candidates is None else candidates
    query = HelpContentQuery(
        locale=locale,
        candidates=ConcurrentStableFrozenList(ordered),
        module_key=context.module_key,
        form_key=context.form_key,
        action_code=context.action_code,
    )
    return await resolver.resolve(query, request=request)


def _module_anchors(
    index: HelpAnchorIndex, module_key: str, product_key: str | None
) -> ConcurrentStableList[HelpMenuAnchor]:
    """按模块段取菜单锚点（可选产品段过滤；平台优先后按主键升序）。

    Args:
        index: 锚点索引。
        module_key: 模块键。
        product_key: 产品段（None 表示不过滤）。

    Returns:
        ConcurrentStableList[HelpMenuAnchor]: 排序后的候选锚点。
    """
    matched: ConcurrentStableList[HelpMenuAnchor] = ConcurrentStableList(
        anchor
        for anchor in index.menus
        if anchor.module_key == module_key and (product_key is None or anchor.product == product_key)
    )
    return matched.sorted(key=lambda anchor: (0 if anchor.product == PLATFORM_PRODUCT_KEY else 1, anchor.model_id))


def _action_target(context: HelpContextInput) -> tuple[str | None, str]:
    """拆动作入参为「业务码 + 动作码」。

    入参可写动作码（`create`）或完整权限码（`user:create`）；带业务前缀且与 `form_key` 不一致时
    视为不匹配（不产生按钮候选，但仍可落到动作码全局兜底）。

    Args:
        context: 解析上下文入参（`action_code` 必非空）。

    Returns:
        tuple[str | None, str]: 业务码（缺省取 `form_key`）与动作码。
    """
    action_code = cast("str", context.action_code)
    business, separator, action = action_code.partition(":")
    if not separator:
        return context.form_key, action_code
    if context.form_key is not None and business != context.form_key:
        return None, action
    return business or None, action


def _clean(value: str | None) -> str | None:
    """去首尾空白；空串视为未提供。

    Args:
        value: 原始值。

    Returns:
        str | None: 归一值；未提供为 None。
    """
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
