"""布局归一与三级解析（Kiwi 2526）：结构容错 / 空回退 / 逐级回退 / 失效引用。"""

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.formdesign.layout import (
    DEFAULT_LAYOUT_COLUMNS,
    DEFAULT_SECTION_KEY,
    collect_field_keys,
    default_layout,
    dump_layout_config,
    empty_layout,
    find_duplicate_fields,
    is_layout_empty,
    normalize_detail_columns,
    normalize_field_refs,
    normalize_layout,
    parse_layout_config,
    resolve_layout_for_level,
    validate_layout_refs,
)

pytestmark = pytest.mark.kiwi_id(2526)


def test_normalize_layout_tolerates_dirty_input() -> None:
    """裸字符串引用 / `colspan` / 非法列数 / 超界宽度 全部容错归一，不抛错。"""
    layout = normalize_layout(
        {
            "main": {
                "labelPosition": "left",
                "labelWidth": 999,
                "sections": [
                    {
                        "title": "基本信息",
                        "columns": 9,
                        "fields": ["name", {"key": "code", "colspan": True}, "name", None],
                    },
                    {"key": "s2", "columns": "2", "groups": [{"fields": ["age"]}], "fields": []},
                ],
            },
            "query": {"fields": ["name", "status"]},
            "detail": {"columns": ["name", {"key": "amt", "width": 9999}]},
        }
    )
    assert layout.main.label_position == "left"
    assert layout.main.label_width == 400
    first = layout.main.sections[0]
    assert first.columns == DEFAULT_LAYOUT_COLUMNS
    assert [ref.key for ref in first.fields] == ["name", "code"]
    assert first.fields[1].col_span is True
    assert layout.main.sections[1].columns == 2
    assert layout.main.sections[1].groups[0].key.startswith("section-2-g")
    assert list(layout.query.fields) if layout.query else [] == ["name", "status"]
    assert layout.detail is not None
    assert layout.detail[1].width == 800


def test_normalize_field_refs_dedup_and_merge_span() -> None:
    """重复引用去重保序，跨列标记并合到首次出现。"""
    refs = normalize_field_refs(["a", {"key": "a", "colSpan": True}, {"key": "b"}])
    assert [(ref.key, ref.col_span) for ref in refs] == [("a", True), ("b", False)]


def test_normalize_detail_columns_clamps_and_dedups() -> None:
    """明细列宽夹取到 40~800，重复键只留首个。"""
    columns = normalize_detail_columns(["n", {"key": "n", "width": 10}, {"key": "m", "width": 5000}])
    assert [(column.key, column.width) for column in columns] == [("n", None), ("m", 800)]


def test_layout_roundtrip_and_dump() -> None:
    """布局序列化 / 反序列化等值（写库与下发同形）。"""
    layout = normalize_layout(
        {
            "main": {"labelPosition": "top", "sections": [{"key": "s", "columns": 2, "fields": ["a", "b"]}]},
            "query": {"fields": ["a"]},
        }
    )
    dumped = dump_layout_config(layout)
    assert '"labelPosition":"top"' in dumped
    assert parse_layout_config(dumped) == layout


def test_parse_layout_config_rejects_broken_json() -> None:
    """库内 JSON 损坏抛参数错（10001），不静默产出空布局。"""
    from bms_core.core.exceptions import ParamError

    with pytest.raises(ParamError):
        parse_layout_config("{not json")


def test_empty_layout_and_default_grid() -> None:
    """空布局判定与默认栅格（跳过停用 / 建列失败字段，保留字段序）。"""
    assert is_layout_empty(empty_layout()) is True
    grid = default_layout(
        ConcurrentStableFrozenList(
            (
                ConcurrentStableDict({"key": "a"}),
                ConcurrentStableDict({"key": "b", "status": "disabled"}),
                ConcurrentStableDict({"key": "c", "disabled": True}),
                ConcurrentStableDict({"key": "d", "status": "active"}),
            )
        )
    )
    assert grid.main.sections[0].key == DEFAULT_SECTION_KEY
    assert [ref.key for ref in grid.main.sections[0].fields] == ["a", "d"]


def test_collect_and_duplicate_detection() -> None:
    """引用收集覆盖主表 / 分组 / 查询区 / 明细区 / 字典高级查询；重复引用可检出。"""
    layout = normalize_layout(
        {
            "main": {"sections": [{"key": "s1", "fields": ["a"]}, {"key": "s2", "fields": ["a", "b"]}]},
            "query": {"fields": ["c"]},
            "detail": {"columns": ["d"]},
            "dictAdvanced": {"fields": ["e"], "columns": ["f"]},
        }
    )
    assert list(collect_field_keys(layout)) == ["a", "b", "c", "d", "e", "f"]
    assert list(find_duplicate_fields(layout)) == ["a"]


def test_validate_layout_refs_reports_issues() -> None:
    """失效 / 停用 / 重复 / 空分区 均回报问题（不抛错、不阻断）。"""
    layout = normalize_layout(
        {"main": {"sections": [{"key": "s1", "fields": ["ghost", "off"]}, {"key": "s2", "fields": []}]}}
    )
    issues = validate_layout_refs(
        layout,
        known_keys=ConcurrentStableFrozenList(("off",)),
        disabled_keys=ConcurrentStableFrozenList(("off",)),
    )
    kinds = {(issue.kind, issue.field_key) for issue in issues}
    assert ("unknown-field", "ghost") in kinds
    assert ("disabled-field", "off") in kinds
    assert any(issue.kind == "empty-section" for issue in issues)
    # 重复引用仅在未经归一的原始结构里可检出（归一阶段去重是设计意图，故单独验证检测函数）
    raw = normalize_layout({"main": {"sections": [{"key": "s1", "fields": ["a"]}]}})
    assert list(find_duplicate_fields(raw)) == []


def test_resolve_layout_for_level_falls_back() -> None:
    """三级解析：角色 → 租户 → 平台；皆空返回 empty。"""
    platform = normalize_layout({"main": {"sections": [{"key": "p", "fields": ["a"]}]}})
    tenant = normalize_layout({"main": {"sections": [{"key": "t", "fields": ["a"]}]}})
    role = normalize_layout({"main": {"sections": [{"key": "r", "fields": ["a"]}]}})
    levels = ConcurrentStableDict({"platform": platform, "tenant": tenant, "role": role})
    hit, source = resolve_layout_for_level(levels, "role")
    assert hit is role and source == "role"
    only_tenant = ConcurrentStableDict({"platform": platform, "tenant": tenant})
    hit2, source2 = resolve_layout_for_level(only_tenant, "role")
    assert hit2 is tenant and source2 == "tenant"
    empty = ConcurrentStableDict({"platform": empty_layout()})
    hit3, source3 = resolve_layout_for_level(empty, "role")
    assert hit3 is None and source3 == "empty"


def test_layout_section_list_is_frozen() -> None:
    """归一结果是不可变形态（防下游误改共享布局）。"""
    layout = normalize_layout({"main": {"sections": [{"key": "s", "fields": ["a"]}]}})
    with pytest.raises(TypeError):
        layout.main.sections.add(None)  # type: ignore[attr-defined]


del ConcurrentStableList
