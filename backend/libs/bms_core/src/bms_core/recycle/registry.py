"""回收站表规格登记（13_01）：平台首批业务实体白名单 + 追加注册口。

口径：

- **白名单而非自动发现**：只有登记过的表才进入回收站；平台元数据、系统参数、语言文案、
  任务定义、归档策略等有专属恢复入口或恢复副作用的表不登记；
- **子表级联**：多语言 / 锚点 / 扩展信息等子表 `visible=False`、`restorable=False`，
  只随主表级联恢复，但**同样参与超期清理**（否则会留下永久孤儿）；
- **展示列白名单**：详情只返回登记的展示列，不返回整行（避免口令等敏感列泄露）；
- **唯一冲突判定**：恢复前按表上的业务唯一约束预检；含 `form_key` 的复合唯一不作为冲突依据
  （页面标识，不是行唯一键）；
- **追加注册**：其他服务 / 产品在装载期调用 `register_recycle_tables()`，同表同值幂等、
  异值即拒（与 `register_audited_tables` / `register_table_records` 同构）。
"""

from __future__ import annotations

from collections.abc import Iterable

from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.models.base import Base
from bms_core.recycle.spec import RecycleCascade, RecycleField, RecycleTableSpec
from bms_core.services.table_registry import TableStatus, table_record

__all__ = [
    "RECYCLE_TABLES",
    "recycle_spec_of",
    "recycle_table_specs",
    "register_recycle_tables",
    "reset_recycle_tables",
    "validate_recycle_specs",
    "visible_recycle_specs",
]


def _field(column: str, label: str) -> RecycleField:
    """构造展示列。"""
    return RecycleField(column=column, label=label)


def _cascade(table: str, column: str, *, recursive: bool = False) -> RecycleCascade:
    """构造级联关系。"""
    return RecycleCascade(table=table, column=column, recursive=recursive)


def _spec(
    *,
    table: str,
    label: str,
    module_key: str,
    module_label: str,
    title_field: str,
    fields: Iterable[RecycleField] = (),
    keywords: Iterable[str] = (),
    cascades: Iterable[RecycleCascade] = (),
    visible: bool = True,
    restorable: bool = True,
) -> RecycleTableSpec:
    """构造表规格（元组入参 → 冻结集合字段）。"""
    return RecycleTableSpec(
        table=table,
        label=label,
        module_key=module_key,
        module_label=module_label,
        title_field=title_field,
        visible_fields=ConcurrentStableFrozenList(fields),
        keyword_fields=ConcurrentStableFrozenList(keywords),
        cascades=ConcurrentStableFrozenList(cascades),
        visible=visible,
        restorable=restorable,
    )


