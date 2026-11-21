"""生效布局组装：三级解析 + 字段合并 + 权限叠加 + 选项集快照（渲染路径核心，10_01）。

流程（与《架构设计 · 表单定制》§3 一致）：

1. **取三层**：按 `form_code` 取布局与属性行（各层各一份，可缺）；
2. **三级解析**：角色视图（按 `role_type` 内置优先级 + `role_id` 升序取首个非空）→ 租户覆盖 →
   平台默认 → 皆空则按字段 `sort` 生成默认栅格（`source = empty`、`fallback = true`）；
3. **字段合并**：平台字段（`sys_field`）合并自建字段（仅 `status=enabled ∧ ddl_status=active`）；
4. **属性叠加**：属性与布局**同层同源**（选哪层布局就用哪层属性）；
5. **权限优先**：`visible=false` 的字段从清单与全部布局引用中剔除；`editable=false` 保留并标记；
6. **选项集快照**：枚举字段按 `option_set_key` 去重解析，随响应一次下发。
"""

from __future__ import annotations

from dataclasses import dataclass

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.objects import BaseValueObject
from bms_core.formdesign.attrs import FieldAttrs, dump_attrs, parse_attrs_config
from bms_core.formdesign.layout import (
    FormLayout,
    LayoutDetailColumn,
    LayoutGroup,
    LayoutMain,
    LayoutQuery,
    LayoutSection,
    default_layout,
    is_layout_empty,
    layout_to_config,
    parse_layout_config,
)
from bms_core.models.platform.form_design import (
    DDL_STATUS_ACTIVE,
    SCOPE_PLATFORM,
    SCOPE_ROLE,
    SCOPE_TENANT,
    SysFieldExt,
    SysFormFieldAttr,
    SysFormLayout,
)
from bms_core.permission.role_priority import ROLE_TYPE_PRIORITY as ROLE_TYPE_PRIORITY
from bms_core.permission.role_priority import pick_role_candidate

__all__ = [
    "ROLE_TYPE_PRIORITY",
    "AssembledLayout",
    "LevelSnapshot",
    "assemble_layout",
    "collect_levels",
    "merge_fields",
    "pick_role_level",
    "strip_invisible",
]

"""角色视图命中优先级的单一定义在 `bms_core/permission/role_priority.py`（11_01 上移），
本模块经 `__all__` 再导出 `ROLE_TYPE_PRIORITY` 与 `pick_role_level` 以保持既有引用不变。"""


@dataclass(frozen=True)
class LevelSnapshot(BaseValueObject):
    """单层快照（布局 + 该层属性），供三级解析后取用。

    Attributes:
        scope: 层级。
        role_id: 角色 ID（非角色层级为 0）。
        layout: 该层布局（无配置为 None）。
        attrs: 该层字段属性（字段键 → 属性）。
    """

    scope: str
    """层级。"""

    role_id: int
    """角色 ID（非角色层级为 0）。"""

    layout: FormLayout | None
    """该层布局（无配置为 None）。"""

    attrs: ConcurrentStableDict[str, FieldAttrs]
    """该层字段属性（字段键 → 属性）。"""


@dataclass(frozen=True)
class AssembledLayout(BaseValueObject):
    """组装结果（布局 + 字段 + 来源 + 权限 + 选项集）。

    Attributes:
        layout: 生效布局。
        fields: 合并字段清单（已剔除不可见）。
        source: 来源层级或 `empty`。
        fallback: 是否走空布局回退。
        permissions: 字段权限标记（仅收窄项）。
        option_sets: 选项集快照集。
    """

    layout: FormLayout
    """生效布局。"""

    fields: ConcurrentStableFrozenList[ConcurrentStableDict[str, object]]
    """合并字段清单（已剔除不可见）。"""

    source: str
    """来源层级或 `empty`。"""

    fallback: bool
    """是否走空布局回退。"""

    permissions: ConcurrentStableDict[str, ConcurrentStableDict[str, object]]
    """字段权限标记（仅收窄项）。"""

    option_sets: ConcurrentStableFrozenList[ConcurrentStableDict[str, object]]
    """选项集快照集。"""

    def layout_config(self) -> ConcurrentStableDict[str, object]:
        """取布局配置字典（下发用）。

        Returns:
            ConcurrentStableDict[str, object]: `layout_config` 结构。
        """
        return layout_to_config(self.layout)


