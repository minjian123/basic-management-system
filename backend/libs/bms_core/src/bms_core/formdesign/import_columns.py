"""导入模板列派生：按生效布局生成导入列集（10_01）。

**为什么需要派生**（任务 10_01 决策 8 / 18）：导入模板列必须与表单布局一致（平台字段 + 已生效自建
字段），否则「页面填得进、导入填不进」。但布局是运行期数据、`BaseImportDefinition.columns` 是同步
property 无法查库，因此在基座加异步钩子 `columns_for(session)`（默认回退静态列集，既有定义零改动），
本模块提供派生算法供覆写者复用。

**派生规则**：

1. 按**生效布局主表字段顺序**排列（分区 → 分组内的引用序）；
2. 布局未引用但原列集存在的列：保序追加在末尾（不丢数据，向后兼容）；
3. 布局引用但原列集无的平台字段：追加（配置新增字段即为导入新增列）；
4. 自建字段只取 `active`（`pending` / `failed` 不进模板，避免导入写不存在的列）。
"""

from typing import Any, Protocol

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.db.session import DbSession
from bms_core.formdesign.layout import collect_field_keys, is_layout_empty, parse_layout_config
from bms_core.transfer.base import ColumnSpec

__all__ = [
    "LayoutColumnResolver",
    "current_layout_column_resolver",
    "derive_import_columns",
    "layout_columns_of",
    "merge_column_specs",
    "register_layout_column_resolver",
]


def merge_column_specs(
    *,
    layout_keys: ConcurrentStableFrozenList[str],
    extra_specs: ConcurrentStableDict[str, ColumnSpec],
    layout_specs: ConcurrentStableDict[str, ColumnSpec],
    base_specs: ConcurrentStableDict[str, ColumnSpec],
) -> ConcurrentStableFrozenList[ColumnSpec]:
    """按布局顺序合并列规格（布局序优先，未引用的基线列保序追加）。

    Args:
        layout_keys: 布局字段引用键（顺序即列序）。
        extra_specs: 自建字段派生的列规格（键 → 规格）。
        layout_specs: 平台字段按布局顺序派生的规格（键 → 规格，可能缺）。
        base_specs: 导入定义原有列规格（键 → 规格）。

    Returns:
        ConcurrentStableFrozenList[ColumnSpec]: 合并后的列集（无重复键）。
    """
    result: ConcurrentStableList[ColumnSpec] = ConcurrentStableList()
    emitted: ConcurrentStableDict[str, bool] = ConcurrentStableDict()
    for key in layout_keys:
        if emitted.get(key) is True:
            continue
        spec = extra_specs.get(key) or layout_specs.get(key) or base_specs.get(key)
        if spec is None:
            continue
        emitted.set(key, True)
        result.add(spec)
    for key in base_specs:
        if emitted.get(key) is True:
            continue
        emitted.set(key, True)
        result.add(base_specs[key])
    return ConcurrentStableFrozenList(result)


def derive_import_columns(
    *,
    layout_keys: ConcurrentStableFrozenList[str],
    extra_specs: ConcurrentStableDict[str, ColumnSpec],
    layout_specs: ConcurrentStableDict[str, ColumnSpec],
    base_specs: ConcurrentStableDict[str, ColumnSpec],
) -> ConcurrentStableFrozenList[ColumnSpec]:
    """派生导入列集（`merge_column_specs` 的语义化入口；空布局时等于原列集）。

    Args:
        layout_keys: 布局字段引用键（顺序即列序；空表示无布局配置）。
        extra_specs: 自建字段派生的列规格。
        layout_specs: 平台字段按布局顺序派生的规格。
        base_specs: 导入定义原有列规格。

    Returns:
        ConcurrentStableFrozenList[ColumnSpec]: 派生后的列集。
    """
    return merge_column_specs(
        layout_keys=layout_keys,
        extra_specs=extra_specs,
        layout_specs=layout_specs,
        base_specs=base_specs,
    )


del ConcurrentStableFrozenDict


