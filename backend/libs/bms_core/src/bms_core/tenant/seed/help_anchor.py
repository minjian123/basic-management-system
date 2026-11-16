"""帮助锚点种子声明：批量校验与按自然键 upsert（08_01）。

装载面口径（2026-11-17 拍板）：产品清单当前没有菜单 / 表单 / 字段 / 动作声明段，实际装载入口是
平台 `ops.seed_menu` 与产品仓 `[[seeds]]` 入口。本模块给种子提供**同一条**声明通道：

- 声明先做**全量校验**（格式 / 形状 / 声明方产品段 / 批内重复 / 目标行存在 / 跨表唯一）；
- 任一违规**整批拒载**（一条不写），错误信息列出全部违规项；
- 校验通过后**仅差异更新**：目标为空 → 写；与声明不同 → 改；相同 → 跳过；
- **不提供清空语义**：声明未写某行 = 不修改该行（清空走元数据写接口显式置空）。

平台种子在 `bms_core/tenant/seed/menu.py` 里把可选声明表转成 `HelpAnchorDeclaration`；产品仓在自己的
种子入口里调用同一函数，`declaring_product` 取本产品 `product_key`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.exceptions import MenuHelpKeyInvalidError
from bms_core.core.objects import BaseValueObject
from bms_core.db.session import DbSession
from bms_core.help.anchors import HelpAnchorKind, validate_help_key
from bms_core.models.platform.menu_form import SysButton, SysField, SysForm, SysMenu
from bms_core.models.platform.permission_meta import SysAction, SysBusiness, SysPermission
from bms_core.repositories.help_anchor import find_help_key_conflict

__all__ = ["HelpAnchorApplyResult", "HelpAnchorDeclaration", "apply_help_anchor_declarations"]


@dataclass(frozen=True)
class HelpAnchorDeclaration(BaseValueObject):
    """一条锚点装载声明（按自然键定位目标元数据行）。

    Attributes:
        kind: 节点类型。
        help_key: 声明值（五段式；空串视为违规——装载必须显式给出锚点）。
        declaring_product: 声明方产品标识（校验首段；平台传 `platform`）。
        menu_path: 菜单路由路径（`kind=menu` 必填）。
        business_code: 业务码（`kind=form/field/button` 必填）。
        field_key: 字段键（`kind=field` 必填）。
        action_code: 动作码（`kind=button/action` 必填；按钮按「业务码 + 动作码」定位权限码）。
    """

    kind: HelpAnchorKind
    help_key: str
    declaring_product: str
    menu_path: str | None = None
    business_code: str | None = None
    field_key: str | None = None
    action_code: str | None = None


@dataclass(frozen=True)
class HelpAnchorApplyResult(BaseValueObject):
    """装载结果计数。

    Attributes:
        created: 原值为空、本次写入的条数。
        updated: 原值不同、本次覆盖的条数。
        unchanged: 原值相同、跳过的条数。
    """

    created: int
    updated: int
    unchanged: int


async def apply_help_anchor_declarations(
    session: DbSession,
    declarations: ConcurrentStableList[HelpAnchorDeclaration],
) -> HelpAnchorApplyResult:
    """批量校验并 upsert 锚点声明（**整批原子**：任一违规不写任何一条）。

    Args:
        session: 平台库会话（种子所在事务；不自行提交）。
        declarations: 声明清单（插入序）。

    Returns:
        HelpAnchorApplyResult: 新增 / 覆盖 / 跳过计数。

    Raises:
        MenuHelpKeyInvalidError: 格式 / 形状 / 产品段 / 批内重复 / 目标不存在 / 跨表重复（40211，
            `data` 为全部违规项清单）。
    """
    issues: ConcurrentStableList[str] = ConcurrentStableList()
    prepared: ConcurrentStableList[tuple[HelpAnchorDeclaration, str, Any]] = ConcurrentStableList()
    seen_keys: ConcurrentStableSet[str] = ConcurrentStableSet()
    for declaration in declarations:
        label = _describe(declaration)
        try:
            value = validate_help_key(
                declaration.help_key,
                kind=declaration.kind,
                declaring_product=declaration.declaring_product,
            )
        except MenuHelpKeyInvalidError as exc:
            issues.add(f"{label}：{exc.message}")
            continue
        if value is None:
            issues.add(f"{label}：装载声明必须给出 help_key（空值不清空、也不代表未登记）")
            continue
        if value in seen_keys:
            issues.add(f"{label}：批内 help_key 重复：{value!r}")
            continue
        seen_keys.add(value)
        target = await _resolve_target(session, declaration)
        if target is None:
            issues.add(f"{label}：目标元数据不存在（自然键未命中）")
            continue
        conflict = await find_help_key_conflict(
            session, value, exclude_kind=declaration.kind, exclude_id=cast("int", target.id)
        )
        if conflict is not None:
            issues.add(f"{label}：help_key 已被 {conflict.table}#{conflict.model_id} 占用：{value!r}")
            continue
        prepared.add((declaration, value, target))
    if issues:
        raise MenuHelpKeyInvalidError("帮助锚点装载声明非法：" + "；".join(issues), data=issues)

    created = 0
    updated = 0
    unchanged = 0
    for _declaration, value, target in prepared:
        current = cast("str | None", target.help_key)
        if current is None:
            created += 1
        elif current != value:
            updated += 1
        else:
            unchanged += 1
            continue
        target.help_key = value
    if created or updated:
        await session.flush()
    return HelpAnchorApplyResult(created=created, updated=updated, unchanged=unchanged)


def _describe(declaration: HelpAnchorDeclaration) -> str:
    """声明摘要（错误信息定位用）。

    Args:
        declaration: 锚点声明。

    Returns:
        str: 形如 `menu(/sys/users)=platform:platform:::` 的摘要。
    """
    parts: ConcurrentStableList[str] = ConcurrentStableList((declaration.kind.value,))
    if declaration.menu_path:
        parts.add(f"path={declaration.menu_path}")
    if declaration.business_code:
        parts.add(f"business={declaration.business_code}")
    if declaration.field_key:
        parts.add(f"field={declaration.field_key}")
    if declaration.action_code:
        parts.add(f"action={declaration.action_code}")
    return f"{parts[0]}({', '.join(parts[1:])})={declaration.help_key!r}"


async def _resolve_target(session: DbSession, declaration: HelpAnchorDeclaration) -> Any | None:
    """按自然键定位目标元数据行（未软删）。

    Args:
        session: 平台库会话。
        declaration: 锚点声明。

    Returns:
        Any | None: 命中的 ORM 行；自然键缺失或未命中返回 `None`。
    """
    if declaration.kind is HelpAnchorKind.MENU:
        if not declaration.menu_path:
            return None
        statement = select(SysMenu).where(SysMenu.path == declaration.menu_path, SysMenu.deleted_at.is_(None))
        return (await session.execute(statement)).scalars().first()
    if declaration.kind is HelpAnchorKind.ACTION:
        if not declaration.action_code:
            return None
        statement = select(SysAction).where(SysAction.code == declaration.action_code, SysAction.deleted_at.is_(None))
        return (await session.execute(statement)).scalars().first()
    if not declaration.business_code:
        return None
    business = (
        (
            await session.execute(
                select(SysBusiness).where(
                    SysBusiness.code == declaration.business_code, SysBusiness.deleted_at.is_(None)
                )
            )
        )
        .scalars()
        .first()
    )
    if business is None:
        return None
    form = (
        (await session.execute(select(SysForm).where(SysForm.business_id == business.id, SysForm.deleted_at.is_(None))))
        .scalars()
        .first()
    )
    if form is None:
        return None
    if declaration.kind is HelpAnchorKind.FORM:
        return form
    if declaration.kind is HelpAnchorKind.FIELD:
        if not declaration.field_key:
            return None
        statement = select(SysField).where(
            SysField.form_id == form.id,
            SysField.field_key == declaration.field_key,
            SysField.deleted_at.is_(None),
        )
        return (await session.execute(statement)).scalars().first()
    if not declaration.action_code:
        return None
    action = (
        (
            await session.execute(
                select(SysAction).where(SysAction.code == declaration.action_code, SysAction.deleted_at.is_(None))
            )
        )
        .scalars()
        .first()
    )
    if action is None:
        return None
    permission = (
        (
            await session.execute(
                select(SysPermission).where(
                    SysPermission.business_id == business.id,
                    SysPermission.action_id == action.id,
                    SysPermission.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .first()
    )
    if permission is None:
        return None
    statement = select(SysButton).where(
        SysButton.form_id == form.id,
        SysButton.permission_id == permission.id,
        SysButton.deleted_at.is_(None),
    )
    return (await session.execute(statement)).scalars().first()