def collect_levels(
    *,
    layouts: ConcurrentStableList[SysFormLayout],
    attr_rows: ConcurrentStableList[SysFormFieldAttr],
) -> ConcurrentStableDict[str, ConcurrentStableDict[int, LevelSnapshot]]:
    """把库行按层级归集（scope → role_id → 快照）。

    Args:
        layouts: 布局行。
        attr_rows: 属性行。

    Returns:
        ConcurrentStableDict[str, ConcurrentStableDict[int, LevelSnapshot]]: 层级 → 角色 → 快照。
    """
    attr_index: ConcurrentStableDict[tuple[str, int], ConcurrentStableDict[str, FieldAttrs]] = ConcurrentStableDict()
    for row in attr_rows:
        slot = (row.scope, row.role_id)
        bucket = attr_index.get(slot)
        if bucket is None:
            created: ConcurrentStableDict[str, FieldAttrs] = ConcurrentStableDict()
            attr_index.set(slot, created)
            bucket = created
        bucket.set(row.field_key, parse_attrs_config(row.attrs))
    levels: ConcurrentStableDict[str, ConcurrentStableDict[int, LevelSnapshot]] = ConcurrentStableDict()
    for scope in (SCOPE_PLATFORM, SCOPE_TENANT, SCOPE_ROLE):
        levels.set(scope, ConcurrentStableDict())
    for row in layouts:
        scope_map = levels.get(row.scope)
        if scope_map is None:  # pragma: no cover - 库内 scope 受白名单约束
            continue
        scope_map.set(
            row.role_id,
            LevelSnapshot(
                scope=row.scope,
                role_id=row.role_id,
                layout=parse_layout_config(row.layout_config),
                attrs=attr_index.get((row.scope, row.role_id)) or ConcurrentStableDict(),
            ),
        )
    # 只有属性、无布局的层也要能命中（属性层独立于布局存在）
    for (scope, role_id), attrs in attr_index.items():
        scope_map = levels.get(scope)
        if scope_map is None or role_id in scope_map:
            continue
        scope_map.set(role_id, LevelSnapshot(scope=scope, role_id=role_id, layout=None, attrs=attrs))
    return levels


def pick_role_level(
    *,
    candidates: ConcurrentStableList[tuple[str, int, FormLayout | None]],
) -> tuple[int | None, FormLayout | None]:
    """从命中角色中选一个层级（按 `role_type` 优先级 + `role_id` 升序，取首个非空布局）。

    Args:
        candidates: 候选清单（`(role_type, role_id, layout)`）。

    Returns:
        tuple[int | None, FormLayout | None]: （选中角色 ID, 布局）；无命中返回 `(None, None)`。
    """
    return pick_role_candidate(candidates, is_empty=is_layout_empty)


def merge_fields(
    *,
    platform_fields: ConcurrentStableList[ConcurrentStableDict[str, object]],
    ext_fields: ConcurrentStableList[SysFieldExt],
    attrs: ConcurrentStableDict[str, FieldAttrs],
) -> ConcurrentStableFrozenList[ConcurrentStableDict[str, object]]:
    """合并平台字段与自建字段（按 `sort` 升序、同序按 `field_key` 升序），并叠加属性。

    Args:
        platform_fields: 平台字段项（`key` / `label` / `type` / `sort` / `status`）。
        ext_fields: 自建字段行（仅 `active` 传入）。
        attrs: 该层字段属性。

    Returns:
        ConcurrentStableFrozenList[ConcurrentStableDict[str, object]]: 合并字段清单。
    """
    merged: ConcurrentStableList[tuple[int, str, ConcurrentStableDict[str, object]]] = ConcurrentStableList()
    for item in platform_fields:
        field_attrs = attrs.get(str(item.get("key"))) or FieldAttrs()
        record: ConcurrentStableDict[str, object] = ConcurrentStableDict(item)
        record.set("attrs", dump_attrs(field_attrs))
        raw_sort = item.get("sort")
        sort_value = raw_sort if isinstance(raw_sort, int) else 0
        merged.add((sort_value, str(item.get("key")), record))
    for row in ext_fields:
        field_attrs = attrs.get(row.field_key) or FieldAttrs()
        record = ConcurrentStableDict(
            {
                "key": row.field_key,
                "label": row.name,
                "type": row.type,
                "group": "tenant",
                "sort": row.sort,
                "status": DDL_STATUS_ACTIVE if row.ddl_status == DDL_STATUS_ACTIVE else row.ddl_status,
                "disabled": row.status != "enabled" or row.ddl_status != DDL_STATUS_ACTIVE,
                "attrs": dump_attrs(field_attrs),
            }
        )
        merged.add((row.sort, row.field_key, record))
    ordered = sorted(merged, key=lambda item: (item[0], item[1]))
    return ConcurrentStableFrozenList(item[2] for item in ordered)


