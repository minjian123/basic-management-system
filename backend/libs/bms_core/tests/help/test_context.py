"""帮助五级候选链与解析编排（08_02；Kiwi 2521）。"""

import pytest
from fastapi import Request

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.help.content import (
    BaseHelpContentResolver,
    HelpArticle,
    HelpCategory,
    HelpContentQuery,
    HelpContentResult,
    HelpLevel,
)
from bms_core.help.context import HelpContextInput, build_help_candidates, has_anchor, resolve_help_context
from bms_core.help.index import HelpAnchorIndex, HelpMenuAnchor

pytestmark = pytest.mark.kiwi_id(2521)

_FORM_KEY = "probe_biz"
_FIELD_KEY = "probe_field"
_ACTION = "probe_create"
_FIELD_ANCHOR = "platform:probe_module:probe_biz:probe_field:"
_BUTTON_ANCHOR = "platform:probe_module:probe_biz::probe_create"
_ACTION_ANCHOR = "platform::::probe_create"
_FORM_ANCHOR = "platform:probe_module:probe_biz::"
_MODULE_ANCHOR = "platform:probe_module:::"
_BIZ_MODULE_ANCHOR = "biz:probe_module:::"


def _index() -> HelpAnchorIndex:
    """构造覆盖五级的锚点索引（模块级含平台与产品两条同名段）。

    Returns:
        HelpAnchorIndex: 锚点索引。
    """
    return HelpAnchorIndex(
        menus=ConcurrentStableFrozenList(
            [
                HelpMenuAnchor(product="biz", module_key="probe_module", help_key=_BIZ_MODULE_ANCHOR, model_id=20),
                HelpMenuAnchor(product="platform", module_key="probe_module", help_key=_MODULE_ANCHOR, model_id=10),
            ]
        ),
        forms=ConcurrentStableFrozenDict({_FORM_KEY: _FORM_ANCHOR}),
        fields=ConcurrentStableFrozenDict({(_FORM_KEY, _FIELD_KEY): _FIELD_ANCHOR}),
        buttons=ConcurrentStableFrozenDict({(_FORM_KEY, _ACTION): _BUTTON_ANCHOR}),
        actions=ConcurrentStableFrozenDict({_ACTION: _ACTION_ANCHOR}),
    )


def _context(**overrides: str | None) -> HelpContextInput:
    """构造完整上下文（按需覆盖单个入参）。

    Args:
        **overrides: 覆盖字段。

    Returns:
        HelpContextInput: 解析上下文。
    """
    values: ConcurrentStableDict[str, str | None] = ConcurrentStableDict(
        {
            "product_key": None,
            "module_key": "probe_module",
            "form_key": _FORM_KEY,
            "field_key": _FIELD_KEY,
            "action_code": _ACTION,
        }
    )
    for key, value in overrides.items():
        values.set(key, value)
    return HelpContextInput.of(
        product_key=values.get("product_key"),
        module_key=values.get("module_key"),
        form_key=values.get("form_key"),
        field_key=values.get("field_key"),
        action_code=values.get("action_code"),
    )


class _RecordingResolver(BaseHelpContentResolver):
    """记录查询并恒定返回给定结果的解析桩。"""

    def __init__(self, result: HelpContentResult) -> None:
        """初始化。

        Args:
            result: 恒定返回值。
        """
        self.queries: ConcurrentStableList[HelpContentQuery] = ConcurrentStableList()
        self._result = result

    async def resolve(self, query: HelpContentQuery, *, request: Request | None = None) -> HelpContentResult:
        """记录查询并返回结果。

        Args:
            query: 解析查询。
            request: 当前请求（忽略）。

        Returns:
            HelpContentResult: 恒定结果。
        """
        del request
        self.queries.add(query)
        return self._result


def test_candidates_follow_five_level_order() -> None:
    """完整上下文 → 候选按「字段 → 动作（按钮、兜底）→ 表单 → 模块 → 全局」排列。"""
    candidates = build_help_candidates(_index(), _context())
    assert [candidate.level for candidate in candidates] == [
        HelpLevel.FIELD,
        HelpLevel.ACTION,
        HelpLevel.ACTION,
        HelpLevel.FORM,
        HelpLevel.MODULE,
        HelpLevel.MODULE,
        HelpLevel.GLOBAL,
    ]
    assert [candidate.help_key for candidate in candidates] == [
        _FIELD_ANCHOR,
        _BUTTON_ANCHOR,
        _ACTION_ANCHOR,
        _FORM_ANCHOR,
        _MODULE_ANCHOR,
        _BIZ_MODULE_ANCHOR,
        None,
    ]


