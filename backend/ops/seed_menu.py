"""菜单元数据种子脚本（幂等）：平台库业务 / 动作权限码与平台 MVP 页面挂接链（需求 07-5）。

用法：

```bash
cd backend
uv run python -m ops.seed_menu
uv run python -m ops.seed_menu --dry-run
```

- URL 解析复用 `ops.seed_tenant.resolve_url(service="platform")`（`sys_menu` 等归属平台服务库）；
- 幂等：业务码按 `code`、动作码按 `(business_id, code)`、表单按 `business_id`、菜单按 `path`、
  菜单 ↔ 表单关联按 `(menu_id, form_id)`、按钮按 `(form_id, action_id)`、字段按 `(form_id, field_key)`
  判存（`deleted_at IS NULL`），不存在插入、存在跳过；
- 菜单 ↔ 表单为**多对多**（02_03 返工）：表单先按 `business_id` upsert，再经 `sys_menu_form` 关联入口；
- 业务码清单取自《架构设计 · 权限计算引擎》「业务与动作权限码清单」节；动作码归属按
  《英文简称规范》「动作码简称」节的典型权限码落地；
- **产品管理面权限码（12_04）**：产品业务码与域级 / 专属动作码随产品接入登记（首例 mdm 组织域
  `org` 及其 `org:query` / `org:create` / `org:update` / `org:delete` / `org:move`）；
- 建表分支兼容保留（Alembic 落库后由 `alembic -n alembic:platform:platform upgrade head` 建表；
  SQLite 开发库由启动期自动建表）。
"""

import argparse
import asyncio
from typing import Any, cast

from sqlalchemy import Table, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.keys import PLATFORM_SERVICE_KEY
from bms_platform.models.menu import (
    SysAction,
    SysActionI18n,
    SysBusiness,
    SysBusinessI18n,
    SysButton,
    SysField,
    SysFieldI18n,
    SysForm,
    SysMenu,
    SysMenuForm,
    SysMenuI18n,
)
from ops.seed_tenant import resolve_url

ZH = "zh-CN"
EN = "en-US"

BUSINESS_SEEDS: tuple[tuple[str, str, str], ...] = (
    ("sys", "平台运维总控", "Platform operations"),
    ("tenant", "租户管理", "Tenant management"),
    ("menu", "菜单/表单/按钮/字段维护", "Menu metadata"),
    ("business", "业务权限维护", "Business permissions"),
    ("action", "动作权限维护", "Action permissions"),
    ("user", "用户管理", "User management"),
    ("post", "岗位管理", "Position management"),
    ("dept", "部门管理", "Department management"),
    ("org", "组织主数据", "Organization master data"),
    ("role", "角色管理", "Role management"),
    ("dict", "字典管理", "Dictionary management"),
    ("config", "系统参数", "System configuration"),
    ("dashboard", "首页工作台", "Dashboard"),
    ("formdesign", "表单定制", "Form designer"),
    ("file", "文件管理", "File management"),
    ("session", "会话管理", "Session management"),
    ("mail", "邮件与短信通知", "Mail and SMS"),
    ("task", "任务调度", "Task scheduling"),
    ("archive", "归档管理", "Archive management"),
    ("i18n", "国际化管理", "Internationalization"),
    ("sso", "SSO 身份绑定", "SSO binding"),
    ("recycle", "回收站", "Recycle bin"),
    ("backup", "备份管理", "Backup management"),
    ("ai", "AI 助手与模型配置", "AI assistant"),
    ("open", "开放接口与 Webhook", "Open API"),
    ("idp", "外部 IdP 配置", "Identity provider"),
    ("data", "敏感数据脱敏", "Data masking"),
    ("wf", "工作流", "Workflow"),
    ("notice", "公告管理", "Notice management"),
    ("help", "帮助中心", "Help center"),
    ("pur", "采购管理", "Purchasing"),
    ("pay", "收付款管理", "Payment"),
    ("notification", "通知中心", "Notification center"),
    ("rpt", "报表与大屏", "Reports"),
    ("monitor", "系统监控", "System monitoring"),
    ("log", "审计日志", "Audit log"),
    ("import", "Excel 批量导入", "Bulk import"),
    ("export", "列表导出", "Export"),
    ("query", "列表查询方案管理", "Query scheme"),
)
"""业务权限码种子（《架构设计 · 权限计算引擎》「业务与动作权限码清单」节）。"""

