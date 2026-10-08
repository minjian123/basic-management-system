"""内置角色与授权种子脚本（幂等）：三权内置角色 + 在册权限码授权（`02_04`）。

用法：

```bash
cd backend
uv run python -m ops.seed_rbac --tenant demo --dry-run      # 计划预演
uv run python -m ops.seed_rbac --tenant demo                # 落库（幂等）
uv run python -m ops.seed_rbac --tenant demo --tenant-url "sqlite+aiosqlite:///…" --platform-url "…"
```

- **库定位（两库协同）**：角色域（`sys_role` / `sys_role_permission`）在 **platform 服务租户库**；
  动作码（`sys_action` / `sys_business`）在 **platform 服务平台库**——分别解析（租户库复用
  `ops.seed_user` 的「注册库对照表取库名基 → 模板解析」口径，平台库复用 `ops.seed_tenant.resolve_url`）；
- **幂等**：角色按 `(code, deleted_at IS NULL)`、授权按 `(role_id, perm_type, target_id, source_menu_id,
  deleted_at IS NULL)` 判存——不存在插入、存在跳过，重复执行全为「跳过」；
- **授权目标**：权限码 `业务:动作` → `sys_action` 行（`perm_type="action"`、`source_menu_id=0`）；
  平台库未登记的动作码**跳过并上报**（如审计域尚未落地的码）；
- **三权清单（需求 07-6）**：系统管理员持**除 `role:*` 外的全部在册码**（角色域归安全管理员，
  系统 / 审计管理员不得越权授予）；安全管理员持 `role:query/create/update/delete/grant`；
  审计管理员本轮不授权（审计域权限码随审计模块落地）——**安全管理员不属豁免层级**，其可达性
  完全依赖本清单（防 403 自锁的关键一侧）。
"""

import argparse
import asyncio
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.keys import PLATFORM_SERVICE_KEY
from bms_platform.models.menu import SysAction, SysBusiness
from bms_platform.models.role import (
    NO_SOURCE_MENU_ID,
    PERM_TYPE_ACTION,
    ROLE_TYPE_AUDIT,
    ROLE_TYPE_SECURITY,
    ROLE_TYPE_SYSTEM,
    SysRole,
    SysRolePermission,
)
from ops.seed_tenant import resolve_url as resolve_platform_url
from ops.seed_user import resolve_tenant_basis, resolve_tenant_url  # 复用既有租户库解析口径

ROLE_SYSTEM_ADMIN = "system_admin"
"""系统管理员角色码（内置；豁免层级）。"""

ROLE_SECURITY_ADMIN = "security_admin"
"""安全管理员角色码（内置；**不豁免**，可达性由授权清单决定）。"""

ROLE_AUDIT_ADMIN = "audit_admin"
"""审计管理员角色码（内置；审计域权限码随审计模块落地）。"""

SECURITY_ADMIN_CODES: tuple[str, ...] = (
    "role:query",
    "role:create",
    "role:update",
    "role:delete",
    "role:grant",
)
"""安全管理员授权（角色域全部权限码；需求 07-6「`role` 业务仅安全管理员持有」）。"""

SYSTEM_ADMIN_EXCLUDED_CODES = frozenset(SECURITY_ADMIN_CODES)
"""系统管理员**不**持有的码（角色域；防越权授予）。"""

SYSTEM_ADMIN_CODES: tuple[str, ...] = (
    "menu:query",
    "menu:create",
    "menu:update",
    "menu:delete",
    "business:query",
    "action:query",
    "user:query",
    "user:lock",
    "user:unlock",
    "session:query",
    "session:kick",
    "sso:bind",
    "open:manage",
    "idp:manage",
)
"""系统管理员授权（在册权限码去除角色域码）。与 `require_permission` 在册清单同步维护。"""

AUDIT_ADMIN_CODES: tuple[str, ...] = ()
"""审计管理员授权（本轮为空；审计域权限码随审计模块落地）。"""


@dataclass
class SeedOutcome:
    """执行结果（新增 / 跳过计数与缺码清单）。"""

    roles_created: int = 0
    """新增角色数。"""

    roles_skipped: int = 0
    """已存在角色数。"""

    grants_created: int = 0
    """新增授权条目数。"""

    grants_skipped: int = 0
    """已存在授权条目数。"""

    missing_codes: ConcurrentStableList[str] = field(default_factory=lambda: ConcurrentStableList[str]())
    """平台库未登记、被跳过的权限码（需先执行 `ops.seed_menu` 或补齐产品域动作码）。"""


