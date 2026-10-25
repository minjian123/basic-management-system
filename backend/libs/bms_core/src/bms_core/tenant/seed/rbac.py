"""内置角色与授权种子（幂等）：三权内置角色 + 在册权限码授权（14_04 自 `ops.seed_rbac` 下沉；`02_04`）。

用法（经 `ops` 同名薄壳，命令与参数不变）：

```bash
cd backend
uv run python -m ops.seed_rbac --tenant demo --dry-run                    # 计划预演
uv run python -m ops.seed_rbac --tenant demo                              # 落库（幂等）
uv run python -m ops.seed_rbac --tenant demo --assign-user admin          # 落库并把 admin 绑到内置系统管理员
uv run python -m ops.seed_rbac --tenant demo --tenant-url "sqlite+aiosqlite:///…" --platform-url "…"
```

- **bootstrap 绑定（`--assign-user`）**：把首个可用账号（`sys_user.code`，或直接给用户主键）绑到内置
  **系统管理员**角色——该角色 `role_type=system` 命中权限引擎的**豁免层级**，使本地开发对全部
  `require_permission` 端点开箱可用（免逐码授权；权限码级判定由权限引擎专项用例覆盖）。账号尚未建号时
  跳过并上报（须先执行建号种子），幂等（已有绑定即跳过）。
- **库定位（两库协同）**：角色域（`sys_role` / `sys_role_permission`）在 **platform 服务租户库**；
  权限码（`sys_permission` / `sys_business` / `sys_action`）在 **platform 服务平台库**——分别解析（租户库复用
  账号种子的「注册库对照表取库名基 → 模板解析」口径，平台库按库键 `platform_{service}` 解析）；
- **幂等**：角色按 `(code, deleted_at IS NULL)`、授权按 `(role_id, perm_type, target_id, source_menu_id,
  deleted_at IS NULL)` 判存——不存在插入、存在跳过，重复执行全为「跳过」；
- **授权目标**：权限码 `业务:动作` → `sys_permission` 行（`perm_type="permission"`、`source_menu_id=0`）；
  平台库未登记的权限码**跳过并上报**（如审计域尚未落地的码）；
- **三权清单（需求 07-6）**：系统管理员持**除 `role:*` 外的全部在册码**（角色域归安全管理员，
  系统 / 审计管理员不得越权授予）；安全管理员持 `role:query/create/update/delete/grant`；
  审计管理员本轮不授权（审计域权限码随审计模块落地）——**安全管理员不属豁免层级**，其可达性
  完全依赖本清单（防 403 自锁的关键一侧）。

归属：本模块属**开通所需的默认数据种子**（基座机制，供任何服务 / 产品复用），只依赖 `bms_core`。
"""

import argparse
import os
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.objects import BaseDataContract
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import PLATFORM_SERVICE_KEY, build_platform_db_key
from bms_core.models.platform.permission_meta import SysAction, SysBusiness, SysPermission
from bms_core.models.platform.role import (
    NO_SOURCE_MENU_ID,
    PERM_TYPE_PERMISSION,
    ROLE_TYPE_AUDIT,
    ROLE_TYPE_SECURITY,
    ROLE_TYPE_SYSTEM,
    SEPARATION_ROLE_TYPES,
    SysRole,
    SysRolePermission,
    SysUserRole,
)
from bms_core.models.platform.user import SysUser
from bms_core.tenant.seed.user import resolve_tenant_basis, resolve_tenant_url

__all__ = [
    "AUDIT_ADMIN_CODES",
    "BUILTIN_ADMIN_ROLES",
    "DEFAULT_ASSIGN_ACCOUNT",
    "ROLE_AUDIT_ADMIN",
    "ROLE_SECURITY_ADMIN",
    "ROLE_SYSTEM_ADMIN",
    "SECURITY_ADMIN_CODES",
    "SYSTEM_ADMIN_CODES",
    "SYSTEM_ADMIN_EXCLUDED_CODES",
    "SeedOutcome",
    "build_parser",
    "main",
    "seed_rbac",
]