ACTION_SEEDS: tuple[tuple[str, str, str, str], ...] = (
    ("sys", "query", "查询", "Query"),
    ("sys", "manage", "管理（含查询与维护）", "Manage"),
    ("menu", "query", "查询", "Query"),
    ("menu", "create", "新建", "Create"),
    ("menu", "update", "修改", "Update"),
    ("menu", "delete", "删除", "Delete"),
    ("business", "query", "查询", "Query"),
    ("action", "query", "查询", "Query"),
    ("user", "query", "查询", "Query"),
    ("user", "create", "新建", "Create"),
    ("user", "update", "修改", "Update"),
    ("user", "delete", "删除", "Delete"),
    ("user", "lock", "账号锁定", "Lock account"),
    ("user", "unlock", "账号解锁", "Unlock account"),
    ("user", "reset_pwd", "重置密码", "Reset password"),
    ("user", "assign_role", "分配角色", "Assign role"),
    ("role", "query", "查询", "Query"),
    ("role", "create", "新建", "Create"),
    ("role", "update", "修改", "Update"),
    ("role", "delete", "删除", "Delete"),
    ("role", "grant", "授权/分配", "Grant"),
    ("tenant", "query", "查询", "Query"),
    ("tenant", "create", "开通", "Create"),
    ("tenant", "update", "修改", "Update"),
    ("tenant", "quota", "租户配额配置", "Quota"),
    ("session", "query", "查询", "Query"),
    ("session", "kick", "强制踢出", "Kick"),
    ("dict", "query", "查询", "Query"),
    ("dict", "manage", "管理（含查询与维护）", "Manage"),
    ("dict", "query-scheme", "高级查询方案管理", "Query scheme"),
    ("task", "query", "查询", "Query"),
    ("task", "manage", "管理（含查询与维护）", "Manage"),
    ("task", "trigger", "手动触发", "Trigger"),
    ("file", "query", "查询", "Query"),
    ("file", "upload", "上传", "Upload"),
    ("file", "download", "下载", "Download"),
    ("file", "delete", "删除", "Delete"),
    ("monitor", "view", "查看", "View"),
    ("monitor", "cache", "缓存清理与热数据刷新", "Cache"),
    ("rpt", "query", "查询", "Query"),
    ("rpt", "view", "查看", "View"),
    ("rpt", "design", "设计", "Design"),
    ("wf", "query", "查询", "Query"),
    ("wf", "approve", "审批（同意/驳回/撤回）", "Approve"),
    ("wf", "define", "流程定义与版本管理", "Define"),
    ("mail", "query", "查询", "Query"),
    ("mail", "send", "发送", "Send"),
    ("sso", "query", "查询", "Query"),
    ("sso", "bind", "SSO 身份绑定查看/管理", "Bind"),
    ("recycle", "query", "查询", "Query"),
    ("recycle", "restore", "回收站恢复", "Restore"),
    ("ai", "query", "查询", "Query"),
    ("ai", "chat", "AI 对话", "Chat"),
    ("ai", "manage", "模型配置", "Manage"),
    ("data", "plain", "敏感字段明文查看", "Plain text"),
    ("query", "query", "查询", "Query"),
    ("query", "scheme", "列表查询方案管理", "Scheme"),
    ("query", "manage", "管理（含查询与维护）", "Manage"),
    ("open", "query", "查询", "Query"),
    ("open", "call", "以第三方身份调用", "Call"),
    ("import", "query", "查询", "Query"),
    ("import", "execute", "执行导入", "Execute"),
    ("export", "query", "查询", "Query"),
    ("pay", "refund", "退款", "Refund"),
    ("log", "query", "查询", "Query"),
    ("notice", "query", "查询", "Query"),
    ("help", "query", "查询", "Query"),
    ("notification", "query", "查询", "Query"),
    ("config", "query", "查询", "Query"),
    ("dashboard", "query", "查询", "Query"),
    ("formdesign", "query", "查询", "Query"),
    ("i18n", "query", "查询", "Query"),
    ("archive", "query", "查询", "Query"),
    ("backup", "query", "查询", "Query"),
    ("post", "query", "查询", "Query"),
    ("dept", "query", "查询", "Query"),
    ("org", "query", "查询", "Query"),
    ("org", "create", "新建", "Create"),
    ("org", "update", "修改", "Update"),
    ("org", "delete", "删除", "Delete"),
    ("org", "move", "移动", "Move"),
    ("idp", "query", "查询", "Query"),
    ("pur", "query", "查询", "Query"),
)
"""动作权限码种子（归属业务码 + 名称；《英文简称规范》「动作码简称」节）。"""

