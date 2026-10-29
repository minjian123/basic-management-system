"""平台服务 services 层：三权分立校验（`03_02`，需求 07-6）。

口径（《架构设计 · 权限计算引擎》§8、《概要设计 · 角色管理》§2.2 / §6.2、《概要设计 · 审计合规》）：

- **三类内置管理员互斥**：系统（`system`）/ 安全（`security`）/ 审计（`audit`）管理员按
  `sys_role.role_type` 判定（`SEPARATION_ROLE_TYPES` 单一来源）；同一用户**不得兼任**两类，
  冲突拒绝 `30010`（`UserSeparationConflictError`）；
- **`role` 业务归属**：`role` 业务的权限码（平台库 `sys_permission ⋈ sys_business(code='role')`）
  只允许授予 `role_type=security` 的角色；系统 / 审计管理员不得执行角色域写操作——冲突拒绝 `30048`
  （`RoleSeparationConflictError`）；
- **防自锁**：安全管理员不得修改「自身所属角色」的授权集合，不得通过授权使自身兼任互斥类型角色；
- **前置生效**：全部校验在写事务内、**写入语句之前**执行；拒绝时不产生任何写入、不递增权限版本；
- **审计留痕**：拒绝前经基座 `AuditCapturer.capture()` 产生审计事件（当前 `NullAuditCapturer`
  不落库，真实落库随审计合规模块）。

错误码分工（按路径）：分配路径（写 `sys_user_role`）→ `30010`；角色 / 授权配置路径 → `30048`。
"""

from __future__ import annotations

from bms_core.audit.base import AuditCapturer, FieldChange
from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.context import get_current_user_id
from bms_core.core.exceptions import RoleSeparationConflictError, UserSeparationConflictError
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.models.platform.role import (
    ROLE_TYPE_AUDIT,
    ROLE_TYPE_SECURITY,
    ROLE_TYPE_SYSTEM,
    SEPARATION_ROLE_TYPES,
    SysRole,
)
from bms_platform.domains.permission_meta.public import BusinessRepository, PermissionRepository
from bms_platform.domains.role.dto import RoleSummary
from bms_platform.domains.role.repositories.role import RoleRepository, UserRoleRepository

ROLE_BUSINESS_CODE = "role"
"""`role` 业务码：角色与授权本身（仅安全管理员持有）。"""

_TABLE_USER_ROLE = "sys_user_role"
"""审计表名：角色分配（`30010` 兼任冲突）。"""

_TABLE_ROLE = "sys_role"
"""审计表名：角色（操作人侧越权）。"""

_TABLE_ROLE_PERMISSION = "sys_role_permission"
"""审计表名：角色授权（`role` 归属违规 / 防自锁）。"""


class RoleBusinessPermissions(BaseFrameworkObject):
    """`role` 业务的权限码集合（数据驱动：平台库 `sys_business(code='role')` ⋈ `sys_permission`）。"""

    def __init__(self, session: DbSession) -> None:
        """初始化 `role` 业务权限码读取器。

        Args:
            session: 平台库会话（`sys_business` / `sys_permission` 所在库）。
        """
        self._businesses = BusinessRepository(session)
        self._permissions = PermissionRepository(session)

    async def permission_ids(self) -> ConcurrentStableSet[int]:
        """取 `role` 业务的全部权限码主键（业务码缺失或无权限码时为空集）。

        Returns:
            ConcurrentStableSet[int]: 权限码主键集合。
        """
        for business in await self._businesses.list_all():
            if business.code != ROLE_BUSINESS_CODE:
                continue
            rows = await self._permissions.list_by_business(business.id)
            return ConcurrentStableSet(row.id for row in rows)
        return ConcurrentStableSet()


