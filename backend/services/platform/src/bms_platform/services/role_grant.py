"""平台服务 services 层：角色授权服务（菜单 / 表单 / 权限码 / 字段 / 数据权限的授予与提交）。

口径（需求 07-3、《概要设计 · 角色管理》、《组件设计 · 权限配置》）：

- 授权引用**平台元数据**（`sys_menu` / `sys_form` / `sys_permission` / `sys_field`，platform 平台库）；
  角色与授权表在 **platform 租户库**（`bms_platform_{code}`）——同服务、跨库，校验在同服务内完成；
- **数据权限**按基础数据字典结构化（数据源标识 `data_source_key` 经**统一数据源登记**校验字段白名单与存在性，
  无需跨服务读出口）；
  四类策略（选择 / 区域 / 匹配 / 扩展）**只选不编**，`config` 结构按《数据库设计 · `sys_data_scope`》：
  `select` 行 `item_code`（兼容前端历史键 `itemCode`）且**勾选数不超** `[data_scope].options.max_in_values`
  （超阈即拒并引导改用区域 / 匹配 / 扩展），`region` 行起止须齐全且 `start <= end`，
  `match.field` 须属该字典类型白名单（内置三字段 + 已启用扩展属性），
  `match.pattern` 仅允许 `*` `?` 与中英文 / 数字 / 下划线，`extension.key` 须在扩展权限注册表内；
- **全量覆盖提交**（先删后插、单事务）；成功**一次**权限版本 +1（`bms:{租户}:permission:version`）供权限计算失效；
- 菜单 ↔ 表单**多对多**关联（`sys_menu_form`）落 `03_01` 返工；本轮实现**存在性校验**与**来源须在本次授权内**校验，
  「来源菜单与其表单匹配」校验待返工后接入（已登记）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import select

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.config import Settings, get_settings
from bms_core.core.exceptions import (
    ParamError,
    RoleFieldMismatchError,
    RoleNotFoundError,
    RoleScopeValueInvalidError,
    RoleTargetInvalidError,
)
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.datasource.registry import DataSourceRegistry
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.models.platform.menu import SysField, SysForm, SysMenu, SysPermission
from bms_core.models.platform.role import (
    NO_SOURCE_MENU_ID,
    PERM_TYPE_FORM,
    PERM_TYPE_MENU,
    PERM_TYPE_PERMISSION,
    PERM_TYPES,
    POLICY_TYPE_EXTENSION,
    POLICY_TYPE_MATCH,
    POLICY_TYPE_REGION,
    POLICY_TYPE_SELECT,
    POLICY_TYPES,
    SysDataScope,
    SysRole,
    SysRoleField,
    SysRolePermission,
)
from bms_core.permission.version import permission_version_key
from bms_core.scope.extensions import registered_data_scope_extensions
from bms_core.scope.limits import data_scope_max_in_values
from bms_platform.repositories.role import (
    DataScopeRepository,
    RoleFieldRepository,
    RolePermissionRepository,
    RoleRepository,
)
from bms_platform.services.separation import SeparationGuard

BUILTIN_MATCH_FIELDS: ConcurrentStableList[str] = ConcurrentStableList(("code", "name", "remark"))
"""数据匹配内置字段白名单（字典数据本身的字段）。"""

MATCH_PATTERN = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fa5*?]+$")
"""数据匹配通配符值允许集（`*` `?` 与中英文 / 数字 / 下划线）。"""


@dataclass(frozen=True)
class PermissionGrantEntry(BaseValueObject):
    """一条授权条目（菜单 / 表单 / 权限码）。"""

    perm_type: str
    target_id: int
    source_menu_id: int = NO_SOURCE_MENU_ID


@dataclass(frozen=True)
class FieldGrantEntry(BaseValueObject):
    """一条字段权限条目（只落收窄项）。"""

    form_id: int
    field_id: int
    visible: bool = True
    editable: bool = True
    source_menu_id: int = NO_SOURCE_MENU_ID


@dataclass(frozen=True)
class DataScopeGrantEntry(BaseValueObject):
    """一条数据权限条目（角色 × 字典 × 策略 → 结构化配置）。"""

    data_source_key: str
    policy_type: str
    config: ConcurrentStableList[ConcurrentStableDict[str, object]]


class MenuMetadataChecker(BaseFrameworkObject):
    """平台库元数据校验器（菜单 / 表单 / 动作 / 字段的存在性与归属）。"""

    def __init__(self, session: DbSession) -> None:
        """初始化。

        Args:
            session: platform 平台库只读会话。
        """
        self._session = session

    async def existing_ids(self, model: type[Any], ids: ConcurrentStableSet[int]) -> ConcurrentStableSet[int]:
        """取给定主键中**真实存在**的部分。

        Args:
            model: 元数据模型（`SysMenu` / `SysForm` / `SysPermission` / `SysField`）。
            ids: 待校验主键集合。

        Returns:
            ConcurrentStableSet[int]: 存在的主键集合。
        """
        if not ids:
            return ConcurrentStableSet()
        statement = select(model.id).where(model.id.in_(tuple(ids)))
        return ConcurrentStableSet((await self._session.execute(statement)).scalars().all())

    async def form_field_pairs(self, form_ids: ConcurrentStableSet[int]) -> ConcurrentStableSet[tuple[int, int]]:
        """取表单 → 字段的归属对（用于字段权限校验）。

        Args:
            form_ids: 表单主键集合。

        Returns:
            ConcurrentStableSet[tuple[int, int]]: `(form_id, field_id)` 集合。
        """
        if not form_ids:
            return ConcurrentStableSet()
        statement = select(SysField.form_id, SysField.id).where(SysField.form_id.in_(tuple(form_ids)))
        rows = (await self._session.execute(statement)).all()
        return ConcurrentStableSet((int(row[0]), int(row[1])) for row in rows)


class RoleGrantService(BaseFrameworkObject):
    """角色授权服务：授权读取与全量覆盖提交（含目标校验、来源校验与版本失效）。"""

    def __init__(
        self,
        roles: RoleRepository,
        permissions: RolePermissionRepository,
        fields: RoleFieldRepository,
        data_scopes: DataScopeRepository,
        metadata: MenuMetadataChecker,
        uow: UnitOfWork,
        cache: CacheRegion,
        guard: SeparationGuard | None = None,
        settings: Settings | None = None,
    ) -> None:
        """初始化。

        Args:
            roles: 角色仓储。
            permissions: 授权仓储（`sys_role_permission`）。
            fields: 字段权限仓储（`sys_role_field`）。
            data_scopes: 数据权限仓储（`sys_data_scope`）。
            metadata: 平台库元数据校验器。
            uow: 工作单元（platform 租户库写事务）。
            cache: 缓存能力域（权限版本 +1）。
            guard: 三权分立校验器（`03_02`；None 时不做 `role` 归属与防自锁校验）。
            settings: 应用配置（读 `[data_scope].options.max_in_values`；None 取进程单例）。
        """
        self._roles = roles
        self._permissions = permissions
        self._fields = fields
        self._data_scopes = data_scopes
        self._metadata = metadata
        self._uow = uow
        self._cache = cache
        self._guard = guard
        self._settings = settings if settings is not None else get_settings()

    async def list_permission_entries(self, role_id: int) -> ConcurrentStableList[SysRolePermission]:
        """取角色授权条目（菜单 / 表单 / 权限码）。

        Args:
            role_id: 角色主键。

        Returns:
            ConcurrentStableList[SysRolePermission]: 授权条目。
        """
        await self._require_role(role_id)
        return await self._permissions.list_by_role(role_id)

    async def replace_permissions(
        self,
        role_id: int,
        entries: ConcurrentStableList[PermissionGrantEntry],
        *,
        tenant_id: str | None,
    ) -> ConcurrentStableList[SysRolePermission]:
        """全量覆盖角色授权（先删后插、单事务；成功一次版本 +1）。

        Args:
            role_id: 角色主键。
            entries: 授权条目清单。
            tenant_id: 租户标识（权限版本键作用域）。

        Returns:
            ConcurrentStableList[SysRolePermission]: 重建后的授权条目。

        Raises:
            RoleNotFoundError: 角色不存在。
            ParamError: 授权类型非法或条目重复。
            RoleTargetInvalidError: 授权目标不存在，或来源菜单未在本次授权内。
            RoleSeparationConflictError: `role` 业务授予非安全管理员角色，或修改自身所属角色（30048）。
        """
        async with self._uow.begin():
            role = await self._require_role(role_id)
            normalized = self._validate_perm_entries(entries)
            await self._ensure_targets_exist(normalized)
            if self._guard is not None:
                await self._guard.ensure_grant_scope(role=role, permission_ids=self._permission_targets(normalized))
            await self._permissions.delete_by_role(role_id)
            created: ConcurrentStableList[SysRolePermission] = ConcurrentStableList()
            for entry in normalized:
                created.add(
                    await self._permissions.create(
                        role_id=role_id,
                        perm_type=entry.perm_type,
                        target_id=entry.target_id,
                        source_menu_id=entry.source_menu_id,
                    )
                )
        await self._bump_version(tenant_id)
        return created

    async def list_field_entries(self, role_id: int) -> ConcurrentStableList[SysRoleField]:
        """取角色字段权限条目（仅收窄项）。

        Args:
            role_id: 角色主键。

        Returns:
            ConcurrentStableList[SysRoleField]: 字段权限条目。
        """
        await self._require_role(role_id)
        return await self._fields.list_by_role(role_id)

    async def replace_fields(
        self,
        role_id: int,
        entries: ConcurrentStableList[FieldGrantEntry],
        *,
        tenant_id: str | None,
    ) -> ConcurrentStableList[SysRoleField]:
        """全量覆盖角色字段权限（先删后插、单事务；成功一次版本 +1）。

        Args:
            role_id: 角色主键。
            entries: 字段权限条目清单。
            tenant_id: 租户标识（权限版本键作用域）。

        Returns:
            ConcurrentStableList[SysRoleField]: 重建后的字段权限条目。

        Raises:
            RoleNotFoundError: 角色不存在。
            ParamError: 条目非法（不可见即不可编辑、重复）。
            RoleFieldMismatchError: 字段不属于该表单。
            RoleSeparationConflictError: 修改自身所属角色的授权集合（防自锁，30048）。
        """
        async with self._uow.begin():
            role = await self._require_role(role_id)
            self._validate_field_entries(entries)
            await self._ensure_fields_exist(entries)
            if self._guard is not None:
                await self._guard.ensure_not_self_lock(role=role)
            await self._fields.delete_by_role(role_id)
            created: ConcurrentStableList[SysRoleField] = ConcurrentStableList()
            for entry in entries:
                created.add(
                    await self._fields.create(
                        role_id=role_id,
                        form_id=entry.form_id,
                        field_id=entry.field_id,
                        visible=entry.visible,
                        editable=entry.editable,
                        source_menu_id=entry.source_menu_id,
                    )
                )
        await self._bump_version(tenant_id)
        return created

    async def list_data_scope_entries(self, role_id: int) -> ConcurrentStableList[SysDataScope]:
        """取角色数据权限条目（按字典 × 策略）。

        Args:
            role_id: 角色主键。

        Returns:
            ConcurrentStableList[SysDataScope]: 数据权限条目。
        """
        await self._require_role(role_id)
        return await self._data_scopes.list_by_role(role_id)

    async def replace_data_scopes(
        self,
        role_id: int,
        entries: ConcurrentStableList[DataScopeGrantEntry],
        *,
        tenant_id: str | None,
    ) -> ConcurrentStableList[SysDataScope]:
        """全量覆盖角色数据权限（先删后插、单事务；成功一次版本 +1）。

        Args:
            role_id: 角色主键。
            entries: 数据权限条目清单。
            tenant_id: 租户标识（权限版本键作用域）。

        Returns:
            ConcurrentStableList[SysDataScope]: 重建后的数据权限条目。

        Raises:
            RoleNotFoundError: 角色不存在。
            RoleScopeValueInvalidError: 策略 / 匹配值 / 扩展权限非法。
            RoleSeparationConflictError: 修改自身所属角色的授权集合（防自锁，30048）。
        """
        async with self._uow.begin():
            role = await self._require_role(role_id)
            await self._validate_data_scopes(entries)
            if self._guard is not None:
                await self._guard.ensure_not_self_lock(role=role)
            await self._data_scopes.delete_by_role(role_id)
            created: ConcurrentStableList[SysDataScope] = ConcurrentStableList()
            for entry in entries:
                created.add(
                    await self._data_scopes.create(
                        role_id=role_id,
                        data_source_key=entry.data_source_key,
                        policy_type=entry.policy_type,
                        config=[item for item in entry.config],
                    )
                )
        await self._bump_version(tenant_id)
        return created

    def _validate_perm_entries(
        self, entries: ConcurrentStableList[PermissionGrantEntry]
    ) -> ConcurrentStableList[PermissionGrantEntry]:
        """校验授权条目：类型合法、无重复、来源菜单须在同一提交内或已存在。

        Args:
            entries: 原始条目清单。

        Returns:
            ConcurrentStableList[PermissionGrantEntry]: 规范化条目。

        Raises:
            ParamError: 授权类型非法或条目重复。
            RoleTargetInvalidError: 来源菜单未在本次授权内。
        """
        seen: ConcurrentStableSet[tuple[str, int, int]] = ConcurrentStableSet()
        menu_ids: ConcurrentStableSet[int] = ConcurrentStableSet()
        for entry in entries:
            if entry.perm_type not in PERM_TYPES:
                raise ParamError("授权类型非法")
            if entry.perm_type == PERM_TYPE_MENU:
                menu_ids.add(entry.target_id)
        for entry in entries:
            if (
                entry.perm_type != PERM_TYPE_MENU
                and entry.source_menu_id != NO_SOURCE_MENU_ID
                and entry.source_menu_id not in menu_ids
            ):
                raise RoleTargetInvalidError("来源菜单未在本次授权内（须同时授予该菜单入口）")
            key = (entry.perm_type, entry.target_id, entry.source_menu_id)
            if key in seen:
                raise ParamError("授权条目重复")
            seen.add(key)
        normalized: ConcurrentStableList[PermissionGrantEntry] = ConcurrentStableList()
        normalized.update(entries)
        return normalized

    async def _ensure_targets_exist(self, entries: ConcurrentStableList[PermissionGrantEntry]) -> None:
        """校验授权目标在平台元数据中真实存在。

        Args:
            entries: 规范化后的授权条目。

        Raises:
            RoleTargetInvalidError: 存在不存在的授权目标。
        """
        grouped: ConcurrentStableDict[str, ConcurrentStableSet[int]] = ConcurrentStableDict()
        grouped.set(PERM_TYPE_MENU, ConcurrentStableSet())
        grouped.set(PERM_TYPE_FORM, ConcurrentStableSet())
        grouped.set(PERM_TYPE_PERMISSION, ConcurrentStableSet())
        for entry in entries:
            existing = grouped.get(entry.perm_type)
            if existing is None:
                continue
            existing.add(entry.target_id)
        models: ConcurrentStableDict[str, Any] = ConcurrentStableDict()
        models.set(PERM_TYPE_MENU, SysMenu)
        models.set(PERM_TYPE_FORM, SysForm)
        models.set(PERM_TYPE_PERMISSION, SysPermission)
        for perm_type in PERM_TYPES:
            ids = grouped.get(perm_type)
            if not ids:
                continue
            found = await self._metadata.existing_ids(cast("type[Any]", models.get(perm_type)), ids)
            missing: ConcurrentStableList[int] = ConcurrentStableList()
            for target in ids:
                if target not in found:
                    missing.add(target)
            if missing:
                raise RoleTargetInvalidError(f"授权目标不存在（{perm_type}）：{tuple(missing)}")

    def _validate_field_entries(self, entries: ConcurrentStableList[FieldGrantEntry]) -> None:
        """校验字段权限条目：不可见即不可编辑、无重复。

        Args:
            entries: 字段权限条目。

        Raises:
            ParamError: 条目非法。
        """
        seen: ConcurrentStableSet[tuple[int, int, int]] = ConcurrentStableSet()
        for entry in entries:
            if not entry.visible and entry.editable:
                raise ParamError("字段不可见时不可编辑")
            key = (entry.form_id, entry.field_id, entry.source_menu_id)
            if key in seen:
                raise ParamError("字段权限条目重复")
            seen.add(key)

    async def _ensure_fields_exist(self, entries: ConcurrentStableList[FieldGrantEntry]) -> None:
        """校验字段属于其声明的表单。

        Args:
            entries: 字段权限条目。

        Raises:
            RoleFieldMismatchError: 字段不属于该表单。
        """
        form_ids: ConcurrentStableSet[int] = ConcurrentStableSet()
        for entry in entries:
            form_ids.add(entry.form_id)
        pairs = await self._metadata.form_field_pairs(form_ids)
        for entry in entries:
            if (entry.form_id, entry.field_id) not in pairs:
                raise RoleFieldMismatchError(f"字段不属于该表单：form={entry.form_id} field={entry.field_id}")

    async def _validate_data_scopes(self, entries: ConcurrentStableList[DataScopeGrantEntry]) -> None:
        """校验数据权限条目：字典存在、策略合法、各策略 `config` 结构、扩展权限已注册。

        Args:
            entries: 数据权限条目。

        Raises:
            RoleScopeValueInvalidError: 策略 / `config` 结构 / 匹配值 / 扩展权限非法（30047）。
        """
        registered_keys: ConcurrentStableSet[str] = ConcurrentStableSet()
        for extension in registered_data_scope_extensions():
            registered_keys.add(extension.key)
        max_select_items = data_scope_max_in_values(self._settings)
        seen: ConcurrentStableSet[tuple[str, str]] = ConcurrentStableSet()
        for entry in entries:
            if entry.policy_type not in POLICY_TYPES:
                raise RoleScopeValueInvalidError(f"数据权限策略非法：{entry.policy_type}")
            if not self._data_source_key_exists(entry.data_source_key):
                raise RoleScopeValueInvalidError(f"字典标识不存在：{entry.data_source_key}")
            key = (entry.data_source_key, entry.policy_type)
            if key in seen:
                raise RoleScopeValueInvalidError("同一字典同一策略只允许一条")
            seen.add(key)
            if entry.policy_type == POLICY_TYPE_SELECT:
                self._validate_select(entry, max_select_items)
            if entry.policy_type == POLICY_TYPE_REGION:
                self._validate_region(entry)
            if entry.policy_type == POLICY_TYPE_MATCH:
                allowed = self._match_field_whitelist(entry.data_source_key)
                for item in entry.config:
                    field = item.get("field")
                    pattern = item.get("pattern")
                    if not isinstance(field, str) or field not in allowed:
                        raise RoleScopeValueInvalidError(f"匹配字段不在白名单内：{field}")
                    if not isinstance(pattern, str) or not MATCH_PATTERN.fullmatch(pattern):
                        raise RoleScopeValueInvalidError(f"匹配值含非法字符：{pattern}")
            if entry.policy_type == POLICY_TYPE_EXTENSION:
                for item in entry.config:
                    extension_key = item.get("key")
                    if not isinstance(extension_key, str) or extension_key not in registered_keys:
                        raise RoleScopeValueInvalidError(f"扩展权限未注册：{extension_key}")

    @staticmethod
    def _validate_select(entry: DataScopeGrantEntry, max_items: int) -> None:
        """校验数据选择条目：`item_code`（兼容 `itemCode`）非空且勾选数不超阈。

        Args:
            entry: 数据选择条目。
            max_items: 勾选值上限（<= 0 表示不限制）。

        Raises:
            RoleScopeValueInvalidError: 缺取值 / 取值非空字符串 / 勾选数超阈（30047）。
        """
        codes: ConcurrentStableSet[str] = ConcurrentStableSet()
        for item in entry.config:
            code = None
            for key in ("item_code", "itemCode"):
                raw = item.get(key)
                if isinstance(raw, str) and raw:
                    code = raw
                    break
            if code is None:
                raise RoleScopeValueInvalidError("数据选择项缺少 item_code（须为非空字符串）")
            codes.add(code)
        if max_items > 0 and len(codes) > max_items:
            raise RoleScopeValueInvalidError(
                f"数据选择勾选 {len(codes)} 个值，超过上限 {max_items}：请改用数据区域 / 数据匹配 / 扩展权限"
            )

    @staticmethod
    def _validate_region(entry: DataScopeGrantEntry) -> None:
        """校验数据区域条目：起止齐全、可比且开始不大于结束。

        Args:
            entry: 数据区域条目。

        Raises:
            RoleScopeValueInvalidError: 缺开始 / 结束值、起止不可比或开始大于结束（30047）。
        """
        for item in entry.config:
            start = item.get("start")
            end = item.get("end")
            if start is None or end is None:
                raise RoleScopeValueInvalidError("数据区域行缺少开始值或结束值")
            try:
                inverted = cast("Any", start) > cast("Any", end)
            except TypeError:
                raise RoleScopeValueInvalidError("数据区域起止值不可比较") from None
            if inverted:
                raise RoleScopeValueInvalidError("数据区域开始值大于结束值")

    def _data_source_key_exists(self, data_source_key: str) -> bool:
        """字典标识是否已登记（启用）。

        Args:
            data_source_key: 字典标识（业务码）。

        Returns:
            bool: 已登记且启用为 True。
        """
        record = DataSourceRegistry().get(data_source_key)
        return record is not None and record.status == "enabled"

    def _match_field_whitelist(self, data_source_key: str) -> ConcurrentStableSet[str]:
        """取某字典的可匹配字段白名单（登记项 `allowlist` + 内置三字段）。

        Args:
            data_source_key: 字典标识（业务码）。

        Returns:
            ConcurrentStableSet[str]: 白名单字段键。

        Raises:
            RoleScopeValueInvalidError: 字典标识不存在。
        """
        record = DataSourceRegistry().get(data_source_key)
        if record is None:
            raise RoleScopeValueInvalidError(f"字典标识不存在：{data_source_key}")
        allowed: ConcurrentStableSet[str] = ConcurrentStableSet(BUILTIN_MATCH_FIELDS)
        allowed.update(record.allowlist)
        return allowed

    @staticmethod
    def _permission_targets(
        entries: ConcurrentStableList[PermissionGrantEntry],
    ) -> ConcurrentStableSet[int]:
        """取授权条目中的权限码目标主键集合（`perm_type='permission'` 条目）。

        Args:
            entries: 规范化授权条目。

        Returns:
            ConcurrentStableSet[int]: 权限码主键集合。
        """
        return ConcurrentStableSet(entry.target_id for entry in entries if entry.perm_type == PERM_TYPE_PERMISSION)

    async def _bump_version(self, tenant_id: str | None) -> None:
        """权限版本 +1（授权变更后一次递增，供权限计算失效）。

        Args:
            tenant_id: 租户标识。
        """
        await self._cache.aincrease(permission_version_key(tenant_id))

    async def _require_role(self, role_id: int) -> SysRole:
        """校验角色存在并返回。

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