MENU_SEEDS: tuple[tuple[int, str, str, str, str | None, str | None, int, bool, str | None], ...] = (
    (0, "/sys", "系统管理", "System", None, "el:setting", 10, False, None),
    (1, "/sys/users", "用户管理", "Users", "sys/users", "el:user", 1, False, "user"),
    (1, "/sys/roles", "角色管理", "Roles", "sys/roles", "el:key", 2, False, "role"),
    (1, "/sys/account-locks", "账号锁定", "Account locks", "sys/account-locks", "el:lock", 3, False, "user"),
    (1, "/sys/menus", "菜单管理", "Menus", "sys/menus", "el:menu", 4, False, "menu"),
    (1, "/sys/businesses", "业务权限管理", "Business permissions", "sys/businesses", "el:list", 5, False, "business"),
    (1, "/sys/actions", "动作权限管理", "Action permissions", "sys/actions", "el:operation", 6, False, "action"),
    (0, "/platform", "平台管理", "Platform", None, "el:platform", 20, False, None),
    (8, "/platform/tenants", "租户管理", "Tenants", "platform/tenants", "el:office-building", 1, False, "tenant"),
    (0, "/monitor", "系统监控", "Monitoring", None, "el:monitor", 30, False, None),
    (10, "/monitor/sessions", "会话管理", "Sessions", "monitor/sessions", "el:connection", 1, False, "session"),
)

BUTTON_SEEDS: tuple[tuple[str, str, str, str, int], ...] = (
    ("/sys/users", "新增", "create", "toolbar", 1),
    ("/sys/users", "编辑", "update", "toolbar", 2),
    ("/sys/users", "删除", "delete", "toolbar", 3),
    ("/sys/users", "锁定", "lock", "interface", 4),
    ("/sys/users", "解锁", "unlock", "interface", 5),
    ("/sys/users", "重置密码", "reset_pwd", "interface", 6),
    ("/sys/users", "分配角色", "assign_role", "interface", 7),
    ("/sys/roles", "新增", "create", "toolbar", 1),
    ("/sys/roles", "编辑", "update", "toolbar", 2),
    ("/sys/roles", "删除", "delete", "toolbar", 3),
    ("/sys/roles", "授权", "grant", "interface", 4),
    ("/sys/account-locks", "解锁", "unlock", "toolbar", 1),
    ("/sys/menus", "新增", "create", "toolbar", 1),
    ("/sys/menus", "编辑", "update", "toolbar", 2),
    ("/sys/menus", "删除", "delete", "toolbar", 3),
    ("/platform/tenants", "开通", "create", "toolbar", 1),
    ("/platform/tenants", "编辑", "update", "toolbar", 2),
    ("/platform/tenants", "配额", "quota", "interface", 3),
    ("/monitor/sessions", "强制踢出", "kick", "toolbar", 1),
)

FIELD_SEEDS: tuple[tuple[str, str, str, str, str, int], ...] = (
    ("/sys/users", "username", "用户名", "Username", "input", 1),
    ("/sys/users", "display_name", "姓名", "Display name", "input", 2),
    ("/sys/users", "status", "状态", "Status", "select", 3),
    ("/sys/users", "dept_id", "部门", "Department", "org-select", 4),
    ("/sys/roles", "code", "角色标识", "Role code", "input", 1),
    ("/sys/roles", "name", "角色名", "Role name", "input", 2),
    ("/sys/roles", "status", "状态", "Status", "select", 3),
    ("/sys/account-locks", "username", "用户名", "Username", "input", 1),
    ("/sys/account-locks", "lock_type", "锁定类型", "Lock type", "select", 2),
    ("/sys/menus", "name", "菜单名", "Menu name", "input", 1),
    ("/sys/menus", "path", "路由路径", "Path", "input", 2),
    ("/sys/menus", "icon", "图标", "Icon", "icon", 3),
    ("/sys/menus", "status", "状态", "Status", "select", 4),
    ("/sys/businesses", "code", "业务码", "Business code", "input", 1),
    ("/sys/businesses", "name", "名称", "Name", "input", 2),
    ("/sys/businesses", "status", "状态", "Status", "select", 3),
    ("/sys/actions", "code", "动作码", "Action code", "input", 1),
    ("/sys/actions", "name", "名称", "Name", "input", 2),
    ("/platform/tenants", "code", "租户编码", "Tenant code", "input", 1),
    ("/platform/tenants", "name", "租户名称", "Tenant name", "input", 2),
    ("/platform/tenants", "domain", "域名", "Domain", "input", 3),
    ("/platform/tenants", "status", "状态", "Status", "select", 4),
)