RECYCLE_TABLES: ConcurrentStableList[RecycleTableSpec] = ConcurrentStableList(
    (
        # ---- 用户与账号 ----
        _spec(
            table="sys_user",
            label="用户",
            module_key="user",
            module_label="用户与账号",
            title_field="name",
            fields=(_field("code", "登录账号"), _field("name", "姓名"), _field("status", "状态")),
            keywords=("code", "name"),
            cascades=(_cascade("sys_user_extension", "user_id"),),
        ),
        _spec(
            table="sys_user_extension",
            label="用户扩展信息",
            module_key="user",
            module_label="用户与账号",
            title_field="label",
            fields=(_field("label", "扩展标签"), _field("remark", "备注")),
            visible=False,
            restorable=False,
        ),
        # ---- 角色与授权 ----
        _spec(
            table="sys_role",
            label="角色",
            module_key="role",
            module_label="角色与授权",
            title_field="name",
            fields=(
                _field("code", "角色标识"),
                _field("name", "角色名"),
                _field("role_type", "角色类型"),
                _field("status", "状态"),
            ),
            keywords=("code", "name"),
        ),
        # ---- 平台元数据（自定义图标）----
        _spec(
            table="sys_icon",
            label="自定义图标",
            module_key="permission_meta",
            module_label="平台元数据",
            title_field="name",
            fields=(
                _field("code", "图标键"),
                _field("name", "名称"),
                _field("category", "分组"),
                _field("status", "状态"),
            ),
            keywords=("code", "name"),
            cascades=(_cascade("sys_icon_i18n", "icon_id"),),
        ),
        _spec(
            table="sys_icon_i18n",
            label="图标名多语言",
            module_key="permission_meta",
            module_label="平台元数据",
            title_field="name",
            fields=(_field("locale", "语言"), _field("name", "名称")),
            visible=False,
            restorable=False,
        ),
        # ---- 帮助内容 ----
        _spec(
            table="sys_help_category",
            label="帮助分类",
            module_key="help",
            module_label="帮助内容",
            title_field="name",
            fields=(_field("name", "分类名"), _field("status", "状态"), _field("sort", "排序")),
            keywords=("name",),
            cascades=(_cascade("sys_help_category", "parent_id", recursive=True),),
        ),
        _spec(
            table="sys_help_article",
            label="帮助文章",
            module_key="help",
            module_label="帮助内容",
            title_field="title",
            fields=(
                _field("title", "标题"),
                _field("status", "状态"),
                _field("source", "来源"),
                _field("is_top", "置顶"),
            ),
            keywords=("title",),
            cascades=(
                _cascade("sys_help_article_i18n", "article_id"),
                _cascade("sys_help_article_target", "article_id"),
            ),
        ),
        _spec(
            table="sys_help_article_i18n",
            label="文章多语言",
            module_key="help",
            module_label="帮助内容",
            title_field="title",
            fields=(_field("locale", "语言"), _field("title", "标题")),
            visible=False,
            restorable=False,
        ),
        _spec(
            table="sys_help_article_target",
            label="文章锚点",
            module_key="help",
            module_label="帮助内容",
            title_field="target_key",
            fields=(_field("target_type", "目标类型"), _field("target_key", "目标键")),
            visible=False,
            restorable=False,
        ),
        _spec(
            table="sys_help_feedback",
            label="帮助阅读反馈",
            module_key="help",
            module_label="帮助内容",
            title_field="feedback",
            fields=(_field("feedback", "反馈"), _field("comment", "评论")),
            keywords=("comment",),
        ),
        _spec(
            table="sys_help_package",
            label="帮助包登记",
            module_key="help",
            module_label="帮助内容",
            title_field="product_key",
            fields=(
                _field("product_key", "产品"),
                _field("package_version", "版本"),
                _field("status", "状态"),
                _field("loaded_at", "装载时间"),
            ),
            keywords=("product_key",),
        ),
        # ---- 工作台 ----
        _spec(
            table="sys_dashboard_card",
            label="工作台卡片",
            module_key="dashboard",
            module_label="工作台",
            title_field="name",
            fields=(
                _field("code", "卡片标识"),
                _field("name", "卡片名"),
                _field("card_type", "卡片类型"),
                _field("status", "状态"),
            ),
            keywords=("code", "name"),
            cascades=(_cascade("sys_dashboard_card_i18n", "card_id"),),
        ),
        _spec(
            table="sys_dashboard_card_i18n",
            label="卡片名多语言",
            module_key="dashboard",
            module_label="工作台",
            title_field="name",
            fields=(_field("locale", "语言"), _field("name", "卡片名")),
            visible=False,
            restorable=False,
        ),
        _spec(
            table="sys_dashboard_template",
            label="工作台模板",
            module_key="dashboard",
            module_label="工作台",
            title_field="name",
            fields=(_field("scope", "范围"), _field("name", "模板名"), _field("status", "状态")),
            keywords=("name",),
        ),
        # ---- 表单定制 ----
        _spec(
            table="sys_form_layout",
            label="表单布局",
            module_key="form_design",
            module_label="表单定制",
            title_field="form_code",
            fields=(
                _field("form_code", "表单标识"),
                _field("scope", "范围"),
                _field("status", "状态"),
            ),
            keywords=("form_code",),
        ),
        _spec(
            table="sys_form_field_attr",
            label="表单字段属性",
            module_key="form_design",
            module_label="表单定制",
            title_field="field_key",
            fields=(
                _field("form_code", "表单标识"),
                _field("field_key", "字段键"),
                _field("scope", "范围"),
            ),
            keywords=("form_code", "field_key"),
        ),
        _spec(
            table="sys_field_ext",
            label="自建字段",
            module_key="form_design",
            module_label="表单定制",
            title_field="name",
            fields=(
                _field("form_code", "表单标识"),
                _field("field_key", "字段键"),
                _field("name", "字段名"),
                _field("type", "字段类型"),
                _field("status", "状态"),
            ),
            keywords=("form_code", "field_key", "name"),
            cascades=(_cascade("sys_field_ext_i18n", "field_id"),),
        ),
        _spec(
            table="sys_field_ext_i18n",
            label="自建字段名多语言",
            module_key="form_design",
            module_label="表单定制",
            title_field="name",
            fields=(_field("locale", "语言"), _field("name", "字段名")),
            visible=False,
            restorable=False,
        ),
    )
)
"""平台首批回收站表规格（12 张可见表 + 6 张级联子表）。"""

