"""平台服务 services 层：角色服务（角色 CRUD / 内置角色保护 / 删除保护）。

口径（需求 07-3、《概要设计 · 角色管理》）：

- 角色域 5 表落 **platform 服务租户库**（`bms_platform_{code}`），与字典 / 系统参数 / 用户扩展同库；
  授权引用的菜单 / 表单 / 动作元数据在 **platform 服务平台库**（同服务、不同库）→ 校验经平台侧元数据完成；
- 角色码租户内唯一（`(code, deleted_at)`），**可修改**（格式受 `role.code_pattern` 约束；改码后展示随之更新）；
- 内置角色按 **`role_type`**（`custom` / `system` / `security` / `audit`，非 `custom` 即内置）判定：
  **禁删、禁停用、禁改类型**（角色码与名称可改）；
- 删除前校验**用户分配**（`sys_user_role`，同库）；岗位 / 部门分配归 mdm 组织域
  （经只读契约核验，mdm 未就绪期间按降级跳过）；
- 三权互斥真实校验归 `03_02`（本任务仅预留错误码 `30048`）。
"""

from __future__ import annotations

import re

from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import (
    ConcurrentConflictError,
    ParamError,
    RoleAssignedError,
    RoleCodeExistsError,
    RoleNotFoundError,
    RoleProtectedError,
)
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.models.role import ROLE_TYPE_CUSTOM, SysRole
from bms_platform.repositories.role import RoleRepository, UserRoleRepository

ROLE_STATUSES: tuple[str, ...] = ("enabled", "disabled")
"""角色状态取值。"""

ROLE_CODE_PATTERN_KEY = "role.code_pattern"
"""角色码格式的系统参数键。"""

DEFAULT_ROLE_CODE_PATTERN = r"^[a-z][a-z0-9_-]{1,31}$"
"""角色码格式缺省值（小写字母开头，长度 2~32）。"""


async def resolve_role_code_pattern(config: BaseConfigSource) -> str:
    """取角色码格式（`role.code_pattern`；缺省 `DEFAULT_ROLE_CODE_PATTERN`）。

    Args:
        config: 系统参数取数（按租户）。

    Returns:
        str: 正则表达式字符串。
    """
    values = await config.get_many(ConcurrentStableList((ROLE_CODE_PATTERN_KEY,)))
    raw = values.get(ROLE_CODE_PATTERN_KEY)
    if isinstance(raw, str) and raw.strip():
        return raw
    return DEFAULT_ROLE_CODE_PATTERN