_MENU_TABLES: tuple[Table, ...] = (
    cast("Table", SysBusiness.__table__),
    cast("Table", SysBusinessI18n.__table__),
    cast("Table", SysAction.__table__),
    cast("Table", SysActionI18n.__table__),
    cast("Table", SysMenu.__table__),
    cast("Table", SysMenuI18n.__table__),
    cast("Table", SysForm.__table__),
    cast("Table", SysMenuForm.__table__),
    cast("Table", SysButton.__table__),
    cast("Table", SysField.__table__),
    cast("Table", SysFieldI18n.__table__),
)
"""菜单元数据十一表（含 `sys_menu_form` 关联；建表用；显式取 `Table` 以避免联合类型推导）。"""


async def _exists(session: AsyncSession, model: Any, *conditions: Any) -> bool:
    """判存（按条件 + 未软删除）。

    Args:
        session: 数据库会话。
        model: ORM 模型。
        conditions: 过滤条件。

    Returns:
        bool: 已存在为 True。
    """
    statement = select(model).where(*conditions, model.deleted_at.is_(None)).limit(1)
    return (await session.execute(statement)).scalars().first() is not None


async def _add_i18n(session: AsyncSession, model: Any, key: str, owner_id: int, zh: str, en: str) -> int:
    """补多语言文案（缺则插）。

    Args:
        session: 数据库会话。
        model: 多语言附表模型。
        key: 主表 ID 列名。
        owner_id: 主表 ID。
        zh: 中文文案。
        en: 英文文案。

    Returns:
        int: 新增行数。
    """
    created = 0
    for locale, name in ((ZH, zh), (EN, en)):
        key_attr = getattr(model, key)
        conditions = (key_attr == owner_id, model.locale == locale)
        if await _exists(session, model, *conditions):
            continue
        session.add(model(**{key: owner_id, "locale": locale, "name": name}))
        created += 1
    return created