ROLE_SYSTEM_ADMIN = "system_admin"
"""系统管理员角色码（内置；豁免层级）。"""

ROLE_SECURITY_ADMIN = "security_admin"
"""安全管理员角色码（内置；**不豁免**，可达性由授权清单决定）。"""

ROLE_AUDIT_ADMIN = "audit_admin"
"""审计管理员角色码（内置；审计域权限码随审计模块落地）。"""

SECURITY_ADMIN_CODES: ConcurrentStableList[str] = ConcurrentStableList(
    (
        "role:query",
        "role:create",
        "role:update",
        "role:delete",
        "role:grant",
    )
)
"""安全管理员授权（角色域全部权限码；需求 07-6「`role` 业务仅安全管理员持有」）。"""

SYSTEM_ADMIN_EXCLUDED_CODES = frozenset(SECURITY_ADMIN_CODES)
"""系统管理员**不**持有的码（角色域；防越权授予）。"""

SYSTEM_ADMIN_CODES: ConcurrentStableList[str] = ConcurrentStableList(
    (
        "menu:query",
        "menu:create",
        "menu:update",
        "menu:delete",
        "business:query",
        "business:manage",
        "business:create",
        "business:update",
        "business:delete",
        "action:query",
        "action:manage",
        "action:create",
        "action:update",
        "action:delete",
        "form:query",
        "form:create",
        "form:update",
        "form:delete",
        "icon:query",
        "icon:manage",
        "icon:create",
        "icon:update",
        "icon:delete",
        "permission:query",
        "permission:manage",
        "permission:create",
        "permission:update",
        "permission:delete",
        "permission:generate",
        "user:query",
        "user:create",
        "user:update",
        "user:delete",
        "user:reset_pwd",
        "user:assign_role",
        "user:lock",
        "user:unlock",
        "session:query",
        "session:kick",
        "sso:bind",
        "open:manage",
        "idp:manage",
        "user-extension:query",
        "user-extension:update",
    )
)
"""系统管理员授权（在册权限码去除角色域码）。与 `require_permission` 在册清单同步维护。"""

DEFAULT_ASSIGN_ACCOUNT = "admin"
"""缺省绑定账号（本地 bootstrap：把首个可用账号绑到内置系统管理员，命中豁免层级）。"""

AUDIT_ADMIN_CODES: ConcurrentStableList[str] = ConcurrentStableList()
"""审计管理员授权（本轮为空；审计域权限码随审计模块落地）。"""

BUILTIN_ADMIN_ROLES: ConcurrentStableList[tuple[str, str, str, ConcurrentStableList[str]]] = ConcurrentStableList(
    (
        (ROLE_SYSTEM_ADMIN, "系统管理员", ROLE_TYPE_SYSTEM, SYSTEM_ADMIN_CODES),
        (ROLE_SECURITY_ADMIN, "安全管理员", ROLE_TYPE_SECURITY, SECURITY_ADMIN_CODES),
        (ROLE_AUDIT_ADMIN, "审计管理员", ROLE_TYPE_AUDIT, AUDIT_ADMIN_CODES),
    )
)
"""三类内置管理员角色与授权清单的**单一来源**（`03_02`；`04_01` 开通种子直接引用）。

元素为 `(角色码, 角色名, role_type, 权限码清单)`；`role_type` 三值即
`SEPARATION_ROLE_TYPES`——同一用户不得兼任其中两类。
"""


