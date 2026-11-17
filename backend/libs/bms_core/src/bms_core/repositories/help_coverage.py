"""帮助覆盖率台账只读快照（08_04）。

一个平台库会话内读齐覆盖率引擎所需的元数据与锚点，**只读、不写、不缓存**：

- 动作：`sys_button` → 权限码（业务码 / 动作码）→ 表单 → 菜单路径；
- 菜单：`sys_menu` → `sys_menu_form` → 表单业务码；
- 分组：`sys_module` 的 `business_code → (product_key, module_key)`；
- 参考：表单 / 字段锚点与动作码兜底锚点；
- 锚点：复用 `list_help_anchors`（跨五表全局锚点，08_01 同一读助手）。

口径见任务 08_04 详细设计 §5.1 / §5.2；本模块只做行投影，不做覆盖判定（判定在
`bms_core.help.coverage` 的纯函数引擎里）。
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import select

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.db.session import DbSession
from bms_core.help.coverage import (
    HelpCoverageAction,
    HelpCoverageAnchor,
    HelpCoverageFallback,
    HelpCoverageMenu,
    HelpCoverageModule,
    HelpCoverageReferenceRow,
    HelpCoverageSnapshot,
)
from bms_core.models.platform.catalog import SysModule
from bms_core.models.platform.menu_form import SysButton, SysField, SysForm, SysMenu, SysMenuForm
from bms_core.models.platform.permission_meta import SysAction, SysBusiness, SysPermission
from bms_core.repositories.help_anchor import list_help_anchors

__all__ = ["load_help_coverage_snapshot"]


async def load_help_coverage_snapshot(session: DbSession) -> HelpCoverageSnapshot:
    """读取覆盖率所需元数据与锚点（启用且未软删；结果顺序确定）。

    Args:
        session: 平台库只读会话（元数据五表 + 模块登记 + 锚点）。

    Returns:
        HelpCoverageSnapshot: 覆盖率快照。
    """
    businesses = await _enabled(session, SysBusiness)
    actions = await _enabled(session, SysAction)
    permissions = await _enabled(session, SysPermission)
    forms = await _enabled(session, SysForm)
    menu_forms = await _alive(session, SysMenuForm)
    menus = await _enabled(session, SysMenu)
    buttons = await _enabled(session, SysButton)
    fields = await _enabled(session, SysField)
    modules = await _enabled(session, SysModule)
    anchors = await list_help_anchors(session)

    business_code_by_id: ConcurrentStableDict[int, str] = ConcurrentStableDict(
        (cast("int", row.id), cast("str", row.code)) for row in businesses
    )
    action_code_by_id: ConcurrentStableDict[int, str] = ConcurrentStableDict(
        (cast("int", row.id), cast("str", row.code)) for row in actions
    )
    form_business_by_id: ConcurrentStableDict[int, str] = ConcurrentStableDict(
        (cast("int", row.id), business_code_by_id[cast("int", row.business_id)])
        for row in forms
        if cast("int", row.business_id) in business_code_by_id
    )
    menu_path_by_id: ConcurrentStableDict[int, str] = ConcurrentStableDict(
        (cast("int", row.id), cast("str", row.path)) for row in menus
    )
    form_menu_paths: ConcurrentStableDict[int, ConcurrentStableList[str]] = ConcurrentStableDict()
    for link in menu_forms:
        form_id = cast("int", link.form_id)
        path = menu_path_by_id.get(cast("int", link.menu_id))
        if path is None:
            continue
        bucket = form_menu_paths.get(form_id)
        if bucket is None:
            new_bucket: ConcurrentStableList[str] = ConcurrentStableList()
            form_menu_paths.set(form_id, new_bucket)
            bucket = new_bucket
        bucket.add(path)

    permission_code_by_id: ConcurrentStableDict[int, tuple[str, str]] = ConcurrentStableDict()
    business_codes_with_permission: ConcurrentStableList[str] = ConcurrentStableList()
    seen_businesses: ConcurrentStableDict[str, bool] = ConcurrentStableDict()
    for permission in permissions:
        business_code = business_code_by_id.get(cast("int", permission.business_id))
        action_code = action_code_by_id.get(cast("int", permission.action_id))
        if business_code is None or action_code is None:
            continue
        permission_code_by_id.set(cast("int", permission.id), (business_code, action_code))
        if not seen_businesses.get(business_code):
            seen_businesses.set(business_code, True)
            business_codes_with_permission.add(business_code)

    action_fallback_by_code: ConcurrentStableDict[str, str | None] = ConcurrentStableDict(
        (cast("str", row.code), cast("str | None", row.help_key)) for row in actions
    )

    action_rows: ConcurrentStableList[HelpCoverageAction] = ConcurrentStableList()
    for button in buttons:
        permission = permission_code_by_id.get(cast("int", button.permission_id))
        if permission is None:
            continue
        form_id = cast("int", button.form_id)
        business_code = form_business_by_id.get(form_id)
        if business_code is None:
            continue
        paths = form_menu_paths.get(form_id, ConcurrentStableList())
        action_rows.add(
            HelpCoverageAction(
                model_id=cast("int", button.id),
                business_code=business_code,
                action_code=permission[1],
                button_name=cast("str", button.name),
                menu_paths=ConcurrentStableFrozenList(sorted(paths)),
                help_key=cast("str | None", button.help_key),
                fallback_help_key=action_fallback_by_code.get(permission[1]),
            )
        )

    menu_rows: ConcurrentStableList[HelpCoverageMenu] = ConcurrentStableList()
    business_codes_by_menu: ConcurrentStableDict[int, ConcurrentStableList[str]] = ConcurrentStableDict()
    for link in menu_forms:
        menu_id = cast("int", link.menu_id)
        form_id = cast("int", link.form_id)
        business_code = form_business_by_id.get(form_id)
        if business_code is None:
            continue
        bucket = business_codes_by_menu.get(menu_id)
        if bucket is None:
            new_bucket: ConcurrentStableList[str] = ConcurrentStableList()
            business_codes_by_menu.set(menu_id, new_bucket)
            bucket = new_bucket
        if business_code not in bucket:
            bucket.add(business_code)
    for menu in menus:
        codes = business_codes_by_menu.get(cast("int", menu.id), ConcurrentStableList())
        menu_rows.add(
            HelpCoverageMenu(
                model_id=cast("int", menu.id),
                path=cast("str", menu.path),
                business_codes=ConcurrentStableFrozenList(sorted(codes)),
                help_key=cast("str | None", menu.help_key),
            )
        )

    reference_rows: ConcurrentStableList[HelpCoverageReferenceRow] = ConcurrentStableList()
    for form in forms:
        business_code = form_business_by_id.get(cast("int", form.id))
        if business_code is None:
            continue
        reference_rows.add(
            HelpCoverageReferenceRow(
                business_code=business_code,
                kind="form",
                help_key=cast("str | None", form.help_key),
            )
        )
    for field in fields:
        business_code = form_business_by_id.get(cast("int", field.form_id))
        if business_code is None:
            continue
        reference_rows.add(
            HelpCoverageReferenceRow(
                business_code=business_code,
                kind="field",
                help_key=cast("str | None", field.help_key),
            )
        )

    module_rows: ConcurrentStableList[HelpCoverageModule] = ConcurrentStableList()
    for module in modules:
        business_code = cast("str | None", module.business_code)
        product_key = cast("str | None", module.product_key)
        if not business_code or not product_key:
            continue
        module_rows.add(
            HelpCoverageModule(
                business_code=business_code,
                product_key=product_key,
                module_key=cast("str", module.module_key),
                registered=True,
            )
        )

    anchor_rows: ConcurrentStableList[HelpCoverageAnchor] = ConcurrentStableList(
        HelpCoverageAnchor(
            kind=entry.kind,
            table=entry.table,
            model_id=entry.model_id,
            help_key=entry.help_key,
        )
        for entry in anchors
    )

    return HelpCoverageSnapshot(
        actions=ConcurrentStableFrozenList(action_rows),
        menus=ConcurrentStableFrozenList(menu_rows),
        modules=ConcurrentStableFrozenList(module_rows),
        reference_rows=ConcurrentStableFrozenList(reference_rows),
        action_fallbacks=ConcurrentStableFrozenList(
            HelpCoverageFallback(action_code=code, help_key=help_key)
            for code, help_key in action_fallback_by_code.items()
        ),
        anchors=ConcurrentStableFrozenList(anchor_rows),
        business_codes_with_permission=ConcurrentStableFrozenList(business_codes_with_permission),
    )


async def _enabled(session: DbSession, model: Any) -> ConcurrentStableList[Any]:
    """取启用且未软删的元数据行（主键升序）。

    Args:
        session: 平台库会话。
        model: 元数据模型（含 `status` / `deleted_at` 列）。

    Returns:
        ConcurrentStableList[Any]: 行集合。
    """
    statement = select(model).where(model.status == "enabled", model.deleted_at.is_(None)).order_by(model.id)
    return ConcurrentStableList((await session.execute(statement)).scalars().all())


async def _alive(session: DbSession, model: Any) -> ConcurrentStableList[Any]:
    """取未软删的行（无 `status` 约束；主键升序）。

    Args:
        session: 平台库会话。
        model: 模型（含 `deleted_at` 列）。

    Returns:
        ConcurrentStableList[Any]: 行集合。
    """
    statement = select(model).where(model.deleted_at.is_(None)).order_by(model.id)
    return ConcurrentStableList((await session.execute(statement)).scalars().all())