async def layout_columns_of(
    session: DbSession,
    *,
    form_code: str,
    layout_model: type[Any],
    attr_model: type[Any],
    ext_model: type[Any],
) -> tuple[ConcurrentStableFrozenList[str], ConcurrentStableDict[str, ColumnSpec]]:
    """取某表单的布局字段序与自建字段列规格（基座实现，模型由调用方注入）。

    **为什么模型经参数注入**：`sys_form_layout` / `sys_form_field_attr` / `sys_field_ext` 三表归
    `form_design` 业务域，而本函数在基座能力域（不得 import 任何服务域）；表模型由调用方（域实现
    或装配面）以参数传入，跨域边界因此保持单向且零 import。

    Args:
        session: 租户库会话。
        form_code: 表单标识（业务码）。
        layout_model: 布局表模型（`sys_form_layout`）。
        attr_model: 字段属性表模型（`sys_form_field_attr`）。
        ext_model: 自建字段表模型（`sys_field_ext`）。

    Returns:
        tuple: （字段键序, 自建字段列规格）；无布局配置时返回空键序。
    """
    from sqlalchemy import select

    layout_rows = (
        (
            await session.execute(
                select(layout_model).where(
                    layout_model.form_code == form_code,
                    layout_model.deleted_at.is_(None),
                    layout_model.scope.in_(("tenant", "platform")),
                )
            )
        )
        .scalars()
        .all()
    )
    chosen = None
    for scope in ("tenant", "platform"):
        for row in layout_rows:
            if row.scope == scope and not is_layout_empty(parse_layout_config(row.layout_config)):
                chosen = row
                break
        if chosen is not None:
            break
    if chosen is None:
        return ConcurrentStableFrozenList(()), ConcurrentStableDict()
    ext_rows = (
        (
            await session.execute(
                select(ext_model).where(
                    ext_model.form_code == form_code,
                    ext_model.deleted_at.is_(None),
                    ext_model.status == "enabled",
                    ext_model.ddl_status == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    specs: ConcurrentStableDict[str, ColumnSpec] = ConcurrentStableDict()
    for row in ext_rows:
        specs.set(
            row.field_key,
            ColumnSpec(
                key=row.field_key,
                title=row.name,
                value_type="text",
                note="自建字段（租户）",
            ),
        )
    return collect_field_keys(parse_layout_config(chosen.layout_config)), specs


class LayoutColumnResolver(Protocol):
    r"""布局列解析回调：\`async (*, form_code, session) -> (字段键序, 自建字段列规格)\`。"""

    async def __call__(
        self,
        *,
        form_code: str,
        session: DbSession,
    ) -> tuple[ConcurrentStableFrozenList[str], ConcurrentStableDict[str, ColumnSpec]]:
        r"""取某表单的布局字段序与自建字段列规格。

        Args:
            form_code: 表单标识（业务码）。
            session: 租户库会话。

        Returns:
            tuple: （字段键序, 自建字段列规格）。
        """
        ...


_RESOLVER: ConcurrentStableList[LayoutColumnResolver] = ConcurrentStableList()
"""已登记的解析回调（装配面登记；运行期只读，取首个）。"""


def register_layout_column_resolver(resolver: LayoutColumnResolver) -> None:
    r"""登记布局列解析回调（装配面调用；同类型重复登记只保留首个）。

    **为什么用回调而不是直接读表**：布局与自建字段三表归 \`form_design\` 业务域，消费方（如
    \`user\` 的导入定义）不得 import 他域模型；装配面是唯一组合点，构造实现后在此登记，
    消费方只经 \`current_layout_column_resolver\` 取用。

    Args:
        resolver: 解析回调。
    """
    if len(_RESOLVER) == 0:
        _RESOLVER.add(resolver)


def current_layout_column_resolver() -> LayoutColumnResolver | None:
    """取当前登记的布局列解析回调（未登记返回 None）。

    Returns:
        LayoutColumnResolver | None: 回调或 None。
    """
    return _RESOLVER[0] if len(_RESOLVER) > 0 else None
