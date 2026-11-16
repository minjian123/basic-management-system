"""帮助锚点（`help_key`）跨表唯一性读助手（08_01）。

`help_key` 散布在五张元数据表（菜单 / 表单 / 字段 / 按钮 / 动作码），唯一性口径是**跨表全局唯一**。
量级很小（元数据百级）、写入频次低，故读侧统一走本模块的整表探测，不在业务侧各写一份 SQL：

- `find_help_key_conflict`：写接口与装载声明保存前探测冲突（可排除自身行）；
- `list_help_anchors`：列示全部非空锚点（08_04 覆盖率台账与启动期对账复用）。

不加数据库唯一约束：五表分别建 `(help_key, deleted_at)` 唯一键会因达梦把复合唯一中的 NULL 视同相等，
使多条未登记行互撞（既有已知方言差异），由应用层保证唯一。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.objects import BaseValueObject
from bms_core.db.session import DbSession
from bms_core.help.anchors import ANCHOR_TABLES, HelpAnchorKind
from bms_core.models.platform.menu_form import SysButton, SysField, SysForm, SysMenu
from bms_core.models.platform.permission_meta import SysAction

__all__ = ["HelpAnchorEntry", "find_help_key_conflict", "list_help_anchors"]

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