def strip_invisible(
    *,
    layout: FormLayout,
    hidden_keys: ConcurrentStableFrozenList[str],
) -> FormLayout:
    """从布局的全部引用中剔除不可见字段（权限优先）。

    Args:
        layout: 布局。
        hidden_keys: 不可见字段键。

    Returns:
        FormLayout: 剔除后的布局（分区内引用、分组引用、查询区、明细列、字典高级查询一并处理）。
    """
    if len(hidden_keys) == 0:
        return layout
    hidden = set(hidden_keys)
    sections: ConcurrentStableList[LayoutSection] = ConcurrentStableList()
    for section in layout.main.sections:
        kept_fields = ConcurrentStableFrozenList(ref for ref in section.fields if ref.key not in hidden)
        kept_groups: ConcurrentStableList[LayoutGroup] = ConcurrentStableList()
        for group in section.groups:
            group_fields = ConcurrentStableFrozenList(ref for ref in group.fields if ref.key not in hidden)
            if len(group_fields) > 0:
                kept_groups.add(LayoutGroup(key=group.key, title=group.title, fields=group_fields))
        sections.add(
            LayoutSection(
                key=section.key,
                title=section.title,
                columns=section.columns,
                fields=kept_fields,
                groups=ConcurrentStableFrozenList(kept_groups),
            )
        )
    query = layout.query
    if query is not None:
        kept_query = ConcurrentStableFrozenList(key for key in query.fields if key not in hidden)
        query = LayoutQuery(fields=kept_query) if len(kept_query) > 0 else None
    detail = layout.detail
    if detail is not None:
        kept_columns = ConcurrentStableFrozenList[LayoutDetailColumn](
            column for column in detail if column.key not in hidden
        )
        detail = kept_columns if len(kept_columns) > 0 else None
    advanced = layout.dict_advanced
    if advanced is not None:
        adv_fields = ConcurrentStableFrozenList(key for key in advanced.fields if key not in hidden)
        adv_columns = ConcurrentStableFrozenList(key for key in advanced.columns if key not in hidden)
        if len(adv_fields) == 0 and len(adv_columns) == 0 and advanced.scheme is None and len(advanced.operators) == 0:
            advanced = None
        else:
            advanced = type(advanced)(
                fields=adv_fields,
                operators=advanced.operators,
                columns=adv_columns,
                scheme=advanced.scheme,
            )
    return FormLayout(
        main=LayoutMain(
            label_position=layout.main.label_position,
            sections=ConcurrentStableFrozenList(sections),
            label_width=layout.main.label_width,
        ),
        query=query,
        detail=detail,
        dict_advanced=advanced,
    )


def assemble_layout(
    *,
    levels: ConcurrentStableDict[str, ConcurrentStableDict[int, LevelSnapshot]],
    level: str,
    role_hint: tuple[int | None, FormLayout | None],
    platform_fields: ConcurrentStableList[ConcurrentStableDict[str, object]],
    ext_fields: ConcurrentStableList[SysFieldExt],
    hidden_keys: ConcurrentStableFrozenList[str],
    permissions: ConcurrentStableDict[str, ConcurrentStableDict[str, object]],
    option_sets: ConcurrentStableFrozenList[ConcurrentStableDict[str, object]],
) -> AssembledLayout:
    """组装生效布局（三级解析 → 合并 → 权限剔除 → 下发形态）。

    Args:
        levels: 层级归集（`collect_levels` 结果）。
        level: 请求层级（渲染路径传 `role`：有角色视图用角色视图，否则逐级回退）。
        role_hint: （选中角色 ID, 角色布局），由 `pick_role_level` 得出。
        platform_fields: 平台字段项。
        ext_fields: 自建字段（仅 `active`）。
        hidden_keys: 不可见字段键。
        permissions: 字段权限标记（仅收窄项）。
        option_sets: 选项集快照集。

    Returns:
        AssembledLayout: 组装结果。
    """
    chosen: LevelSnapshot | None = None
    source = "empty"
    fallback = False
    role_id, role_layout = role_hint
    order: ConcurrentStableList[str]
    if level == "role":
        order = ConcurrentStableList((SCOPE_ROLE, SCOPE_TENANT, SCOPE_PLATFORM))
    elif level == "tenant":
        order = ConcurrentStableList((SCOPE_TENANT, SCOPE_PLATFORM))
    else:
        order = ConcurrentStableList((SCOPE_PLATFORM,))
    for scope in order:
        scope_map = levels.get(scope) or ConcurrentStableDict()
        if scope == SCOPE_ROLE:
            if role_id is None or role_layout is None:
                continue
            candidate = scope_map.get(role_id)
            if candidate is not None and candidate.layout is not None:
                chosen = candidate
                source = SCOPE_ROLE
                break
            chosen = LevelSnapshot(
                scope=SCOPE_ROLE,
                role_id=role_id,
                layout=role_layout,
                attrs=(candidate.attrs if candidate is not None else ConcurrentStableDict()),
            )
            source = SCOPE_ROLE
            break
        candidate = scope_map.get(0)
        if candidate is not None and candidate.layout is not None and not is_layout_empty(candidate.layout):
            chosen = candidate
            source = scope
            break
    attrs = chosen.attrs if chosen is not None else ConcurrentStableDict[str, FieldAttrs]()
    fields = merge_fields(platform_fields=platform_fields, ext_fields=ext_fields, attrs=attrs)
    if chosen is None or chosen.layout is None or is_layout_empty(chosen.layout):
        fallback = True
        source = "empty"
        layout = default_layout(fields)
    else:
        layout = chosen.layout
    stripped = strip_invisible(layout=layout, hidden_keys=hidden_keys)
    hidden = set(hidden_keys)
    visible_fields = ConcurrentStableFrozenList(item for item in fields if str(item.get("key")) not in hidden)
    return AssembledLayout(
        layout=stripped,
        fields=visible_fields,
        source=source,
        fallback=fallback,
        permissions=permissions,
        option_sets=option_sets,
    )
