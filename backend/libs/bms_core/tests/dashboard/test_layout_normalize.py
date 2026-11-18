"""工作台布局纯函数：归一 / 严格校验 / 最小布局 / 过滤 / JSON 往返（Kiwi 2528）。"""

import json

import pytest

from bms_core.core.concurrent import ConcurrentStableFrozenDict, ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.dashboard.layout import (
    CHART_TYPES,
    GRID_COLUMNS,
    MAX_LAYOUT_CARDS,
    CardSize,
    filter_placements,
    is_layout_empty,
    is_valid_card_code,
    layout_json,
    load_layout_config,
    minimal_layout,
    normalize_layout,
    parse_layout,
)

pytestmark = pytest.mark.kiwi_id(2528)


def _sizes(*items: tuple[str, int, int]) -> ConcurrentStableFrozenDict[str, CardSize]:
    """构造卡片尺寸映射。

    Args:
        *items: `(code, width, height)`。

    Returns:
        ConcurrentStableFrozenDict[str, CardSize]: 尺寸映射。
    """
    return ConcurrentStableFrozenDict({code: CardSize(code=code, width=w, height=h) for code, w, h in items})


def _reasons(issues: object) -> ConcurrentStableList[str]:
    """取问题项原因清单。

    Args:
        issues: 问题项集合。

    Returns:
        ConcurrentStableList[str]: 原因清单。
    """
    return ConcurrentStableList(issue.reason for issue in issues)  # type: ignore[attr-defined]


def test_card_code_pattern() -> None:
    """卡片标识形态：合法 / 大写 / 短 / 连字符 / 空。"""
    assert is_valid_card_code("todo")
    assert is_valid_card_code("quick_links")
    assert not is_valid_card_code("Todo")
    assert not is_valid_card_code("a")
    assert not is_valid_card_code("quick-links")
    assert not is_valid_card_code("")


def test_normalize_rejects_non_structure() -> None:
    """结构非法：非对象 / `cards` 非数组 → 空布局。"""
    assert is_layout_empty(normalize_layout(None, sizes=_sizes()))
    assert is_layout_empty(normalize_layout({"cards": "x"}, sizes=_sizes()))
    assert is_layout_empty(normalize_layout([1, 2], sizes=_sizes()))


def test_normalize_skips_invalid_items_and_duplicates() -> None:
    """非法项与非对象项丢弃；重复标识保首个。"""
    raw = {
        "cards": [
            "bad",
            {"code": "Todo"},
            {"code": "todo", "x": 0, "y": 0, "w": 4, "h": 2},
            {"code": "todo", "x": 4, "y": 0, "w": 4, "h": 2},
        ]
    }
    layout = normalize_layout(raw, sizes=_sizes(("todo", 4, 2)))
    assert [item.code for item in layout.cards] == ["todo"]
    assert layout.cards[0].x == 0


def test_normalize_clamps_and_accepts_numeric_strings() -> None:
    """容错归一：越界夹取、数字字符串与整值浮点接受、布尔与非整值浮点视为非法。"""
    raw = {
        "cards": [
            {"code": "todo", "x": 99, "y": -3, "w": 40, "h": 1},
            {"code": "notice", "x": "3", "y": 2.0, "w": 6.0, "h": 3},
            {"code": "help", "w": True, "h": 2.5},
        ]
    }
    layout = normalize_layout(raw, sizes=_sizes(("todo", 4, 2), ("notice", 4, 2), ("help", 2, 2)))
    todo, notice, help_card = layout.cards
    assert (todo.x, todo.y, todo.w, todo.h) == (0, 0, GRID_COLUMNS, 2)
    assert (notice.x, notice.y, notice.w, notice.h) == (3, 2, 6, 3)
    assert (help_card.code, help_card.w, help_card.h) == ("help", 2, 2)


def test_normalize_flow_placement() -> None:
    """缺省位置按行流式排布：满 12 列换行，行高取该行最大高度。"""
    raw = {"cards": [{"code": "ca"}, {"code": "cb"}, {"code": "cc"}, {"code": "cd"}]}
    sizes = _sizes(("ca", 6, 2), ("cb", 6, 4), ("cc", 4, 2), ("cd", 4, 2))
    layout = normalize_layout(raw, sizes=sizes)
    placed = [(item.code, item.x, item.y) for item in layout.cards]
    assert placed == [("ca", 0, 0), ("cb", 6, 0), ("cc", 0, 4), ("cd", 4, 4)]


def test_normalize_visible_flag() -> None:
    """`visible` 非布尔取默认 True；显式 false 保留。"""
    raw = {"cards": [{"code": "todo", "visible": "no"}, {"code": "notice", "visible": False}]}
    layout = normalize_layout(raw, sizes=_sizes(("todo", 4, 2), ("notice", 4, 2)))
    assert layout.cards[0].visible is True
    assert layout.cards[1].visible is False
    assert is_layout_empty(layout) is False


def test_parse_strict_reports_structure_and_limits() -> None:
    """严格解析：结构非法 / 超量 / 重复 / 越界 / 位置非法 / 尺寸非法全部产出问题项。"""
    _layout, issues = parse_layout("bad", sizes=_sizes())
    assert _reasons(issues) == ["structure"]

    too_many = {"cards": [{"code": f"c{index}"} for index in range(MAX_LAYOUT_CARDS + 1)]}
    _layout, issues = parse_layout(too_many, sizes=_sizes())
    assert "too-many-cards" in _reasons(issues)

    raw = {
        "cards": [
            "bad",
            {"code": "Bad"},
            {"code": "todo", "w": 1, "h": 9},
            {"code": "todo"},
            {"code": "notice", "x": 11, "w": 4},
            {"code": "help", "x": "x", "y": -2},
            {"code": "stats", "w": 1.5},
        ]
    }
    _layout, issues = parse_layout(raw, sizes=_sizes(("todo", 4, 2), ("notice", 4, 2), ("help", 2, 2)))
    reasons = _reasons(issues)
    for expected in (
        "structure",
        "code-invalid",
        "width-out-of-range",
        "height-out-of-range",
        "duplicate-code",
        "position-out-of-range",
        "size-invalid",
    ):
        assert expected in reasons


