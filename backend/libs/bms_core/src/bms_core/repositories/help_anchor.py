"""帮助锚点（`help_key`）跨表唯一性读助手 + 解析索引归集（08_01 / 08_02）。

`help_key` 散布在五张元数据表（菜单 / 表单 / 字段 / 按钮 / 动作码），唯一性口径是**跨表全局唯一**。
量级很小（元数据百级）、写入频次低，故读侧统一走本模块的整表探测，不在业务侧各写一份 SQL：

- `find_help_key_conflict`：写接口与装载声明保存前探测冲突（可排除自身行）；
- `list_help_anchors`：列示全部非空锚点（08_04 覆盖率台账与启动期对账复用）；
- `load_help_anchor_index`：按**自然键**归集锚点索引（08_02 五级解析；缓存由 `bms_core/help/index.py` 承担）。

不加数据库唯一约束：五表分别建 `(help_key, deleted_at)` 唯一键会因达梦把复合唯一中的 NULL 视同相等，
使多条未登记行互撞（既有已知方言差异），由应用层保证唯一。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import select

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import MenuHelpKeyInvalidError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseValueObject
from bms_core.db.session import DbSession
from bms_core.help.anchors import ANCHOR_TABLES, HelpAnchorKind, help_key_segments, validate_help_key
from bms_core.help.index import HelpAnchorIndex, HelpMenuAnchor
from bms_core.models.platform.menu_form import SysButton, SysField, SysForm, SysMenu
from bms_core.models.platform.permission_meta import SysAction, SysBusiness, SysPermission

__all__ = ["HelpAnchorEntry", "find_help_key_conflict", "list_help_anchors", "load_help_anchor_index"]

_LOGGER = get_logger("bms.help")
"""帮助域日志（非法存量锚点跳过时只告警，不阻断解析）。"""

_MODELS: ConcurrentStableDict[HelpAnchorKind, Any] = ConcurrentStableDict(
    {
        HelpAnchorKind.MENU: SysMenu,
        HelpAnchorKind.FORM: SysForm,
        HelpAnchorKind.FIELD: SysField,
        HelpAnchorKind.BUTTON: SysButton,
        HelpAnchorKind.ACTION: SysAction,
    }
)
"""节点类型 → ORM 模型（与 `ANCHOR_TABLES` 同序同义）。"""


@dataclass(frozen=True)
class HelpAnchorEntry(BaseValueObject):
    """一条已登记的帮助锚点（可读快照）。

    Attributes:
        kind: 节点类型。
        table: 逻辑表名。
        model_id: 记录主键。
        help_key: 归一后的锚点值。
    """

    kind: HelpAnchorKind
    table: str
    model_id: int
    help_key: str


async def find_help_key_conflict(
    session: DbSession,
    help_key: str,
    *,
    exclude_kind: HelpAnchorKind | None = None,
    exclude_id: int | None = None,
) -> HelpAnchorEntry | None:
    """探测 `help_key` 是否已被其它元数据行占用（跨五表；软删除行不参与）。

    Args:
        session: 平台库会话。
        help_key: 归一后的锚点值。
        exclude_kind: 排除的节点类型（更新自身时传）。
        exclude_id: 排除的记录主键（更新自身时传）。

    Returns:
        HelpAnchorEntry | None: 首个冲突行；无冲突返回 `None`。
    """
    for kind, model in _MODELS.items():
        if kind == exclude_kind:
            rows = await _fetch(session, model, help_key)
            rows = ConcurrentStableList(row for row in rows if row.id != exclude_id)
        else:
            rows = await _fetch(session, model, help_key)
        for row in rows:
            return HelpAnchorEntry(
                kind=kind,
                table=ANCHOR_TABLES[kind],
                model_id=cast("int", row.id),
                help_key=cast("str", row.help_key),
            )
    return None


async def list_help_anchors(session: DbSession) -> ConcurrentStableList[HelpAnchorEntry]:
    """列示全部非空锚点（软删除行不参与；跨五表，主键升序）。

    Args:
        session: 平台库会话。

    Returns:
        ConcurrentStableList[HelpAnchorEntry]: 已登记锚点（插入序：按节点类型 → 主键）。
    """
    entries: ConcurrentStableList[HelpAnchorEntry] = ConcurrentStableList()
    for kind, model in _MODELS.items():
        statement = select(model).where(model.help_key.is_not(None), model.deleted_at.is_(None)).order_by(model.id)
        for row in (await session.execute(statement)).scalars().all():
            entries.add(
                HelpAnchorEntry(
                    kind=kind,
                    table=ANCHOR_TABLES[kind],
                    model_id=cast("int", row.id),
                    help_key=cast("str", row.help_key),
                )
            )
    return entries


async def _fetch(session: DbSession, model: Any, help_key: str) -> ConcurrentStableList[Any]:
    """按 `help_key` 取某表未软删行。

    Args:
        session: 平台库会话。
        model: 元数据模型（五表之一）。
        help_key: 归一后的锚点值。

    Returns:
        ConcurrentStableList[Any]: 命中行（同表内可能多行，冲突判定取首行）。
    """
    statement = select(model).where(model.help_key == help_key, model.deleted_at.is_(None)).order_by(model.id)
    return ConcurrentStableList((await session.execute(statement)).scalars().all())


async def load_help_anchor_index(session: DbSession) -> HelpAnchorIndex:
    """按自然键归集锚点索引（只取启用且未软删行；`NULL` 锚点不进索引）。

    归集口径（与任务 08_02 详细设计 §5.2 一致）：

    - 菜单：锚点第 1 / 2 段为产品段 / 模块段，按菜单主键升序；存量非法锚点跳过并告警；
    - 表单：业务码 → 表单锚点；字段：（业务码, 字段键）→ 字段锚点；
    - 按钮：（业务码, 动作码）→ 按钮锚点（经挂接的权限码解析）；动作码：动作码 → 全局兜底锚点。

    Args:
        session: 平台库会话。

    Returns:
        HelpAnchorIndex: 锚点索引（空集合表示该层级无已登记锚点）。
    """
    businesses = await _enabled_rows(session, SysBusiness)
    actions = await _enabled_rows(session, SysAction)
    permissions = await _enabled_rows(session, SysPermission)
    menus = await _enabled_rows(session, SysMenu)
    forms = await _enabled_rows(session, SysForm)
    buttons = await _enabled_rows(session, SysButton)
    fields = await _enabled_rows(session, SysField)

    business_code_by_id: ConcurrentStableDict[int, str] = ConcurrentStableDict(
        (cast("int", row.id), cast("str", row.code)) for row in businesses
    )
    action_code_by_id: ConcurrentStableDict[int, str] = ConcurrentStableDict(
        (cast("int", row.id), cast("str", row.code)) for row in actions
    )
    permission_code_by_id: ConcurrentStableDict[int, str] = ConcurrentStableDict()
    for permission in permissions:
        business_code = business_code_by_id.get(cast("int", permission.business_id))
        action_code = action_code_by_id.get(cast("int", permission.action_id))
        if business_code is None or action_code is None:
            continue
        permission_code_by_id.set(cast("int", permission.id), f"{business_code}:{action_code}")

    menu_anchors: ConcurrentStableList[HelpMenuAnchor] = ConcurrentStableList()
    for menu in menus:
        raw_key = menu.help_key
        if not raw_key:
            continue
        try:
            help_key = validate_help_key(cast("str", raw_key), kind=HelpAnchorKind.MENU)
        except MenuHelpKeyInvalidError:
            _LOGGER.warning("help_anchor_index_invalid_key", table="sys_menu", model_id=menu.id, help_key=raw_key)
            continue
        segments = help_key_segments(cast("str", help_key))
        menu_anchors.add(
            HelpMenuAnchor(
                product=segments[0],
                module_key=segments[1],
                help_key=cast("str", help_key),
                model_id=cast("int", menu.id),
            )
        )

    form_business_by_id: ConcurrentStableDict[int, str] = ConcurrentStableDict()
    form_anchors: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for form in forms:
        business_code = business_code_by_id.get(cast("int", form.business_id))
        if business_code is None:
            continue
        form_business_by_id.set(cast("int", form.id), business_code)
        if form.help_key:
            form_anchors.set(business_code, cast("str", form.help_key))

    field_anchors: ConcurrentStableDict[tuple[str, str], str] = ConcurrentStableDict()
    for field in fields:
        business_code = form_business_by_id.get(cast("int", field.form_id))
        if business_code is None or not field.help_key:
            continue
        field_anchors.set((business_code, cast("str", field.field_key)), cast("str", field.help_key))

    button_anchors: ConcurrentStableDict[tuple[str, str], str] = ConcurrentStableDict()
    for button in buttons:
        if not button.help_key:
            continue
        permission_code = permission_code_by_id.get(cast("int", button.permission_id))
        if permission_code is None:
            continue
        business_code, _, action_code = permission_code.partition(":")
        button_anchors.set((business_code, action_code), cast("str", button.help_key))

    action_anchors: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for action in actions:
        if action.help_key:
            action_anchors.set(cast("str", action.code), cast("str", action.help_key))

    return HelpAnchorIndex(
        menus=ConcurrentStableFrozenList(menu_anchors),
        forms=ConcurrentStableFrozenDict(form_anchors),
        fields=ConcurrentStableFrozenDict(field_anchors),
        buttons=ConcurrentStableFrozenDict(button_anchors),
        actions=ConcurrentStableFrozenDict(action_anchors),
    )


async def _enabled_rows(session: DbSession, model: Any) -> ConcurrentStableList[Any]:
    """取某元数据表启用且未软删的行（主键升序）。

    Args:
        session: 平台库会话。
        model: 元数据模型。

    Returns:
        ConcurrentStableList[Any]: 启用态行。
    """
    statement = select(model).where(model.status == "enabled", model.deleted_at.is_(None)).order_by(model.id)
    return ConcurrentStableList((await session.execute(statement)).scalars().all())