async def seed_menu(url: str) -> tuple[int, int]:
    """建表并幂等写入菜单元数据种子。

    Args:
        url: 平台库连接串。

    Returns:
        tuple[int, int]: (新增行数, 跳过行数)。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    created = 0
    skipped = 0
    try:
        async with engine.begin() as connection:
            for table in _MENU_TABLES:
                await connection.run_sync(table.create, checkfirst=True)
        async with factory() as session:
            business_ids = ConcurrentStableDict[str, int]()
            for code, zh, en in BUSINESS_SEEDS:
                existing = (
                    (
                        await session.execute(
                            select(SysBusiness).where(SysBusiness.code == code, SysBusiness.deleted_at.is_(None))
                        )
                    )
                    .scalars()
                    .first()
                )
                if existing is None:
                    existing = SysBusiness(code=code, name=zh, status="enabled")
                    session.add(existing)
                    await session.flush()
                    created += 1
                else:
                    skipped += 1
                business_ids.set(code, existing.id)
                created += await _add_i18n(session, SysBusinessI18n, "business_id", existing.id, zh, en)

            action_ids = ConcurrentStableDict[tuple[str, str], int]()
            for business_code, code, zh, en in ACTION_SEEDS:
                business_id = business_ids.get(business_code, 0)
                existing_action = (
                    (
                        await session.execute(
                            select(SysAction).where(
                                SysAction.business_id == business_id,
                                SysAction.code == code,
                                SysAction.deleted_at.is_(None),
                            )
                        )
                    )
                    .scalars()
                    .first()
                )
                if existing_action is None:
                    existing_action = SysAction(business_id=business_id, code=code, name=zh, status="enabled")
                    session.add(existing_action)
                    await session.flush()
                    created += 1
                else:
                    skipped += 1
                action_ids.set((business_code, code), existing_action.id)
                created += await _add_i18n(session, SysActionI18n, "action_id", existing_action.id, zh, en)

            menu_ids = ConcurrentStableDict[str, int]()
            form_ids_by_menu = ConcurrentStableDict[int, int]()
            for parent_index, path, zh, en, component, icon, sort, hidden, business_code in MENU_SEEDS:
                parent_id = 0
                if parent_index:
                    parent_id = menu_ids.get(MENU_SEEDS[parent_index - 1][1], 0)
                existing_menu = (
                    (await session.execute(select(SysMenu).where(SysMenu.path == path, SysMenu.deleted_at.is_(None))))
                    .scalars()
                    .first()
                )
                if existing_menu is None:
                    existing_menu = SysMenu(
                        parent_id=parent_id,
                        name=zh,
                        path=path,
                        component=component,
                        icon=icon,
                        sort=sort,
                        hidden=hidden,
                        status="enabled",
                    )
                    session.add(existing_menu)
                    await session.flush()
                    created += 1
                else:
                    skipped += 1
                menu_ids.set(path, existing_menu.id)
                created += await _add_i18n(session, SysMenuI18n, "menu_id", existing_menu.id, zh, en)
                if business_code is not None:
                    business_id = business_ids[business_code]
                    form = (
                        (
                            await session.execute(
                                select(SysForm).where(SysForm.business_id == business_id, SysForm.deleted_at.is_(None))
                            )
                        )
                        .scalars()
                        .first()
                    )
                    if form is None:
                        form = SysForm(business_id=business_id, component=component, status="enabled")
                        session.add(form)
                        await session.flush()
                        created += 1
                    else:
                        skipped += 1
                    form_ids_by_menu.set(existing_menu.id, form.id)
                    link = (
                        (
                            await session.execute(
                                select(SysMenuForm).where(
                                    SysMenuForm.menu_id == existing_menu.id,
                                    SysMenuForm.form_id == form.id,
                                    SysMenuForm.deleted_at.is_(None),
                                )
                            )
                        )
                        .scalars()
                        .first()
                    )
                    if link is None:
                        session.add(SysMenuForm(menu_id=existing_menu.id, form_id=form.id))
                        created += 1
                    else:
                        skipped += 1

            for path, zh, action_code, button_type, sort in BUTTON_SEEDS:
                form_id = form_ids_by_menu.get(menu_ids.get(path, 0), 0)
                if not form_id:
                    continue
                business_code = next(seed[8] for seed in MENU_SEEDS if seed[1] == path and seed[8] is not None)
                action_id = action_ids.get((business_code, action_code), 0)
                if await _exists(session, SysButton, SysButton.form_id == form_id, SysButton.action_id == action_id):
                    skipped += 1
                    continue
                session.add(
                    SysButton(
                        form_id=form_id,
                        action_id=action_id,
                        name=zh,
                        type=button_type,
                        sort=sort,
                        status="enabled",
                    )
                )
                created += 1

            for path, field_key, zh, en, field_type, sort in FIELD_SEEDS:
                form_id = form_ids_by_menu.get(menu_ids.get(path, 0), 0)
                if not form_id:
                    continue
                existing_field = (
                    (
                        await session.execute(
                            select(SysField).where(
                                SysField.form_id == form_id,
                                SysField.field_key == field_key,
                                SysField.deleted_at.is_(None),
                            )
                        )
                    )
                    .scalars()
                    .first()
                )
                if existing_field is None:
                    existing_field = SysField(
                        form_id=form_id,
                        field_key=field_key,
                        name=zh,
                        type=field_type,
                        sort=sort,
                        status="enabled",
                    )
                    session.add(existing_field)
                    await session.flush()
                    created += 1
                else:
                    skipped += 1
                created += await _add_i18n(session, SysFieldI18n, "field_id", existing_field.id, zh, en)

            await session.commit()
    finally:
        await engine.dispose()
    return created, skipped


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="菜单元数据种子（平台库，幂等 upsert）")
    parser.add_argument("--url", default="", help="平台库连接串（缺省读 BMS_MIGRATION_URL / 配置）")
    parser.add_argument("--dry-run", action="store_true", help="仅输出目标库与种子规模")
    return parser


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码。
    """
    args = build_parser().parse_args(argv)
    url = resolve_url(args.url, service=PLATFORM_SERVICE_KEY)
    if args.dry_run:
        target = make_url(url).render_as_string(hide_password=True)
        print(f"[seed_menu] 目标库：{target}")
        print(
            f"[seed_menu] 种子规模：业务 {len(BUSINESS_SEEDS)} / 动作 {len(ACTION_SEEDS)} / "
            f"菜单 {len(MENU_SEEDS)} / 按钮 {len(BUTTON_SEEDS)} / 字段 {len(FIELD_SEEDS)}（dry-run）"
        )
        return 0
    created, skipped = asyncio.run(seed_menu(url))
    print(f"[seed_menu] 新增 {created} 行 / 跳过 {skipped} 行（幂等；重复执行新增为 0）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
