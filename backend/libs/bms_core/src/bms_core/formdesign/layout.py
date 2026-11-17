"""表单布局领域纯函数：结构归一 / 空布局回退 / 三级解析 / 失效引用（框架无关、无 IO）。

与前端 `frontend/packages/core/src/domain/form-layout.ts` **同语义同常量**（设计器产出与渲染输入同形）
——跨端口径一致，任一侧改动须同步另一侧（前端契约另有 `layoutEqual` 等设计器专用函数，后端不需要）。

**装载容错**（与前端一致，避免配置漂移导致页面白屏）：

- 裸字符串字段引用归一为 `{key}`；`colspan` 与 `colSpan` 两种写法都认；
- 分区 / 分组缺 `key` 时按序号生成；`columns` 非法（非 1/2/3）回落 3；
- 空键 / `null` 引用剔除，不抛错；重复引用去重保序并合跨列标记。
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import ParamError
from bms_core.core.objects import BaseValueObject
from bms_core.core.serialization import normalize_collections

__all__ = [
    "DEFAULT_LABEL_WIDTH",
    "DEFAULT_LAYOUT_COLUMNS",
    "DEFAULT_SECTION_KEY",
    "DETAIL_WIDTH_RANGE",
    "LABEL_WIDTH_RANGE",
    "SECTION_COLUMNS",
    "SECTION_KEY_PREFIX",
    "FormLayout",
    "LayoutDetailColumn",
    "LayoutDictAdvanced",
    "LayoutFieldRef",
    "LayoutGroup",
    "LayoutIssue",
    "LayoutIssueKind",
    "LayoutMain",
    "LayoutQuery",
    "LayoutSection",
    "collect_field_keys",
    "default_layout",
    "empty_layout",
    "find_duplicate_fields",
    "is_layout_empty",
    "normalize_columns",
    "normalize_detail_columns",
    "normalize_field_refs",
    "normalize_layout",
    "parse_layout_config",
    "resolve_layout_for_level",
    "validate_layout_refs",
]

SECTION_COLUMNS: tuple[int, int, int] = (1, 2, 3)
"""分区列数白名单。"""

DEFAULT_LAYOUT_COLUMNS = 3
"""空布局回退与非法列数的缺省列数。"""

DEFAULT_LABEL_WIDTH = 100
"""标签宽度缺省值（`label_position == "left"` 时生效）。"""

LABEL_WIDTH_RANGE: tuple[int, int] = (0, 400)
"""标签宽度上下限（像素）。"""

DETAIL_WIDTH_RANGE: tuple[int, int] = (40, 800)
"""明细列宽上下限（像素）。"""

DEFAULT_SECTION_KEY = "default"
"""空布局回退的分区键（渲染与设计同源）。"""

SECTION_KEY_PREFIX = "section-"
"""自动建分区的键前缀。"""


@dataclass(frozen=True)
class LayoutFieldRef:
    """字段引用（分区内顺序与跨列）。"""

    key: str
    """字段键。"""
    col_span: bool = False
    """是否跨整行。"""


@dataclass(frozen=True)
class LayoutGroup:
    """分区内分组（二级组织，可选）。"""

    key: str
    """分组键。"""
    title: str
    """分组标题。"""
    fields: ConcurrentStableFrozenList[LayoutFieldRef] = field(default_factory=lambda: ConcurrentStableFrozenList(()))
    """分组内字段引用（数组序即顺序）。"""


@dataclass(frozen=True)
class LayoutSection:
    """布局分区。"""

    key: str
    """分区键。"""
    title: str
    """分区标题。"""
    columns: int
    """列数（1 / 2 / 3）。"""
    fields: ConcurrentStableFrozenList[LayoutFieldRef] = field(default_factory=lambda: ConcurrentStableFrozenList(()))
    """字段引用（数组序即顺序）。"""
    groups: ConcurrentStableFrozenList[LayoutGroup] = field(default_factory=lambda: ConcurrentStableFrozenList(()))
    """可选分组（空表示无分组）。"""


@dataclass(frozen=True)
class LayoutMain:
    """主表结构。"""

    label_position: str
    """标签位置（`top` / `left`）。"""
    sections: ConcurrentStableFrozenList[LayoutSection] = field(default_factory=lambda: ConcurrentStableFrozenList(()))
    """分区列表。"""
    label_width: int | None = None
    """标签宽度（`left` 时生效；缺省不写）。"""


@dataclass(frozen=True)
class LayoutQuery:
    """查询表单区（列表页筛选）。"""

    fields: ConcurrentStableFrozenList[str] = field(default_factory=lambda: ConcurrentStableFrozenList(()))
    """查询字段键（数组序即顺序）。"""


@dataclass(frozen=True)
class LayoutDetailColumn:
    """明细区列。"""

    key: str
    """列字段键。"""
    width: int | None = None
    """列宽（像素；缺省不写）。"""


@dataclass(frozen=True)
class LayoutDictAdvanced:
    """字典高级查询界面配置（可选）。"""

    fields: ConcurrentStableFrozenList[str] = field(default_factory=lambda: ConcurrentStableFrozenList(()))
    """属性字段。"""
    operators: ConcurrentStableFrozenList[str] = field(default_factory=lambda: ConcurrentStableFrozenList(()))
    """操作符集合。"""
    columns: ConcurrentStableFrozenList[str] = field(default_factory=lambda: ConcurrentStableFrozenList(()))
    """结果列。"""
    scheme: str | None = None
    """默认方案标识。"""


@dataclass(frozen=True)
class FormLayout:
    """布局模型（`sys_form_layout.layout_config` 的结构；运行态确定值）。"""

    main: LayoutMain
    """主表。"""
    query: LayoutQuery | None = None
    """查询表单区（缺省表示未配置）。"""
    detail: ConcurrentStableFrozenList[LayoutDetailColumn] | None = None
    """明细区列（缺省表示未配置）。"""
    dict_advanced: LayoutDictAdvanced | None = None
    """字典高级查询界面配置（缺省表示未配置）。"""


LayoutIssueKind = str
"""布局校验问题种类标识（`unknown-field` / `disabled-field` / `duplicate-field` / `empty-section` / `columns`）。"""


@dataclass(frozen=True)
class LayoutIssue(BaseValueObject):
    """布局校验问题（保存期告警不阻断，渲染期跳过）。"""

    kind: LayoutIssueKind
    """问题种类。"""
    message: str
    """说明（中文；不进契约文案，前端按 kind 做 i18n）。"""
    section_key: str | None = None
    """涉事分区键（可选）。"""
    field_key: str | None = None
    """涉事字段键（可选）。"""


def _ref_key(raw: object) -> str | None:
    """取字段引用键（兼容字符串与 `{key}` 两种写法）。

    Args:
        raw: 原始引用。

    Returns:
        str | None: 去空白后的键；空返回 None。
    """
    if isinstance(raw, str):
        return raw if raw.strip() != "" else None
    if isinstance(raw, Mapping):
        value = cast("dict[str, object]", raw).get("key")
        if isinstance(value, str) and value.strip() != "":
            return value
    return None


def _ref_col_span(raw: object) -> bool:
    """是否跨列（兼容 `colSpan` / `colspan` 两种写法）。

    Args:
        raw: 原始引用。

    Returns:
        bool: 跨列为 True。
    """
    if not isinstance(raw, Mapping):
        return False
    record = cast("dict[str, object]", raw)
    return record.get("colSpan") is True or record.get("colspan") is True


def normalize_field_refs(refs: object) -> ConcurrentStableFrozenList[LayoutFieldRef]:
    """归一字段引用列表（剔空键、去重保序、并合跨列标记）。

    Args:
        refs: 原始引用列表（可含字符串、`{key}`、`null`）。

    Returns:
        ConcurrentStableFrozenList[LayoutFieldRef]: 归一后的引用（插入序）。
    """
    result: ConcurrentStableList[LayoutFieldRef] = ConcurrentStableList()
    positions: ConcurrentStableDict[str, int] = ConcurrentStableDict()
    if not isinstance(refs, list):
        return ConcurrentStableFrozenList(())
    for item in cast("list[object]", refs):
        key = _ref_key(item)
        if key is None:
            continue
        span = _ref_col_span(item)
        existing = positions.get(key)
        if existing is not None:
            if span and not result[existing].col_span:
                result[existing] = LayoutFieldRef(key=key, col_span=True)
            continue
        positions[key] = len(result)
        result.add(LayoutFieldRef(key=key, col_span=span))
    return ConcurrentStableFrozenList(result)


def normalize_columns(value: object) -> int:
    """归一列数（仅 1 / 2 / 3 合法，其余回落缺省 3）。

    Args:
        value: 原始值。

    Returns:
        int: 生效列数。
    """
    if isinstance(value, bool):
        return DEFAULT_LAYOUT_COLUMNS
    if isinstance(value, int):
        return value if value in SECTION_COLUMNS else DEFAULT_LAYOUT_COLUMNS
    if isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            return DEFAULT_LAYOUT_COLUMNS
        return parsed if parsed in SECTION_COLUMNS else DEFAULT_LAYOUT_COLUMNS
    return DEFAULT_LAYOUT_COLUMNS


def _clamp_int(value: object, bounds: tuple[int, int], fallback: int) -> int:
    """夹取整数到区间。

    Args:
        value: 原始值。
        bounds: 上下限。
        fallback: 不可解析时的回落值。

    Returns:
        int: 夹取后的整数。
    """
    if isinstance(value, bool) or value is None:
        return fallback
    if isinstance(value, int | float):
        number = int(value)
    elif isinstance(value, str):
        try:
            number = int(value.strip())
        except ValueError:
            return fallback
    else:
        return fallback
    return min(max(number, bounds[0]), bounds[1])


def normalize_detail_columns(columns: object) -> ConcurrentStableFrozenList[LayoutDetailColumn]:
    """归一明细列（兼容字符串与 `{key, width}`，去重保序，宽度夹取）。

    Args:
        columns: 原始列列表。

    Returns:
        ConcurrentStableFrozenList[LayoutDetailColumn]: 归一后的列（插入序）。
    """
    result: ConcurrentStableList[LayoutDetailColumn] = ConcurrentStableList()
    seen: ConcurrentStableDict[str, bool] = ConcurrentStableDict()
    if not isinstance(columns, list):
        return ConcurrentStableFrozenList(())
    for item in cast("list[object]", columns):
        key = _ref_key(item)
        if key is None or key in seen:
            continue
        seen.set(key, True)
        width: object = None
        if isinstance(item, Mapping):
            width = cast("dict[str, object]", item).get("width")
        if width is None:
            result.add(LayoutDetailColumn(key=key))
        else:
            result.add(LayoutDetailColumn(key=key, width=_clamp_int(width, DETAIL_WIDTH_RANGE, 0)))
    return ConcurrentStableFrozenList(result)


def empty_layout() -> FormLayout:
    """空布局（无分区、无查询区、无明细区）。

    Returns:
        FormLayout: 空布局。
    """
    return FormLayout(main=LayoutMain(label_position="top"))


def normalize_layout(raw: object) -> FormLayout:
    """归一布局（缺省项补确定值，失败引用不抛错；装载输入兼容裸字符串引用）。

    Args:
        raw: 原始布局（字典或 `FormLayout`）。

    Returns:
        FormLayout: 归一后的布局。
    """
    if isinstance(raw, FormLayout):
        raw = layout_to_config(raw)
    if not isinstance(raw, Mapping):
        return empty_layout()
    config = cast("dict[str, object]", raw)
    main_raw = config.get("main")
    if not isinstance(main_raw, Mapping):
        return empty_layout()
    main_cfg = cast("dict[str, object]", main_raw)
    sections: ConcurrentStableList[LayoutSection] = ConcurrentStableList()
    raw_sections = main_cfg.get("sections")
    if isinstance(raw_sections, list):
        for position, section_raw in enumerate(cast("list[object]", raw_sections)):
            if not isinstance(section_raw, Mapping):
                continue
            section_cfg = cast("dict[str, object]", section_raw)
            raw_key = section_cfg.get("key")
            generated_key = f"{SECTION_KEY_PREFIX}{position + 1}"
            section_key = raw_key if isinstance(raw_key, str) and raw_key != "" else generated_key
            raw_title = section_cfg.get("title")
            groups: ConcurrentStableList[LayoutGroup] = ConcurrentStableList()
            raw_groups = section_cfg.get("groups")
            if isinstance(raw_groups, list):
                for group_position, group_raw in enumerate(cast("list[object]", raw_groups)):
                    if not isinstance(group_raw, Mapping):
                        continue
                    group_cfg = cast("dict[str, object]", group_raw)
                    raw_group_key = group_cfg.get("key")
                    group_key = (
                        raw_group_key
                        if isinstance(raw_group_key, str) and raw_group_key != ""
                        else f"{SECTION_KEY_PREFIX}{position + 1}-g{group_position + 1}"
                    )
                    raw_group_title = group_cfg.get("title")
                    groups.add(
                        LayoutGroup(
                            key=group_key,
                            title=raw_group_title if isinstance(raw_group_title, str) else "",
                            fields=normalize_field_refs(group_cfg.get("fields")),
                        )
                    )
            sections.add(
                LayoutSection(
                    key=section_key,
                    title=raw_title if isinstance(raw_title, str) else "",
                    columns=normalize_columns(section_cfg.get("columns")),
                    fields=normalize_field_refs(section_cfg.get("fields")),
                    groups=ConcurrentStableFrozenList(groups),
                )
            )
    label_position = "left" if main_cfg.get("labelPosition") == "left" else "top"
    raw_label_width = main_cfg.get("labelWidth")
    label_width = (
        None if raw_label_width is None else _clamp_int(raw_label_width, LABEL_WIDTH_RANGE, DEFAULT_LABEL_WIDTH)
    )
    layout = FormLayout(
        main=LayoutMain(
            label_position=label_position,
            sections=ConcurrentStableFrozenList(sections),
            label_width=label_width,
        )
    )
    query_raw = config.get("query")
    if isinstance(query_raw, Mapping):
        query_cfg = cast("dict[str, object]", query_raw)
        query_fields = normalize_field_refs(query_cfg.get("fields"))
        if len(query_fields) > 0:
            layout = FormLayout(
                main=layout.main,
                query=LayoutQuery(fields=ConcurrentStableFrozenList(ref.key for ref in query_fields)),
                detail=layout.detail,
                dict_advanced=layout.dict_advanced,
            )
    detail_raw = config.get("detail")
    if isinstance(detail_raw, Mapping):
        detail_cfg = cast("dict[str, object]", detail_raw)
        columns = normalize_detail_columns(detail_cfg.get("columns"))
        if len(columns) > 0:
            layout = FormLayout(
                main=layout.main,
                query=layout.query,
                detail=columns,
                dict_advanced=layout.dict_advanced,
            )
    advanced_raw = config.get("dictAdvanced")
    if isinstance(advanced_raw, Mapping):
        advanced_cfg = cast("dict[str, object]", advanced_raw)
        operators = advanced_cfg.get("operators")
        op_list = (
            [item for item in cast("list[object]", operators) if isinstance(item, str) and item != ""]
            if isinstance(operators, list)
            else []
        )
        raw_scheme = advanced_cfg.get("scheme")
        dict_advanced = LayoutDictAdvanced(
            fields=ConcurrentStableFrozenList(ref.key for ref in normalize_field_refs(advanced_cfg.get("fields"))),
            operators=ConcurrentStableFrozenList(op_list),
            columns=ConcurrentStableFrozenList(ref.key for ref in normalize_field_refs(advanced_cfg.get("columns"))),
            scheme=raw_scheme if isinstance(raw_scheme, str) and raw_scheme != "" else None,
        )
        if (
            len(dict_advanced.fields) > 0
            or len(dict_advanced.operators) > 0
            or len(dict_advanced.columns) > 0
            or dict_advanced.scheme is not None
        ):
            layout = FormLayout(
                main=layout.main,
                query=layout.query,
                detail=layout.detail,
                dict_advanced=dict_advanced,
            )
    return layout


def layout_to_config(layout: FormLayout) -> ConcurrentStableDict[str, object]:
    """布局 → `layout_config` 字典（写库与契约下发同形；键用前端既有 camelCase）。

    Args:
        layout: 布局模型。

    Returns:
        ConcurrentStableDict[str, object]: 可 JSON 序列化的配置字典（值全为内置容器）。
    """
    sections: ConcurrentStableList[object] = ConcurrentStableList()
    for section in layout.main.sections:
        section_map: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "key": section.key,
                "title": section.title,
                "columns": section.columns,
                "fields": ConcurrentStableList(_ref_to_config(ref) for ref in section.fields),
            }
        )
        if len(section.groups) > 0:
            group_list: ConcurrentStableList[object] = ConcurrentStableList()
            for group in section.groups:
                group_list.add(
                    ConcurrentStableDict(
                        {
                            "key": group.key,
                            "title": group.title,
                            "fields": ConcurrentStableList(_ref_to_config(ref) for ref in group.fields),
                        }
                    )
                )
            section_map.set("groups", group_list)
        sections.add(section_map)
    main_map: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "labelPosition": layout.main.label_position,
            "sections": sections,
        }
    )
    if layout.main.label_width is not None:
        main_map.set("labelWidth", layout.main.label_width)
    result: ConcurrentStableDict[str, object] = ConcurrentStableDict({"main": main_map})
    if layout.query is not None:
        result.set("query", ConcurrentStableDict({"fields": layout.query.fields}))
    if layout.detail is not None:
        column_list: ConcurrentStableList[object] = ConcurrentStableList()
        for column in layout.detail:
            if column.width is None:
                column_list.add(ConcurrentStableDict({"key": column.key}))
            else:
                column_list.add(ConcurrentStableDict({"key": column.key, "width": column.width}))
        result.set("detail", ConcurrentStableDict({"columns": column_list}))
    if layout.dict_advanced is not None:
        advanced: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        if len(layout.dict_advanced.fields) > 0:
            advanced.set("fields", layout.dict_advanced.fields)
        if len(layout.dict_advanced.operators) > 0:
            advanced.set("operators", layout.dict_advanced.operators)
        if len(layout.dict_advanced.columns) > 0:
            advanced.set("columns", layout.dict_advanced.columns)
        if layout.dict_advanced.scheme is not None:
            advanced.set("scheme", layout.dict_advanced.scheme)
        if len(advanced) > 0:
            result.set("dictAdvanced", advanced)
    return ConcurrentStableDict(cast("dict[str, object]", normalize_collections(result)))


def _ref_to_config(ref: LayoutFieldRef) -> object:
    """字段引用 → 配置形态（跨列才写 `colSpan`）。

    Args:
        ref: 字段引用。

    Returns:
        object: 字符串或 `{key, colSpan}` 字典。
    """
    return {"key": ref.key, "colSpan": True} if ref.col_span else ref.key


def parse_layout_config(raw: str) -> FormLayout:
    """解析库里存的 `layout_config` JSON 文本并归一。

    Args:
        raw: JSON 文本。

    Returns:
        FormLayout: 归一后的布局。

    Raises:
        ParamError: JSON 非法（10001；库内数据损坏，属配置异常）。
    """
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParamError(f"布局配置 JSON 非法：{exc.msg}") from exc
    return normalize_layout(parsed)


def dump_layout_config(layout: FormLayout) -> str:
    """序列化布局为 `layout_config` JSON 文本（写库用；键序稳定便于比对）。

    Args:
        layout: 布局模型。

    Returns:
        str: JSON 文本（`ensure_ascii=False`，紧凑分隔）。
    """
    return json.dumps(
        normalize_collections(layout_to_config(layout)),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def is_layout_empty(layout: FormLayout | None) -> bool:
    """是否为空布局（无有效分区或全部无字段引用且无分组引用）。

    Args:
        layout: 布局（None 视为空）。

    Returns:
        bool: 空为 True。
    """
    if layout is None:
        return True
    for section in layout.main.sections:
        if len(section.fields) > 0:
            return False
        for group in section.groups:
            if len(group.fields) > 0:
                return False
    return True


def default_layout(
    fields: ConcurrentStableFrozenList[ConcurrentStableDict[str, object]],
    columns: int = DEFAULT_LAYOUT_COLUMNS,
) -> FormLayout:
    """空布局回退：按字段清单顺序生成默认栅格（跳过停用与建列失败）。

    Args:
        fields: 合并字段清单（每项须含 `key`；可选 `status` / `disabled`）。
        columns: 列数（缺省 3）。

    Returns:
        FormLayout: 默认栅格布局（单分区，字段按入参顺序）。
    """
    refs: ConcurrentStableList[LayoutFieldRef] = ConcurrentStableList()
    for item in fields:
        if item.get("disabled") is True:
            continue
        status = item.get("status")
        if isinstance(status, str) and status not in ("", "active"):
            continue
        key = item.get("key")
        if isinstance(key, str) and key != "":
            refs.add(LayoutFieldRef(key=key))
    return FormLayout(
        main=LayoutMain(
            label_position="top",
            sections=ConcurrentStableFrozenList(
                (
                    LayoutSection(
                        key=DEFAULT_SECTION_KEY,
                        title="",
                        columns=normalize_columns(columns),
                        fields=ConcurrentStableFrozenList(refs),
                    ),
                )
            ),
        )
    )


def collect_field_keys(layout: FormLayout | None) -> ConcurrentStableFrozenList[str]:
    """收集布局引用的字段键（主表 + 查询区 + 明细区 + 字典高级查询，去重保序）。

    Args:
        layout: 布局。

    Returns:
        ConcurrentStableFrozenList[str]: 引用键（插入序）。
    """
    keys: ConcurrentStableList[str] = ConcurrentStableList()
    seen: ConcurrentStableDict[str, bool] = ConcurrentStableDict()

    def push(key: str) -> None:
        if seen.get(key) is True:
            return
        seen.set(key, True)
        keys.add(key)

    if layout is None:
        return ConcurrentStableFrozenList(())
    for section in layout.main.sections:
        for ref in section.fields:
            push(ref.key)
        for group in section.groups:
            for ref in group.fields:
                push(ref.key)
    if layout.query is not None:
        for key in layout.query.fields:
            push(key)
    if layout.detail is not None:
        for column in layout.detail:
            push(column.key)
    if layout.dict_advanced is not None:
        for key in layout.dict_advanced.fields:
            push(key)
        for key in layout.dict_advanced.columns:
            push(key)
    return ConcurrentStableFrozenList(keys)


def find_duplicate_fields(layout: FormLayout) -> ConcurrentStableFrozenList[str]:
    """找出被多个分区重复引用的字段（主表范围内）。

    Args:
        layout: 布局。

    Returns:
        ConcurrentStableFrozenList[str]: 重复字段键（插入序）。
    """
    seen: ConcurrentStableDict[str, bool] = ConcurrentStableDict()
    duplicated: ConcurrentStableList[str] = ConcurrentStableList()
    for section in layout.main.sections:
        for ref in section.fields:
            if seen.get(ref.key) is True:
                if ref.key not in duplicated:
                    duplicated.add(ref.key)
                continue
            seen.set(ref.key, True)
    return ConcurrentStableFrozenList(duplicated)


def validate_layout_refs(
    layout: FormLayout,
    *,
    known_keys: ConcurrentStableFrozenList[str],
    disabled_keys: ConcurrentStableFrozenList[str],
) -> ConcurrentStableFrozenList[LayoutIssue]:
    """校验布局引用（失效 / 停用 / 重复 / 空分区）——保存期告警、渲染期跳过，均不抛错。

    Args:
        layout: 布局。
        known_keys: 字段清单内的键（平台 + 自建）。
        disabled_keys: 停用 / 建列失败的键。

    Returns:
        ConcurrentStableFrozenList[LayoutIssue]: 问题清单（空表示无问题）。
    """
    known = set(known_keys)
    disabled = set(disabled_keys)
    issues: ConcurrentStableList[LayoutIssue] = ConcurrentStableList()
    for key in collect_field_keys(layout):
        if key not in known:
            issues.add(LayoutIssue(kind="unknown-field", field_key=key, message=f"字段引用失效：{key}"))
        elif key in disabled:
            issues.add(LayoutIssue(kind="disabled-field", field_key=key, message=f"字段已停用或建列失败：{key}"))
    for key in find_duplicate_fields(layout):
        issues.add(LayoutIssue(kind="duplicate-field", field_key=key, message=f"字段被重复引用：{key}"))
    for section in layout.main.sections:
        if len(section.fields) == 0 and len(section.groups) == 0:
            issues.add(
                LayoutIssue(
                    kind="empty-section",
                    section_key=section.key,
                    message=f"分区无字段：{section.title or section.key}",
                )
            )
    return ConcurrentStableFrozenList(issues)


def resolve_layout_for_level(
    levels: ConcurrentStableFrozenDict[str, FormLayout],
    level: str,
) -> tuple[FormLayout | None, str]:
    """按层级解析布局（角色视图 → 租户覆盖 → 平台默认；皆空返回 `None` + `empty`）。

    Args:
        levels: 层级 → 布局（`role` / `tenant` / `platform`，可缺）。
        level: 请求层级（`role` / `tenant` / `platform`）。

    Returns:
        tuple[FormLayout | None, str]: （命中布局或 None, 来源层级或 `empty`）。
    """
    if level == "role":
        order: ConcurrentStableList[str] = ConcurrentStableList(("role", "tenant", "platform"))
    elif level == "tenant":
        order = ConcurrentStableList(("tenant", "platform"))
    else:
        order = ConcurrentStableList(("platform",))
    for candidate in order:
        layout = levels.get(candidate)
        if layout is not None and not is_layout_empty(layout):
            return layout, candidate
    return None, "empty"