class RoleService(BaseFrameworkObject):
    """角色服务：角色增删改查（含内置角色保护与删除保护）。"""

    def __init__(
        self,
        roles: RoleRepository,
        user_roles: UserRoleRepository,
        uow: UnitOfWork,
        config: BaseConfigSource,
    ) -> None:
        """初始化。

        Args:
            roles: 角色仓储。
            user_roles: 角色 × 用户分配仓储（删除保护计数）。
            uow: 工作单元（写事务边界；platform 服务租户库会话）。
            config: 系统参数取数（读 `role.*`）。
        """
        self._roles = roles
        self._user_roles = user_roles
        self._uow = uow
        self._config = config

    async def list_roles(
        self,
        query: BasePageQuery,
        *,
        keyword: str | None = None,
        status: str | None = None,
    ) -> tuple[ConcurrentStableList[SysRole], int]:
        """分页查询角色（关键字 / 状态筛选）。

        Args:
            query: 页码分页请求。
            keyword: 关键字（角色码 / 名称）。
            status: 状态。

        Returns:
            tuple[ConcurrentStableList[SysRole], int]: 当前页记录与总条数。
        """
        rows = await self._roles.list_filtered(query, keyword=keyword, status=status)
        total = await self._roles.count_filtered(keyword=keyword, status=status)
        return rows, total

    async def detail(self, role_id: int) -> SysRole:
        """取角色详情。

        Args:
            role_id: 角色主键。

        Returns:
            SysRole: 角色记录。

        Raises:
            RoleNotFoundError: 角色不存在。
        """
        return await self._require(role_id)

    async def create_role(self, *, code: str, name: str, status: str | None = None) -> SysRole:
        """新建角色（校验格式与唯一性；新角色类型恒为自定义）。

        Args:
            code: 角色码。
            name: 角色名称。
            status: 状态（缺省 `enabled`）。

        Returns:
            SysRole: 新建角色。

        Raises:
            ParamError: 角色码格式非法或状态非法。
            RoleCodeExistsError: 角色码已存在。
        """
        async with self._uow.begin():
            normalized = await self._normalize_code(code)
            resolved_status = status or ROLE_STATUSES[0]
            if resolved_status not in ROLE_STATUSES:
                raise ParamError("角色状态非法")
            if await self._roles.get_by_code(normalized) is not None:
                raise RoleCodeExistsError()
            return await self._roles.create(
                code=normalized,
                name=name.strip(),
                status=resolved_status,
                role_type=ROLE_TYPE_CUSTOM,
            )

    async def update_role(
        self,
        role_id: int,
        *,
        code: str | None = None,
        name: str | None = None,
        status: str | None = None,
        version: int,
    ) -> SysRole:
        """修改角色（角色码 / 名称 / 状态；乐观锁与内置角色保护）。

        Args:
            role_id: 角色主键。
            code: 角色码（None 表示不改；需格式合法且租户内唯一）。
            name: 角色名称（None 表示不改）。
            status: 状态（None 表示不改）。
            version: 客户端版本（乐观锁比对）。

        Returns:
            SysRole: 更新后的角色。

        Raises:
            RoleNotFoundError: 角色不存在。
            RoleProtectedError: 内置角色不可停用。
            ParamError: 角色码格式非法或状态非法。
            RoleCodeExistsError: 角色码已被其他角色占用。
            ConcurrentConflictError: 乐观锁冲突。
        """
        async with self._uow.begin():
            role = await self._require(role_id)
            if version != role.version:
                raise ConcurrentConflictError("角色已被他人修改，请刷新后重试")
            if status is not None:
                if status not in ROLE_STATUSES:
                    raise ParamError("角色状态非法")
                if status != role.status and role.role_type != ROLE_TYPE_CUSTOM:
                    raise RoleProtectedError("内置角色不可停用 / 启用")
                role.status = status
            if code is not None:
                normalized = await self._normalize_code(code)
                if normalized != role.code:
                    existing = await self._roles.get_by_code(normalized)
                    if existing is not None and existing.id != role.id:
                        raise RoleCodeExistsError()
                    role.code = normalized
            if name is not None:
                role.name = name.strip()
            await self._roles.flush()
        return role

    async def delete_role(self, role_id: int) -> None:
        """删除角色（内置保护 + 用户分配保护）。

        Args:
            role_id: 角色主键。

        Raises:
            RoleNotFoundError: 角色不存在。
            RoleProtectedError: 内置角色不可删除。
            RoleAssignedError: 角色仍存在用户分配。
        """
        async with self._uow.begin():
            role = await self._require(role_id)
            if role.role_type != ROLE_TYPE_CUSTOM:
                raise RoleProtectedError("内置角色不可删除")
            if await self._user_roles.count_by_role(role_id) > 0:
                raise RoleAssignedError("角色仍存在用户分配，禁止删除")
            await self._roles.soft_delete(role_id)

    async def subject_counts(self, role_ids: ConcurrentStableList[int]) -> ConcurrentStableDict[int, int]:
        """批量取各角色已分配用户数（列表「主体数」列）。

        Args:
            role_ids: 角色主键清单。

        Returns:
            ConcurrentStableDict[int, int]: 角色主键 → 已分配用户数。
        """
        counts: ConcurrentStableDict[int, int] = ConcurrentStableDict()
        for role_id in role_ids:
            counts.set(role_id, await self._user_roles.count_by_role(role_id))
        return counts

    async def _normalize_code(self, code: str) -> str:
        """归一化并校验角色码（格式受 `role.code_pattern` 约束）。

        Args:
            code: 角色码（未归一）。

        Returns:
            str: 归一化后的角色码。

        Raises:
            ParamError: 角色码格式非法。
        """
        normalized = code.strip()
        pattern = await resolve_role_code_pattern(self._config)
        if not re.fullmatch(pattern, normalized):
            raise ParamError("角色码格式非法（小写字母开头，2~32 位字母 / 数字 / 下划线 / 连字符）")
        return normalized

    async def _require(self, role_id: int) -> SysRole:
        """取角色记录（不存在抛 `RoleNotFoundError`）。

        Args:
            role_id: 角色主键。

        Returns:
            SysRole: 角色记录。

        Raises:
            RoleNotFoundError: 角色不存在。
        """
        role = await self._roles.get(role_id)
        if role is None:
            raise RoleNotFoundError()
        return role
