"""平台服务 services 层：角色授权服务（菜单 / 表单 / 权限码 / 字段 / 数据权限的授予与提交）。

口径（需求 07-3、《概要设计 · 角色管理》、《组件设计 · 权限配置》）：

- 授权引用**平台元数据**（`sys_menu` / `sys_form` / `sys_permission` / `sys_field`，platform 平台库）；
  角色与授权表在 **platform 租户库**（`bms_platform_{code}`）——同服务、跨库，校验在同服务内完成；
- **数据权限**按基础数据字典结构化（`sys_dict_*` 与角色表**同租户库**，字段白名单同库直读，无需跨服务读出口）；
  四类策略（选择 / 区域 / 匹配 / 扩展）**只选不编**，`match.field` 须属该字典类型白名单（内置三字段 + 已启用扩展属性），
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
from bms_core.core.exceptions import (
    ParamError,
    RoleFieldMismatchError,
    RoleNotFoundError,
    RoleScopeValueInvalidError,
    RoleTargetInvalidError,
)
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.dict.models import SysDictAttr, SysDictType
from bms_core.permission.version import permission_version_key
from bms_core.scope.extensions import registered_data_scope_extensions
from bms_platform.models.menu import SysField, SysForm, SysMenu, SysPermission
from bms_platform.models.role import (
    NO_SOURCE_MENU_ID,
    PERM_TYPE_FORM,
    PERM_TYPE_MENU,
    PERM_TYPE_PERMISSION,
    PERM_TYPES,
    POLICY_TYPE_EXTENSION,
    POLICY_TYPE_MATCH,
    POLICY_TYPES,
    SysDataScope,
    SysRoleField,
    SysRolePermission,
)
from bms_platform.repositories.role import (
    DataScopeRepository,
    RoleFieldRepository,
    RolePermissionRepository,
    RoleRepository,
)

BUILTIN_MATCH_FIELDS: tuple[str, ...] = ("code", "name", "remark")
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

    dict_type_id: int
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
        """
        self._roles = roles
        self._permissions = permissions
        self._fields = fields
        self._data_scopes = data_scopes
        self._metadata = metadata
        self._uow = uow
        self._cache = cache

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
        """
        async with self._uow.begin():
            await self._require_role(role_id)
            normalized = self._validate_perm_entries(entries)
            await self._ensure_targets_exist(normalized)
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
        """
        async with self._uow.begin():
            await self._require_role(role_id)
            self._validate_field_entries(entries)
            await self._ensure_fields_exist(entries)
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
        """
        async with self._uow.begin():
            await self._require_role(role_id)
            await self._validate_data_scopes(entries)
            await self._data_scopes.delete_by_role(role_id)
            created: ConcurrentStableList[SysDataScope] = ConcurrentStableList()
            for entry in entries:
                created.add(
                    await self._data_scopes.create(
                        role_id=role_id,
                        dict_type_id=entry.dict_type_id,
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
        """校验数据权限条目：字典存在、策略合法、匹配字段与通配符、扩展权限已注册。

        Args:
            entries: 数据权限条目。

        Raises:
            RoleScopeValueInvalidError: 策略 / 匹配值 / 扩展权限非法。
        """
        registered_keys: ConcurrentStableSet[str] = ConcurrentStableSet()
        for extension in registered_data_scope_extensions():
            registered_keys.add(extension.key)
        seen: ConcurrentStableSet[tuple[int, str]] = ConcurrentStableSet()
        for entry in entries:
            if entry.policy_type not in POLICY_TYPES:
                raise RoleScopeValueInvalidError(f"数据权限策略非法：{entry.policy_type}")
            if not await self._dict_type_exists(entry.dict_type_id):
                raise RoleScopeValueInvalidError(f"字典类型不存在：{entry.dict_type_id}")
            key = (entry.dict_type_id, entry.policy_type)
            if key in seen:
                raise RoleScopeValueInvalidError("同一字典同一策略只允许一条")
            seen.add(key)
            if entry.policy_type == POLICY_TYPE_MATCH:
                allowed = await self._match_field_whitelist(entry.dict_type_id)
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

    async def _dict_type_exists(self, dict_type_id: int) -> bool:
        """字典类型是否存在（未软删）。

        Args:
            dict_type_id: 字典类型主键。

        Returns:
            bool: 存在 True。
        """
        session = cast("DbSession", self._uow.session)
        statement = select(SysDictType.id).where(SysDictType.id == dict_type_id, SysDictType.deleted_at.is_(None))
        return (await session.execute(statement)).scalar_one_or_none() is not None

    async def _match_field_whitelist(self, dict_type_id: int) -> ConcurrentStableSet[str]:
        """取某字典类型的可匹配字段白名单（内置三字段 + 已启用扩展属性）。

        Args:
            dict_type_id: 字典类型主键。

        Returns:
            ConcurrentStableSet[str]: 白名单字段键。

        Raises:
            RoleScopeValueInvalidError: 字典类型不存在。
        """
        session = cast("DbSession", self._uow.session)
        type_statement = select(SysDictType.id).where(SysDictType.id == dict_type_id, SysDictType.deleted_at.is_(None))
        if (await session.execute(type_statement)).scalar_one_or_none() is None:
            raise RoleScopeValueInvalidError(f"字典类型不存在：{dict_type_id}")
        attr_statement = select(SysDictAttr.attr_key).where(
            SysDictAttr.dict_type_id == dict_type_id,
            SysDictAttr.status == "enabled",
            SysDictAttr.deleted_at.is_(None),
        )
        allowed: ConcurrentStableSet[str] = ConcurrentStableSet(BUILTIN_MATCH_FIELDS)
        allowed.update((await session.execute(attr_statement)).scalars().all())
        return allowed

    async def _bump_version(self, tenant_id: str | None) -> None:
        """权限版本 +1（授权变更后一次递增，供权限计算失效）。

        Args:
            tenant_id: 租户标识。
        """
        await self._cache.aincrease(permission_version_key(tenant_id))

    async def _require_role(self, role_id: int) -> None:
        """校验角色存在。

        Args:
            role_id: 角色主键。

        Raises:
            RoleNotFoundError: 角色不存在。
        """
        if await self._roles.get(role_id) is None:
            raise RoleNotFoundError()