class SeparationGuard(BaseFrameworkObject):
    """三权分立校验器：互斥（`30010`）、`role` 归属与防自锁（`30048`）、操作人侧护栏（`30048`）。"""

    def __init__(
        self,
        *,
        roles: RoleRepository,
        user_roles: UserRoleRepository,
        business_permissions: RoleBusinessPermissions | None = None,
        audit: AuditCapturer | None = None,
    ) -> None:
        """初始化三权分立校验器。

        Args:
            roles: 角色仓储（租户库）。
            user_roles: 角色分配仓储（租户库）。
            business_permissions: `role` 业务权限码读取器（平台库；None 时不做 `role` 归属校验）。
            audit: 审计捕获器（None 时不产生审计事件，全局事务分支即如此）。
        """
        self._roles = roles
        self._user_roles = user_roles
        self._business_permissions = business_permissions
        self._audit = audit

    async def ensure_role_domain_operator(self) -> None:
        """操作人侧护栏：系统 / 审计管理员不得执行角色域写操作（`30048`）。

        判定：操作人（`current_user_id`）未软删角色类型集合含 `system` 或 `audit`，
        且不含 `security` → 拒绝。无操作人上下文（内部通道 / 平台层）与安全管理员放行。

        Raises:
            RoleSeparationConflictError: 操作人为系统 / 审计管理员（非安全管理员）。
        """
        actor = get_current_user_id()
        if actor is None:
            return
        types = await self._role_types_of(actor)
        if not types & {ROLE_TYPE_SYSTEM, ROLE_TYPE_AUDIT}:
            return
        if ROLE_TYPE_SECURITY in types:
            return
        self._audit_reject(
            table=_TABLE_ROLE,
            model_id=0,
            changes=ConcurrentStableList(
                [
                    FieldChange(
                        field="operator_role_types",
                        old=tuple(sorted(types)),
                        new="role-domain-write",
                    )
                ]
            ),
        )
        raise RoleSeparationConflictError("系统 / 审计管理员不得执行角色域写操作（三权分立）")

    async def ensure_role_grant_exclusive(self, *, role: SysRole, user_ids: ConcurrentStableList[int]) -> None:
        """分配路径（增量）：目标角色 ∪ 用户既有角色不得含两类内置管理员（`30010`）。

        Args:
            role: 本次授予的角色（目标角色自身不计入冲突）。
            user_ids: 本次授予的用户主键清单。

        Raises:
            UserSeparationConflictError: 用户已持另一类内置管理员角色。
        """
        if role.role_type not in SEPARATION_ROLE_TYPES:
            return
        for user_id in user_ids:
            others = await self._separation_types_of(user_id, exclude_role_id=role.id)
            conflicting = others - {role.role_type}
            if not conflicting:
                continue
            self._audit_reject(
                table=_TABLE_USER_ROLE,
                model_id=user_id,
                changes=ConcurrentStableList(
                    [FieldChange(field="role_type", old=tuple(sorted(conflicting)), new=role.role_type)]
                ),
            )
            raise UserSeparationConflictError(f"用户已兼任内置管理员，不得再授予：{user_id}")

    async def ensure_user_roles_exclusive(
        self, *, user_ids: ConcurrentStableList[int], roles: ConcurrentStableList[RoleSummary]
    ) -> None:
        """分配路径（全量替换）：目标角色集合自身不得含两类内置管理员（`30010`）。

        Args:
            user_ids: 本次全量覆盖的用户主键清单（审计定位用）。
            roles: 本次替换后的角色集合。

        Raises:
            UserSeparationConflictError: 目标角色集合含两类及以上内置管理员类型。
        """
        types = ConcurrentStableSet(role.role_type for role in roles if role.role_type in SEPARATION_ROLE_TYPES)
        if len(types) <= 1:
            return
        self._audit_reject(
            table=_TABLE_USER_ROLE,
            model_id=user_ids[0] if user_ids else 0,
            changes=ConcurrentStableList([FieldChange(field="role_type", old=(), new=tuple(sorted(types)))]),
        )
        raise UserSeparationConflictError("同一用户不得兼任两类内置管理员（三权分立）")

    async def ensure_grant_scope(self, *, role: SysRole, permission_ids: ConcurrentStableSet[int]) -> None:
        """授权路径：`role` 业务只归安全管理员 + 不得修改自身所属角色（`30048`）。

        Args:
            role: 被授权的角色。
            permission_ids: 本次授权的权限码主键集合（`perm_type='permission'` 条目）。

        Raises:
            RoleSeparationConflictError: `role` 业务授予非安全管理员角色，或修改自身所属角色。
        """
        await self._ensure_role_business_owner(role=role, permission_ids=permission_ids)
        await self._ensure_not_self_lock(role=role, table=_TABLE_ROLE_PERMISSION)

    async def ensure_not_self_lock(self, *, role: SysRole) -> None:
        """字段 / 数据权限路径：不得修改自身所属角色的授权集合（`30048`）。

        Args:
            role: 被授权的角色。

        Raises:
            RoleSeparationConflictError: 目标角色属操作人自身。
        """
        await self._ensure_not_self_lock(role=role, table=_TABLE_ROLE_PERMISSION)

    async def _ensure_role_business_owner(self, *, role: SysRole, permission_ids: ConcurrentStableSet[int]) -> None:
        """数据侧不变量：`role` 业务权限码只允许授予 `role_type=security` 的角色。

        Args:
            role: 被授权的角色。
            permission_ids: 本次授权的权限码主键集合。

        Raises:
            RoleSeparationConflictError: `role` 业务权限码授予非安全管理员角色。
        """
        if not permission_ids or self._business_permissions is None:
            return
        role_permission_ids = await self._business_permissions.permission_ids()
        violated = permission_ids & role_permission_ids
        if not violated:
            return
        if role.role_type == ROLE_TYPE_SECURITY:
            return
        self._audit_reject(
            table=_TABLE_ROLE_PERMISSION,
            model_id=role.id,
            changes=ConcurrentStableList(
                [
                    FieldChange(field="role_type", old=role.role_type, new=ROLE_TYPE_SECURITY),
                    FieldChange(field="target_id", old="", new=tuple(sorted(violated))),
                ]
            ),
        )
        raise RoleSeparationConflictError("`role` 业务仅限安全管理员角色持有（三权分立）")

    async def _ensure_not_self_lock(self, *, role: SysRole, table: str) -> None:
        """防自锁：操作人不得修改自身所属角色的授权集合。

        Args:
            role: 被授权的角色。
            table: 审计表名。

        Raises:
            RoleSeparationConflictError: 目标角色属操作人自身。
        """
        actor = get_current_user_id()
        if actor is None:
            return
        if role.id not in await self._user_roles.list_role_ids_by_user(actor):
            return
        if role.role_type not in SEPARATION_ROLE_TYPES:
            return
        self._audit_reject(
            table=table,
            model_id=role.id,
            changes=ConcurrentStableList([FieldChange(field="role_id", old=actor, new=role.id)]),
        )
        raise RoleSeparationConflictError("不得修改自身所属角色的授权集合（防自锁）")

    async def _role_types_of(self, user_id: int) -> ConcurrentStableSet[str]:
        """取用户未软删角色的类型集合。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableSet[str]: 角色类型集合（无角色为空集）。
        """
        role_ids = await self._user_roles.list_role_ids_by_user(user_id)
        roles = await self._roles.list_by_ids(ConcurrentStableSet(role_ids))
        return ConcurrentStableSet(role.role_type for role in roles)

    async def _separation_types_of(self, user_id: int, *, exclude_role_id: int) -> ConcurrentStableSet[str]:
        """取用户已持的**三权参与类型**集合（排除指定角色，供增量分配判定）。

        Args:
            user_id: 用户主键。
            exclude_role_id: 需排除的角色主键（本次授予的目标角色）。

        Returns:
            ConcurrentStableSet[str]: 三权参与类型集合（不含 `custom`）。
        """
        role_ids = await self._user_roles.list_role_ids_by_user(user_id)
        kept = ConcurrentStableSet(role_id for role_id in role_ids if role_id != exclude_role_id)
        roles = await self._roles.list_by_ids(kept)
        return ConcurrentStableSet(role.role_type for role in roles if role.role_type in SEPARATION_ROLE_TYPES)

    def _audit_reject(self, *, table: str, model_id: int, changes: ConcurrentStableList[FieldChange]) -> None:
        """拒绝前产生审计事件（无捕获器时跳过；当前 Null 实现不落库）。

        Args:
            table: 表名。
            model_id: 记录主键（未落库的操作可用 `0`）。
            changes: 判定要素。
        """
        if self._audit is None:
            return
        self._audit.capture(
            table=table,
            model_id=model_id,
            changes=changes,
            actor=get_current_user_id(),
        )