async def seed_rbac(*, tenant_url: str, platform_url: str, dry_run: bool = False) -> SeedOutcome:
    """播种三权内置角色与其授权（幂等）。

    Args:
        tenant_url: platform 服务租户库连接串（角色域）。
        platform_url: platform 服务平台库连接串（业务 / 动作码）。
        dry_run: 仅预演（不写库）。

    Returns:
        SeedOutcome: 执行结果。
    """
    outcome = SeedOutcome()
    action_ids = await _load_action_ids(platform_url)
    plan: ConcurrentStableList[tuple[str, str, str, tuple[str, ...]]] = ConcurrentStableList()
    plan.add((ROLE_SYSTEM_ADMIN, "系统管理员", ROLE_TYPE_SYSTEM, SYSTEM_ADMIN_CODES))
    plan.add((ROLE_SECURITY_ADMIN, "安全管理员", ROLE_TYPE_SECURITY, SECURITY_ADMIN_CODES))
    plan.add((ROLE_AUDIT_ADMIN, "审计管理员", ROLE_TYPE_AUDIT, AUDIT_ADMIN_CODES))
    engine = create_async_engine(tenant_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            for code, name, role_type, codes in plan:
                role_id = await _ensure_role(session, code=code, name=name, role_type=role_type, outcome=outcome)
                for permission in codes:
                    target_id = action_ids.get(permission)
                    if target_id is None:
                        if permission not in outcome.missing_codes:
                            outcome.missing_codes.add(permission)
                        continue
                    await _ensure_grant(session, role_id=role_id, target_id=target_id, outcome=outcome)
            if dry_run:
                await session.rollback()
            else:
                await session.commit()
    finally:
        await engine.dispose()
    return outcome


async def _load_action_ids(platform_url: str) -> ConcurrentStableDict[str, int]:
    """从平台库取「`业务码:动作码` → 动作主键」映射。

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
            by_id: ConcurrentStableDict[int, str] = ConcurrentStableDict()
            for business in businesses:
                by_id.set(business.id, business.code)
            actions = (await session.execute(select(SysAction))).scalars().all()
            result: ConcurrentStableDict[str, int] = ConcurrentStableDict()
            for action in actions:
                business_code = by_id.get(action.business_id)
                if business_code:
                    result.set(f"{business_code}:{action.code}", action.id)
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
                SysRolePermission.perm_type == PERM_TYPE_ACTION,
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
            perm_type=PERM_TYPE_ACTION,
            target_id=target_id,
            source_menu_id=NO_SOURCE_MENU_ID,
        )
    )
    await session.flush()
    outcome.grants_created += 1


async def main(args: argparse.Namespace) -> None:
    """脚本入口：解析两库 URL 并执行播种。

    Args:
        args: 命令行参数。
    """
    basis = await resolve_tenant_basis(args.tenant)
    tenant_url = resolve_tenant_url(basis, args.tenant_url, args.service)
    platform_url = resolve_platform_url(args.platform_url, service=args.service)
    print(f"[seed_rbac] 租户库（角色域）：{_safe_url(tenant_url)}")
    print(f"[seed_rbac] 服务库（动作码）：{_safe_url(platform_url)}")
    outcome = await seed_rbac(tenant_url=tenant_url, platform_url=platform_url, dry_run=args.dry_run)
    mode = "预演" if args.dry_run else "落库"
    print(
        f"[seed_rbac] {mode}完成：角色 新增 {outcome.roles_created} / 跳过 {outcome.roles_skipped}；"
        f"授权 新增 {outcome.grants_created} / 跳过 {outcome.grants_skipped}"
    )
    if outcome.missing_codes:
        print(f"[seed_rbac] 平台库未登记、已跳过的权限码：{', '.join(outcome.missing_codes)}")


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
    parser.add_argument("--dry-run", action="store_true", help="仅预演（不写库）")
    return parser


if __name__ == "__main__":
    asyncio.run(main(build_parser().parse_args()))