@dataclass
class SeedOutcome(BaseDataContract):
    """执行结果（新增 / 跳过计数与缺码清单）。"""

    roles_created: int = 0
    """新增角色数。"""

    roles_skipped: int = 0
    """已存在角色数。"""

    grants_created: int = 0
    """新增授权条目数。"""

    grants_skipped: int = 0
    """已存在授权条目数。"""

    assignments_created: int = 0
    """新增「用户 → 内置角色」绑定数（bootstrap 豁免层级）。"""

    assignments_skipped: int = 0
    """已存在「用户 → 内置角色」绑定数。"""

    assign_unresolved: ConcurrentStableList[str] = field(default_factory=lambda: ConcurrentStableList[str]())
    """待绑定但库中未找到的账号 / 主键（如建号脚本尚未执行）。"""

    missing_codes: ConcurrentStableList[str] = field(default_factory=lambda: ConcurrentStableList[str]())
    """平台库未登记、被跳过的权限码（需先执行菜单种子或补齐产品域动作码）。"""

    assign_conflicts: ConcurrentStableList[str] = field(default_factory=lambda: ConcurrentStableList[str]())
    """因三权互斥（同一账号已持另一类内置管理员）被拒绝的绑定（需求 07-6）。"""


async def seed_rbac(*, tenant_url: str, platform_url: str, assign_user: str = "", dry_run: bool = False) -> SeedOutcome:
    """播种三权内置角色与其授权（幂等），并按需绑定 bootstrap 账号。

    Args:
        tenant_url: platform 服务租户库连接串（角色域）。
        platform_url: platform 服务平台库连接串（业务 / 动作码）。
        assign_user: 待绑定到内置系统管理员的账号（`sys_user.code`）或用户主键（空串跳过）。
        dry_run: 仅预演（不写库）。

    Returns:
        SeedOutcome: 执行结果。
    """
    outcome = SeedOutcome()
    permission_ids = await _load_permission_ids(platform_url)
    plan: ConcurrentStableList[tuple[str, str, str, ConcurrentStableList[str]]] = ConcurrentStableList(
        BUILTIN_ADMIN_ROLES
    )
    engine = create_async_engine(tenant_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            system_role_id = 0
            for code, name, role_type, codes in plan:
                role_id = await _ensure_role(session, code=code, name=name, role_type=role_type, outcome=outcome)
                if code == ROLE_SYSTEM_ADMIN:
                    system_role_id = role_id
                for permission in codes:
                    target_id = permission_ids.get(permission)
                    if target_id is None:
                        if permission not in outcome.missing_codes:
                            outcome.missing_codes.add(permission)
                        continue
                    await _ensure_grant(session, role_id=role_id, target_id=target_id, outcome=outcome)
            if assign_user != "":
                await _ensure_assignment(session, role_id=system_role_id, account=assign_user, outcome=outcome)
            if dry_run:
                await session.rollback()
            else:
                await session.commit()
    finally:
        await engine.dispose()
    return outcome


async def _load_permission_ids(platform_url: str) -> ConcurrentStableDict[str, int]:
    """从平台库取「`业务码:动作码` → 权限码主键」映射。

    Args:
        platform_url: platform 服务平台库连接串。

    Returns:
        ConcurrentStableDict[str, int]: 权限码映射。
    """
    engine = create_async_engine(platform_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            businesses = (await session.execute(select(SysBusiness))).scalars().all()
            business_by_id: ConcurrentStableDict[int, str] = ConcurrentStableDict()
            for business in businesses:
                business_by_id.set(business.id, business.code)
            actions = (await session.execute(select(SysAction))).scalars().all()
            action_by_id: ConcurrentStableDict[int, str] = ConcurrentStableDict()
            for action in actions:
                action_by_id.set(action.id, action.code)
            permissions = (await session.execute(select(SysPermission))).scalars().all()
            result: ConcurrentStableDict[str, int] = ConcurrentStableDict()
            for permission in permissions:
                business_code = business_by_id.get(permission.business_id)
                action_code = action_by_id.get(permission.action_id)
                if business_code and action_code:
                    result.set(f"{business_code}:{action_code}", permission.id)
            return result
    finally:
        await engine.dispose()


async def _ensure_role(session: AsyncSession, *, code: str, name: str, role_type: str, outcome: SeedOutcome) -> int:
    """取或建内置角色（按 `code` 判存）。

    Args:
        session: 租户库会话。
        code: 角色码。
        name: 角色名。
        role_type: 角色类型（内置判定依据）。
        outcome: 结果累计。

    Returns:
        int: 角色主键。
    """
    existing = (
        await session.execute(select(SysRole).where(SysRole.code == code, SysRole.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if existing is not None:
        outcome.roles_skipped += 1
        return existing.id
    role = SysRole(code=code, name=name, status="enabled", role_type=role_type)
    session.add(role)
    await session.flush()
    outcome.roles_created += 1
    return role.id


async def _ensure_grant(session: AsyncSession, *, role_id: int, target_id: int, outcome: SeedOutcome) -> None:
    """取或建授权条目（按 `(role_id, perm_type, target_id, source_menu_id)` 判存）。

    Args:
        session: 租户库会话。
        role_id: 角色主键。
        target_id: 动作主键。
        outcome: 结果累计。
    """
    existing = (
        await session.execute(
            select(SysRolePermission).where(
                SysRolePermission.role_id == role_id,
                SysRolePermission.perm_type == PERM_TYPE_PERMISSION,
                SysRolePermission.target_id == target_id,
                SysRolePermission.source_menu_id == NO_SOURCE_MENU_ID,
                SysRolePermission.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        outcome.grants_skipped += 1
        return
    session.add(
        SysRolePermission(
            role_id=role_id,
            perm_type=PERM_TYPE_PERMISSION,
            target_id=target_id,
            source_menu_id=NO_SOURCE_MENU_ID,
        )
    )
    await session.flush()
    outcome.grants_created += 1


async def _resolve_user_id(session: AsyncSession, account: str) -> int | None:
    """按账号（`sys_user.username`）或用户主键解析用户主键。

    Args:
        session: 租户库会话。
        account: 待解析账号（纯数字按用户主键解析）。

    Returns:
        int | None: 用户主键；未找到返回 None。
    """
    condition = SysUser.id == int(account) if account.isdigit() else SysUser.username == account
    return (
        await session.execute(select(SysUser.id).where(condition, SysUser.deleted_at.is_(None)))
    ).scalar_one_or_none()


async def _ensure_assignment(session: AsyncSession, *, role_id: int, account: str, outcome: SeedOutcome) -> None:
    """把 bootstrap 账号绑定到内置系统管理员角色（按 `(role_id, user_id)` 判存）。

    绑定后主体命中**豁免层级**（`role_type=system`），使本地开发对全部 `require_permission`
    端点开箱可用（无需逐码授权；权限码级判定由权限引擎专项用例覆盖）。

    绑定前做**三权互斥前置校验**（需求 07-6）：账号若已持另一类内置管理员角色
    （`role_type ∈ SEPARATION_ROLE_TYPES` 且与目标角色类型不同），拒绝绑定并记入
    `assign_conflicts`——与 `SeparationGuard`（服务层 30010）同一口径，种子不绕过护栏。

    Args:
        session: 租户库会话。
        role_id: 内置系统管理员角色主键。
        account: 待绑定账号（`sys_user.username`）或用户主键。
        outcome: 结果累计。
    """
    user_id = await _resolve_user_id(session, account)
    if user_id is None:
        outcome.assign_unresolved.add(account)
        return
    target_type = (await session.execute(select(SysRole.role_type).where(SysRole.id == role_id))).scalar_one_or_none()
    held_types = (
        await session.execute(
            select(SysRole.role_type)
            .join(SysUserRole, SysUserRole.role_id == SysRole.id)
            .where(
                SysUserRole.user_id == user_id,
                SysUserRole.deleted_at.is_(None),
                SysRole.deleted_at.is_(None),
                SysRole.role_type.in_(SEPARATION_ROLE_TYPES),
            )
        )
    ).scalars()
    if any(held != target_type for held in held_types):
        outcome.assign_conflicts.add(account)
        return
    existing = (
        await session.execute(
            select(SysUserRole).where(
                SysUserRole.role_id == role_id,
                SysUserRole.user_id == user_id,
                SysUserRole.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        outcome.assignments_skipped += 1
        return
    session.add(SysUserRole(role_id=role_id, user_id=user_id))
    await session.flush()
    outcome.assignments_created += 1


def _safe_url(url: str) -> str:
    """隐去连接串中的口令。

    Args:
        url: 连接串。

    Returns:
        str: 脱敏连接串。
    """
    if "@" not in url:
        return url
    head, _, tail = url.rpartition("@")
    prefix = head.rpartition("://")[0]
    return f"{prefix}://***@{tail}" if prefix else f"***@{tail}"


def _resolve_platform_url(url: str, *, service: str) -> str:
    """解析平台服务库连接串（参数 > `BMS_MIGRATION_URL` > 按库键 `platform_{service}`）。

    Args:
        url: 命令行传入的 URL（空串表示未指定）。
        service: 目标服务标识。

    Returns:
        str: 平台服务库连接串。
    """
    if url:
        return url
    env_url = os.environ.get("BMS_MIGRATION_URL", "")
    if env_url:
        return env_url
    # 运维通道：允许跨服务库键（种子脚本按归属服务写库，不以运行服务为限）
    return EngineFactory(get_settings(), allow_cross_service=True).resolved_url(build_platform_db_key(service))


def build_parser() -> argparse.ArgumentParser:
    """构造命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="内置角色与授权种子（幂等）")
    parser.add_argument("--tenant", default="demo", help="租户编码（缺省 demo）")
    parser.add_argument("--service", default=PLATFORM_SERVICE_KEY, help="目标服务标识（缺省 platform）")
    parser.add_argument("--tenant-url", default="", help="显式租户库连接串（覆盖模板解析）")
    parser.add_argument("--platform-url", default="", help="显式服务库连接串（覆盖模板解析）")
    parser.add_argument(
        "--assign-user",
        default="",
        help=f"把该账号或用户主键绑到内置系统管理员；缺省不绑定（{DEFAULT_ASSIGN_ACCOUNT}）",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅预演（不写库）")
    return parser


async def main(args: argparse.Namespace) -> None:
    """脚本入口：解析两库 URL 并执行播种。

    Args:
        args: 命令行参数。
    """
    basis = await resolve_tenant_basis(args.tenant)
    tenant_url = resolve_tenant_url(basis, args.tenant_url, args.service)
    platform_url = _resolve_platform_url(args.platform_url, service=args.service)
    print(f"[seed_rbac] 租户库（角色域）：{_safe_url(tenant_url)}")
    print(f"[seed_rbac] 服务库（权限码）：{_safe_url(platform_url)}")
    outcome = await seed_rbac(
        tenant_url=tenant_url,
        platform_url=platform_url,
        assign_user=args.assign_user,
        dry_run=args.dry_run,
    )
    mode = "预演" if args.dry_run else "落库"
    print(
        f"[seed_rbac] {mode}完成：角色 新增 {outcome.roles_created} / 跳过 {outcome.roles_skipped}；"
        f"授权 新增 {outcome.grants_created} / 跳过 {outcome.grants_skipped}"
    )
    if args.assign_user:
        print(
            f"[seed_rbac] 绑定内置系统管理员：{args.assign_user} 新增 {outcome.assignments_created} / "
            f"跳过 {outcome.assignments_skipped}"
        )
    if outcome.assign_unresolved:
        print(f"[seed_rbac] 待绑定但库中未找到（先执行建号脚本）：{', '.join(outcome.assign_unresolved)}")
    if outcome.assign_conflicts:
        print(f"[seed_rbac] 三权互斥、已拒绝绑定的账号（已持另一类内置管理员）：{', '.join(outcome.assign_conflicts)}")
    if outcome.missing_codes:
        print(f"[seed_rbac] 平台库未登记、已跳过的权限码：{', '.join(outcome.missing_codes)}")
