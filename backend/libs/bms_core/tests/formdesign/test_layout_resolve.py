"""布局归一与三级解析（Kiwi 2526）：结构容错 / 空回退 / 逐级回退 / 失效引用。"""

from typing import cast

import pytest

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.formdesign.layout import (
    DEFAULT_LABEL_WIDTH,
    DEFAULT_LAYOUT_COLUMNS,
    DEFAULT_SECTION_KEY,
    FormLayout,
    LayoutDictAdvanced,
    LayoutMain,
    collect_field_keys,
    default_layout,
    dump_layout_config,
    empty_layout,
    find_duplicate_fields,
    is_layout_empty,
    layout_to_config,
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
    config = cast(
        "dict[str, object]",
        {"main": {"sections": [{"key": "s1", "fields": ["ghost", "off"]}, {"key": "s2", "fields": []}]}},
    )
    layout = normalize_layout(config)
    issues = validate_layout_refs(
        layout,
        known_keys=ConcurrentStableFrozenList[str](("off",)),
        disabled_keys=ConcurrentStableFrozenList[str](("off",)),
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
    levels = ConcurrentStableFrozenDict({"platform": platform, "tenant": tenant, "role": role})
    hit, source = resolve_layout_for_level(levels, "role")
    assert hit is role and source == "role"
    only_tenant = ConcurrentStableFrozenDict({"platform": platform, "tenant": tenant})
    hit2, source2 = resolve_layout_for_level(only_tenant, "role")
    assert hit2 is tenant and source2 == "tenant"
    empty = ConcurrentStableFrozenDict({"platform": empty_layout()})
    hit3, source3 = resolve_layout_for_level(empty, "role")
    assert hit3 is None and source3 == "empty"


def test_layout_section_list_is_frozen() -> None:
    """归一结果是不可变形态（防下游误改共享布局）。"""
    layout = normalize_layout({"main": {"sections": [{"key": "s", "fields": ["a"]}]}})
    with pytest.raises(TypeError):
        layout.main.sections.add(None)  # type: ignore[attr-defined]


del ConcurrentStableList


def test_normalize_tolerates_missing_and_invalid_structures() -> None:
    """非映射输入回落空布局；分区 / 分组里的非映射项跳过；缺键自动生成；非法宽度回落缺省。"""
    assert normalize_layout("not-a-mapping") == empty_layout()
    assert normalize_layout({"main": "not-a-mapping"}) == empty_layout()
    assert len(normalize_field_refs(None)) == 0
    assert len(normalize_detail_columns(None)) == 0
    dirty = cast(
        "dict[str, object]",
        {
            "main": {
                "labelWidth": "abc",
                "sections": [
                    "junk",
                    {
                        "columns": True,
                        "title": 5,
                        "fields": ["a"],
                        "groups": ["junk", {"title": 3, "fields": ["b", {"key": "c", "width": []}]}],
                    },
                ],
            },
            "detail": {"columns": "not-a-list"},
            "dictAdvanced": {"operators": "not-a-list"},
        },
    )
    layout = normalize_layout(dirty)
    assert layout.main.label_width == DEFAULT_LABEL_WIDTH
    assert len(layout.main.sections) == 1
    section = layout.main.sections[0]
    assert section.key.startswith("section-2")
    assert section.title == ""
    assert section.columns == DEFAULT_LAYOUT_COLUMNS
    assert section.groups[0].key.startswith("section-2-g2")
    assert section.groups[0].title == ""
    assert [ref.key for ref in section.groups[0].fields] == ["b", "c"]
    assert layout.detail is None
    assert layout.dict_advanced is None


def test_clamp_int_fallbacks() -> None:
    """宽度夹取：布尔 / 非数值回落缺省，数值型字符串按整数解析。"""
    assert normalize_layout({"main": {"labelWidth": True}}).main.label_width == DEFAULT_LABEL_WIDTH
    assert normalize_layout({"main": {"labelWidth": [1, 2]}}).main.label_width == DEFAULT_LABEL_WIDTH
    assert normalize_layout({"main": {"labelWidth": "150"}}).main.label_width == 150
    assert normalize_layout({"main": {"labelWidth": 90.6}}).main.label_width == 90


def test_layout_to_config_serializes_groups_detail_and_advanced() -> None:
    """配置序列化覆盖分组 / 明细列（带与不带宽度）/ 字典高级查询四段。"""
    layout = normalize_layout(
        {
            "main": {
                "labelWidth": 120,
                "sections": [
                    {
                        "key": "s",
                        "fields": ["a"],
                        "groups": [{"key": "g", "title": "组", "fields": ["b", {"key": "c", "colSpan": True}]}],
                    }
                ],
            },
            "detail": {"columns": [{"key": "d"}, {"key": "e", "width": 200}]},
            "dictAdvanced": {"fields": ["f"], "operators": ["eq"], "columns": ["g"], "scheme": "advanced"},
        }
    )
    config = layout_to_config(layout)
    main = cast("dict[str, object]", config["main"])
    assert main["labelWidth"] == 120
    sections = cast("list[dict[str, object]]", main["sections"])
    group = cast("list[dict[str, object]]", sections[0]["groups"])[0]
    assert group["title"] == "组"
    group_fields = cast("list[dict[str, object]]", group["fields"])
    assert group_fields[1]["colSpan"] is True
    detail_columns = cast("list[dict[str, object]]", cast("dict[str, object]", config["detail"])["columns"])
    assert detail_columns[0]["key"] == "d"
    assert "width" not in detail_columns[0]
    assert detail_columns[1]["width"] == 200
    advanced = cast("dict[str, object]", config["dictAdvanced"])
    assert advanced["fields"] == ["f"]
    assert advanced["operators"] == ["eq"]
    assert advanced["columns"] == ["g"]
    assert advanced["scheme"] == "advanced"


def test_is_layout_empty_covers_none_groups_and_general_collection() -> None:
    """空布局判定：None 为空、分组内引用也算非空。"""
    assert is_layout_empty(None) is True
    grouped = normalize_layout({"main": {"sections": [{"key": "s", "groups": [{"key": "g", "fields": ["a"]}]}]}})
    assert is_layout_empty(grouped) is False
    assert len(collect_field_keys(None)) == 0


def test_resolve_layout_for_level_tenant_and_platform() -> None:
    """租户层级与平台层级的回退顺序。"""
    platform = normalize_layout({"main": {"sections": [{"key": "p", "fields": ["a"]}]}})
    tenant = normalize_layout({"main": {"sections": [{"key": "t", "fields": ["a"]}]}})
    levels = ConcurrentStableFrozenDict({"platform": platform, "tenant": tenant})
    hit, source = resolve_layout_for_level(levels, "tenant")
    assert hit is tenant and source == "tenant"
    hit2, source2 = resolve_layout_for_level(levels, "platform")
    assert hit2 is platform and source2 == "platform"


def test_normalize_handles_columns_string_and_formlayout_input() -> None:
    """列数为非数值字符串回落缺省；已归一的 `FormLayout` 可再次归一（幂等）。"""
    layout = normalize_layout({"main": {"sections": [{"key": "s", "columns": "abc", "fields": ["a"]}]}})
    assert layout.main.sections[0].columns == DEFAULT_LAYOUT_COLUMNS
    assert normalize_layout(layout) == layout


def test_normalize_field_refs_ignores_objects_without_key() -> None:
    """引用对象缺 `key` / `key` 非非空字符串时视为无效引用（跳过）。"""
    refs = normalize_field_refs([{"key": ""}, {"colSpan": True}, {"key": 5}, "a"])
    assert [ref.key for ref in refs] == ["a"]


def test_normalize_skips_empty_query_and_keeps_advanced_partial() -> None:
    """查询区无引用则不建查询区；字典高级查询只配 scheme 时其余段不下发。"""
    layout = normalize_layout(
        {"main": {"sections": []}, "query": {"fields": []}, "dictAdvanced": {"scheme": "advanced"}}
    )
    assert layout.query is None
    config = layout_to_config(layout)
    assert config["dictAdvanced"] == {"scheme": "advanced"}


def test_layout_to_config_skips_empty_advanced_block() -> None:
    """四段全空的字典高级查询不下发（`dictAdvanced` 键不出现）。"""
    layout = FormLayout(
        main=LayoutMain(label_position="top"),
        dict_advanced=LayoutDictAdvanced(),
    )
    assert "dictAdvanced" not in layout_to_config(layout)


def test_is_layout_empty_walks_sections_and_groups() -> None:
    """多个分区时逐个走：无字段的分区继续看下一个，分组内有字段即非空。"""
    raw = cast(
        "dict[str, object]",
        {
            "main": {
                "sections": [
                    {"key": "s1", "groups": [{"key": "g1", "fields": []}]},
                    {"key": "s2", "groups": [{"key": "g2", "fields": ["a"]}]},
                ]
            }
        },
    )
    layout = normalize_layout(raw)
    assert is_layout_empty(layout) is False
    assert list(collect_field_keys(layout)) == ["a"]


def test_default_layout_skips_items_without_usable_key() -> None:
    """默认栅格跳过无键 / 键非字符串的字段项。"""
    grid = default_layout(
        ConcurrentStableFrozenList(
            (
                ConcurrentStableDict({"key": ""}),
                ConcurrentStableDict({"key": 5}),
                ConcurrentStableDict({"key": "ok"}),
            )
        )
    )
    assert [ref.key for ref in grid.main.sections[0].fields] == ["ok"]


def test_duplicate_fields_across_sections_are_reported() -> None:
    """跨分区重复引用可检出（同一键出现三次只报一次），并计入布局问题清单。"""
    layout = normalize_layout(
        {
            "main": {
                "sections": [
                    {"key": "s1", "fields": ["a"]},
                    {"key": "s2", "fields": ["a"]},
                    {"key": "s3", "fields": ["a"]},
                ]
            }
        }
    )
    assert list(find_duplicate_fields(layout)) == ["a"]
    issues = validate_layout_refs(
        layout,
        known_keys=ConcurrentStableFrozenList[str](("a",)),
        disabled_keys=ConcurrentStableFrozenList[str](()),
    )
    assert [issue.kind for issue in issues] == ["duplicate-field"]