_INJECTED: ConcurrentStableList[RecycleTableSpec] = ConcurrentStableList()
"""其他服务 / 产品注入的表规格（装载期经 `register_recycle_tables()` 登记）。"""


def register_recycle_tables(specs: Iterable[RecycleTableSpec]) -> None:
    """登记追加表规格（**装载期**调用；同表同值幂等、异值即拒）。

    Args:
        specs: 表规格（插入序）。

    Raises:
        ValueError: 同表已登记且内容不同（不静默取一侧）。
    """
    existing = {spec.table: spec for spec in RECYCLE_TABLES}
    for spec in specs:
        current = existing.get(spec.table)
        if current is None:
            for injected in _INJECTED:
                if injected.table == spec.table:
                    current = injected
                    break
        if current is not None and current != spec:
            raise ValueError(f"回收站表规格重复登记且内容不同：{spec.table}")
        if current is None:
            _INJECTED.add(spec)


def reset_recycle_tables() -> None:
    """清空追加注册（**测试隔离用**；不影响平台首批规格）。"""
    _INJECTED.clear()


def recycle_table_specs() -> ConcurrentStableList[RecycleTableSpec]:
    """取表规格合并视图（平台首批 + 追加注册，插入序）。

    Returns:
        ConcurrentStableList[RecycleTableSpec]: 表规格清单。
    """
    merged: ConcurrentStableList[RecycleTableSpec] = ConcurrentStableList(RECYCLE_TABLES)
    merged.extend(_INJECTED)
    return merged


def visible_recycle_specs() -> ConcurrentStableList[RecycleTableSpec]:
    """取可见表规格（模块 / 列表展示用）。

    Returns:
        ConcurrentStableList[RecycleTableSpec]: 可见表规格。
    """
    return ConcurrentStableList(spec for spec in recycle_table_specs() if spec.visible)


def recycle_spec_of(table: str) -> RecycleTableSpec | None:
    """按表名取规格（未登记返回 None）。

    Args:
        table: 逻辑表名。

    Returns:
        RecycleTableSpec | None: 表规格；未登记返回 None。
    """
    for spec in recycle_table_specs():
        if spec.table == table:
            return spec
    return None


def validate_recycle_specs() -> ConcurrentStableList[str]:
    """校验表规格完整性（护栏用例调用，不落运行期）。

    Returns:
        ConcurrentStableList[str]: 非法明细；空列表表示通过。
    """
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    seen: ConcurrentStableList[str] = ConcurrentStableList()
    tables = Base.metadata.tables
    for spec in recycle_table_specs():
        if spec.table in seen:
            errors.add(f"{spec.table}：表规格重复登记")
            continue
        seen.add(spec.table)
        table = tables.get(spec.table)
        if table is None:
            errors.add(f"{spec.table}：ORM 模型不存在")
            continue
        if "deleted_at" not in table.columns:
            errors.add(f"{spec.table}：缺少 deleted_at 列")
        if not spec.label.strip() or not spec.module_label.strip():
            errors.add(f"{spec.table}：中文名 / 模块名不能为空")
        record = table_record(spec.table)
        if record is None:
            errors.add(f"{spec.table}：未登记表归属")
        elif record.status != TableStatus.ENABLED:
            errors.add(f"{spec.table}：表归属未启用（{record.status}）")
        if spec.title_field not in table.columns:
            errors.add(f"{spec.table}：标题列不存在（{spec.title_field}）")
        for field in spec.visible_fields:
            if field.column not in table.columns:
                errors.add(f"{spec.table}：展示列不存在（{field.column}）")
            if not field.label.strip():
                errors.add(f"{spec.table}：展示列缺少中文标签（{field.column}）")
        for column in spec.keyword_fields:
            if column not in table.columns:
                errors.add(f"{spec.table}：关键字列不存在（{column}）")
        for cascade in spec.cascades:
            child = tables.get(cascade.table)
            if child is None:
                errors.add(f"{spec.table}：级联子表不存在（{cascade.table}）")
            elif cascade.column not in child.columns:
                errors.add(f"{spec.table}：级联列不存在（{cascade.table}.{cascade.column}）")
            if recycle_spec_of(cascade.table) is None:
                errors.add(f"{spec.table}：级联子表未登记规格（{cascade.table}）")
        if spec.visible and not spec.restorable:
            errors.add(f"{spec.table}：可见表必须可恢复")
        if not spec.visible and spec.restorable:
            errors.add(f"{spec.table}：隐藏子表不可单独恢复")
        if spec.visible and not spec.keyword_fields:
            errors.add(f"{spec.table}：可见表必须登记关键字列（列表关键字过滤）")
    return errors