def test_empty_context_only_global_candidate() -> None:
    """入参全空 → 只剩全局候选（无元数据锚点）。"""
    candidates = build_help_candidates(_index(), HelpContextInput.of())
    assert [(candidate.level, candidate.help_key) for candidate in candidates] == [(HelpLevel.GLOBAL, None)]


def test_field_level_requires_form_key() -> None:
    """只给字段键（无表单键）→ 不产生字段候选，从动作级开始。"""
    candidates = build_help_candidates(_index(), _context(field_key=_FIELD_KEY, form_key=None))
    assert HelpLevel.FIELD not in [candidate.level for candidate in candidates]


def test_action_prefix_mismatch_skips_button_candidate() -> None:
    """动作入参带业务前缀且与表单键不一致 → 不产生按钮候选，仍保留动作码兜底。"""
    candidates = build_help_candidates(_index(), _context(action_code=f"other:{_ACTION}"))
    action_keys = [candidate.help_key for candidate in candidates if candidate.level is HelpLevel.ACTION]
    assert action_keys == [_ACTION_ANCHOR]

    full = build_help_candidates(_index(), _context(action_code=f"{_FORM_KEY}:{_ACTION}", form_key=None))
    full_action_keys = [candidate.help_key for candidate in full if candidate.level is HelpLevel.ACTION]
    assert full_action_keys == [_BUTTON_ANCHOR, _ACTION_ANCHOR]


def test_module_anchor_product_filter_and_platform_first() -> None:
    """模块级：未指定产品段时平台优先；指定产品段时只取该产品。"""
    default_keys = [
        candidate.help_key
        for candidate in build_help_candidates(_index(), _context())
        if candidate.level is HelpLevel.MODULE
    ]
    assert default_keys == [_MODULE_ANCHOR, _BIZ_MODULE_ANCHOR]

    filtered = [
        candidate.help_key
        for candidate in build_help_candidates(_index(), _context(product_key="biz"))
        if candidate.level is HelpLevel.MODULE
    ]
    assert filtered == [_BIZ_MODULE_ANCHOR]


def test_candidates_dedupe_same_anchor() -> None:
    """同一锚点只保留首次出现（动作码兜底与按钮锚点相同时不重复）。"""
    index = HelpAnchorIndex(
        buttons=ConcurrentStableFrozenDict({(_FORM_KEY, _ACTION): _ACTION_ANCHOR}),
        actions=ConcurrentStableFrozenDict({_ACTION: _ACTION_ANCHOR}),
    )
    candidates = build_help_candidates(index, _context(form_key=_FORM_KEY, field_key=None, module_key=None))
    assert [candidate.help_key for candidate in candidates].count(_ACTION_ANCHOR) == 1


async def test_resolve_help_context_passes_ordered_query() -> None:
    """解析编排把有序候选、语言与上下文原样交给内容侧，并返回其结果。"""
    result = HelpContentResult(
        level=HelpLevel.FIELD,
        help_key=_FIELD_ANCHOR,
        article=HelpArticle(article_id=1, title="字段帮助", content="<p>正文</p>", source="builtin"),
        categories=ConcurrentStableFrozenList([HelpCategory(category_id=1, name="系统管理", path="系统管理")]),
    )
    resolver = _RecordingResolver(result)
    resolved = await resolve_help_context(index=_index(), context=_context(), locale="zh-CN", resolver=resolver)
    assert resolved is result
    query = resolver.queries[0]
    assert query.locale == "zh-CN"
    assert query.form_key == _FORM_KEY
    assert query.action_code == _ACTION
    assert next(candidate.level for candidate in query.candidates) is HelpLevel.FIELD


def test_has_anchor_ignores_global_candidate() -> None:
    """锚点判定：除全局级外任一候选有锚点即真（全空上下文只剩全局级为假）。"""
    assert has_anchor(build_help_candidates(_index(), _context())) is True
    assert has_anchor(build_help_candidates(_index(), HelpContextInput.of())) is False


async def test_resolve_help_context_accepts_prebuilt_candidates() -> None:
    """调用方已构建候选时直接复用（不重复构建，供服务层同时判定 anchor_found）。"""
    candidates = build_help_candidates(_index(), _context())
    resolver = _RecordingResolver(HelpContentResult())
    await resolve_help_context(
        index=_index(),
        context=_context(),
        locale="zh-CN",
        resolver=resolver,
        candidates=candidates,
    )
    query = resolver.queries[0]
    assert [candidate.help_key for candidate in query.candidates] == [candidate.help_key for candidate in candidates]


def test_context_input_normalizes_whitespace() -> None:
    """入参去首尾空白；空串视为未提供。"""
    context = HelpContextInput.of(module_key=" probe_module ", form_key="  ", action_code=None)
    assert context.module_key == "probe_module"
    assert context.form_key is None
    assert context.action_code is None