def test_parse_strict_detects_overlap() -> None:
    """严格解析：两张可见卡矩形相交 → `overlap`；不可见卡不参与。"""
    raw = {
        "cards": [
            {"code": "todo", "x": 0, "y": 0, "w": 6, "h": 2},
            {"code": "notice", "x": 2, "y": 1, "w": 6, "h": 2},
        ]
    }
    _layout, issues = parse_layout(raw, sizes=_sizes(("todo", 6, 2), ("notice", 6, 2)))
    assert "overlap" in _reasons(issues)

    hidden = {
        "cards": [
            {"code": "todo", "x": 0, "y": 0, "w": 6, "h": 2},
            {"code": "notice", "x": 2, "y": 1, "w": 6, "h": 2, "visible": False},
        ]
    }
    _layout, issues = parse_layout(hidden, sizes=_sizes(("todo", 6, 2), ("notice", 6, 2)))
    assert "overlap" not in _reasons(issues)


def test_parse_strict_accepts_valid_layout() -> None:
    """严格解析：合法布局零问题项。"""
    raw = {"cards": [{"code": "todo", "x": 0, "y": 0, "w": 4, "h": 2}, {"code": "notice", "x": 4, "y": 0}]}
    layout, issues = parse_layout(raw, sizes=_sizes(("todo", 4, 2), ("notice", 4, 2)))
    assert list(issues) == []
    assert [item.code for item in layout.cards] == ["todo", "notice"]


def test_minimal_layout_wraps_rows() -> None:
    """最小布局：每行不超 12 列，满行换行且行高取本行最大高度。"""
    sizes = ConcurrentStableList(
        (
            CardSize(code="ca", width=6, height=2),
            CardSize(code="cb", width=6, height=4),
            CardSize(code="cc", width=12, height=2),
            CardSize(code="cd", width=4, height=2),
        )
    )
    layout = minimal_layout(ConcurrentStableFrozenList(sizes))
    placed = [(item.code, item.x, item.y) for item in layout.cards]
    assert placed == [("ca", 0, 0), ("cb", 6, 0), ("cc", 0, 4), ("cd", 0, 6)]


def test_filter_placements_reports_unknown_and_disabled() -> None:
    """过滤：未注册 → `card_unknown`；已停用 → `card_disabled`；其余保留。"""
    raw = {"cards": [{"code": "todo"}, {"code": "notice"}, {"code": "ghost"}]}
    layout = normalize_layout(raw, sizes=_sizes(("todo", 4, 2), ("notice", 4, 2)))
    kept, issues = filter_placements(layout, enabled=ConcurrentStableFrozenDict({"todo": True, "notice": False}))
    assert [item.code for item in kept.cards] == ["todo"]
    assert sorted(_reasons(issues)) == ["card_disabled", "card_unknown"]


def test_layout_json_round_trip() -> None:
    """落库 JSON 与读取还原一致；非法 JSON 回退空布局。"""
    raw = {"cards": [{"code": "todo", "x": 0, "y": 0, "w": 4, "h": 2, "visible": True}]}
    layout = normalize_layout(raw, sizes=_sizes(("todo", 4, 2)))
    text = layout_json(layout)
    assert json.loads(text)["cards"][0]["code"] == "todo"
    restored = normalize_layout(load_layout_config(text), sizes=_sizes(("todo", 4, 2)))
    assert restored == layout
    assert load_layout_config("{not json") == {}


def test_chart_types_match_frontend_whitelist() -> None:
    """图表类型白名单含前端全部类型（同值口径）。"""
    assert set(CHART_TYPES) == {
        "line",
        "area",
        "bar",
        "hbar",
        "stacked_bar",
        "pie",
        "doughnut",
        "scatter",
        "funnel",
        "radar",
        "gauge",
        "table",
        "map",
    }


def test_normalize_reports_position_and_wraps_rows() -> None:
    """非整数 `y` 记位置非法；缺省 `x` 且余宽不足时换行（行高累计）。"""
    _layout, issues = parse_layout(
        {"cards": [{"code": "todo", "x": 0, "y": "x"}, {"code": "notice", "y": 0}]},
        sizes=_sizes(("todo", 4, 2), ("notice", 4, 2)),
    )
    assert "position-out-of-range" in _reasons(issues)

    sizes = _sizes(("ca", 4, 2), ("cb", 4, 3), ("cc", 6, 2))
    flowed = normalize_layout({"cards": [{"code": "ca"}, {"code": "cb"}, {"code": "cc"}]}, sizes=sizes)
    placed = [(item.code, item.x, item.y) for item in flowed.cards]
    assert placed == [("ca", 0, 0), ("cb", 4, 0), ("cc", 0, 3)]


def test_normalize_tolerates_too_many_cards() -> None:
    """容错归一不因超量提前返回（仍解析全部卡片，由保存期严格校验拒收）。"""
    raw = {"cards": [{"code": f"c{index}"} for index in range(MAX_LAYOUT_CARDS + 2)]}
    layout = normalize_layout(raw, sizes=_sizes())
    assert len(layout.cards) == MAX_LAYOUT_CARDS + 2
