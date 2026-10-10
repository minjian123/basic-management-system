"""平台服务 services 层：主体链权限计算引擎（`02_04`）。

主流程五步（《02_04 详细设计》§11.2「主流程不变式」）：

1. **解析器并集**（`PermissionSubjectService`：直接角色 ∪ mdm 岗位 / 部门链角色，来源经注册表注入）；
2. **权限聚合**（角色集合 → `sys_role_permission` → 业务码 ∪ 动作码，**两段解析**）；
3. **快照**（`bms_core.permission.snapshot.PermissionSnapshot`：码集 + 数据范围 + 字段权限 + `tier` / `profile`）；
4. **缓存**（键 `bms:{租户}:perm:{用户}:{版本}`；租户级版本变更即换键）；
5. **供数**（两级校验点 / 字段权限 / 数据范围 / 权限概要四处消费）。

聚合口径：

- **菜单授权**：菜单入口计入 `granted_menu_ids`，并连带其关联表单计入 `granted_form_ids`（入口可见性）；
- **表单授权**：表单计入 `granted_form_ids`（入口可见性）；
- **权限码授权**：`perm_type="permission"` 的 `target_id` 为权限码主键，经**菜单快照的按钮元数据**
  建 `permission_id → permission_code` 索引解析（同源于 `sys_button` ⋈ `sys_permission`，免跨库二次查询；
  未挂按钮的权限码不进索引——与「按钮即授权入口」的界面口径一致）。

档位（`profile`）与 `tier` 分列：`profile` 是引擎能力档位（`smb` / `enterprise` / `enterprise_hr`），
`tier` 是主体层级豁免标记（`standard` / `system_admin` / `platform_admin`）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.objects import BaseFrameworkObject
from bms_core.i18n.base import DEFAULT_LOCALE
from bms_core.permission.field import BaseFieldPermissionProvider, FieldPermission
from bms_core.permission.profile import DEFAULT_PROFILE
from bms_core.permission.snapshot import (
    TIER_PLATFORM_ADMIN,
    TIER_STANDARD,
    TIER_SYSTEM_ADMIN,
    PermissionSnapshot,
)
from bms_core.permission.version import permission_user_cache_key, permission_version_key
from bms_platform.models.role import PERM_TYPE_FORM, PERM_TYPE_MENU, PERM_TYPE_PERMISSION, ROLE_TYPE_SYSTEM
from bms_platform.repositories.role import (
    DataScopeRepository,
    RolePermissionRepository,
    RoleRepository,
)
from bms_platform.services.menu import MenuMetadataService, MenuSnapshot
from bms_platform.services.permission_subject import PermissionSubjectService

DEFAULT_SNAPSHOT_TTL = 300
"""权限快照缓存有效期（秒；缺省口径，可经 `[permission].options.snapshot_ttl_seconds` 覆盖）。"""


@dataclass
class _Granted:
    """聚合中间结果：权限码集合 + 入口（菜单 / 表单）授权集合。"""

    permission_codes: ConcurrentStableSet[str] = field(default_factory=lambda: ConcurrentStableSet[str]())
    menu_ids: ConcurrentStableSet[int] = field(default_factory=lambda: ConcurrentStableSet[int]())
    form_ids: ConcurrentStableSet[int] = field(default_factory=lambda: ConcurrentStableSet[int]())


async def invalidate_permission_cache(
    cache: CacheRegion, *, tenant_id: str | None, user_ids: tuple[int, ...] | None = None
) -> int:
    """失效权限快照（租户权限版本 +1；给定用户时删除其旧版本缓存键）。

    供跨服务变更（mdm 岗位 / 部门 / 角色分配）经内部失效端点触发，亦供本仓服务层复用。

    Args:
        cache: 缓存能力域。
        tenant_id: 租户标识（版本键作用域）。
        user_ids: 受影响用户主键（None 表示全租户，仅版本 +1）。

    Returns:
        int: 递增后的权限版本号。
    """
    version = await cache.aincrease(permission_version_key(tenant_id))
    if user_ids:
        for user_id in user_ids:
            await cache.adelete(permission_user_cache_key(tenant_id, user_id, version - 1))
    return version


class PermissionService(BaseFrameworkObject):
    """主体链权限计算引擎：角色收敛 → 权限聚合 → 快照与缓存。"""

    def __init__(
        self,
        *,
        roles: RoleRepository,
        permissions: RolePermissionRepository,
        data_scopes: DataScopeRepository,
        metadata: MenuMetadataService,
        subject: PermissionSubjectService,
        cache: CacheRegion,
        field_provider: BaseFieldPermissionProvider | None = None,
        profile: str = DEFAULT_PROFILE,
        ttl: int = DEFAULT_SNAPSHOT_TTL,
        exempt_role_types: tuple[str, ...] = (ROLE_TYPE_SYSTEM,),
    ) -> None:
        """初始化。

        Args:
            roles: 角色仓储（`sys_role`；豁免层级判定）。
            permissions: 角色授权仓储（`sys_role_permission`）。
            data_scopes: 角色数据权限仓储（`sys_data_scope`）。
            metadata: 菜单与权限元数据服务（平台库；业务码 / 动作码解析源，自带缓存与版本失效）。
            subject: 主体链收敛服务（解析器链）。
            cache: 缓存能力域（快照缓存 + 权限版本）。
            field_provider: 字段权限求值器（None 表示无字段收窄，字段全开）。
            profile: 引擎档位（缺省 `smb`）。
            ttl: 快照缓存有效期（秒）。
            exempt_role_types: 豁免层级判定的角色类型（缺省 `system`，即系统管理员）。
        """
        self._roles = roles
        self._permissions = permissions
        self._data_scopes = data_scopes
        self._metadata = metadata
        self._subject = subject
        self._cache = cache
        self._field_provider = field_provider
        self._profile = profile
        self._ttl = ttl
        self._exempt_role_types = exempt_role_types

    async def current_version(self, tenant_id: str | None) -> int:
        """取当前租户权限版本（缓存未命中按 0 处理、不回写）。

        Args:
            tenant_id: 租户标识（None 表示全局兜底位）。

        Returns:
            int: 权限版本号。
        """
        raw = await self._cache.aget(permission_version_key(tenant_id))
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw
        return 0

    async def snapshot_for(self, *, user_id: int, tenant_id: str | None) -> PermissionSnapshot:
        """取用户权限快照（命中缓存即返回；未命中则计算并写缓存）。

        Args:
            user_id: 用户主键。
            tenant_id: 租户标识（缓存键作用域）。

        Returns:
            PermissionSnapshot: 用户权限快照。
        """
        version = await self.current_version(tenant_id)
        key = permission_user_cache_key(tenant_id, user_id, version)
        cached = await self._cache.aget(key)
        if cached is not None:
            snapshot = PermissionSnapshot.from_payload(cached)
            if snapshot.version == version:
                return snapshot
        snapshot = await self.compute(user_id=user_id, version=version)
        await self._cache.aset(key, snapshot.to_payload(), ttl=self._ttl)
        return snapshot

    async def compute(self, *, user_id: int, version: int) -> PermissionSnapshot:
        """按主体链计算用户权限快照（不读缓存；供缓存回源与用例断言）。

        Args:
            user_id: 用户主键。
            version: 写入快照的权限版本（校验与排障用）。

        Returns:
            PermissionSnapshot: 用户权限快照。
        """
        role_ids = await self._subject.resolve_role_ids(user_id)
        granted = await self._aggregate(role_ids)
        return PermissionSnapshot(
            version=version,
            profile=self._profile,
            tier=await self._tier(role_ids),
            permission_codes=granted.permission_codes,
            granted_menu_ids=granted.menu_ids,
            granted_form_ids=granted.form_ids,
            data_scopes=await self._data_scope_rules(role_ids),
            field_perms=await self._field_perms(role_ids),
        )

    async def _field_perms(self, role_ids: ConcurrentStableSet[int]) -> ConcurrentStableList[FieldPermission]:
        """求值字段权限收窄项（无 provider / 无角色即全开，返回空列表）。

        Args:
            role_ids: 角色主键集合。

        Returns:
            ConcurrentStableList[FieldPermission]: 收窄项列表（空表示全开）。
        """
        if self._field_provider is None or not role_ids:
            return ConcurrentStableList()
        return await self._field_provider.resolve(role_ids=role_ids, form_ids=ConcurrentStableSet[int]())

    async def invalidate(self, *, tenant_id: str | None, user_ids: tuple[int, ...] | None = None) -> int:
        """失效权限快照：租户权限版本 +1；给定用户时顺带删除其旧版本键。

        Args:
            tenant_id: 租户标识（版本键作用域）。
            user_ids: 受影响用户主键（None 表示全租户，仅版本 +1）。

        Returns:
            int: 递增后的权限版本号。
        """
        return await invalidate_permission_cache(self._cache, tenant_id=tenant_id, user_ids=user_ids)

    async def _aggregate(self, role_ids: ConcurrentStableSet[int]) -> _Granted:
        """聚合角色授权为权限码集合与入口授权集合（两段解析）。

        Args:
            role_ids: 角色主键集合（空集返回空集合）。

        Returns:
            _Granted: 权限码集合 + 菜单入口 / 表单授权集合。
        """
        granted = _Granted()
        if not role_ids:
            return granted
        snapshot = await self._metadata.load_snapshot(locale=DEFAULT_LOCALE, tenant_id=None, ttl=self._ttl)
        menu_forms, permission_codes = _index_metadata(snapshot)
        for row in await self._permissions.list_by_roles(role_ids):
            if row.perm_type == PERM_TYPE_MENU:
                granted.menu_ids.add(row.target_id)
                for form_id in menu_forms.get(row.target_id, ConcurrentStableList[int]()):
                    granted.form_ids.add(form_id)
            elif row.perm_type == PERM_TYPE_FORM:
                granted.form_ids.add(row.target_id)
            elif row.perm_type == PERM_TYPE_PERMISSION:
                code = permission_codes.get(row.target_id)
                if code is not None:
                    granted.permission_codes.add(code)
        return granted

    async def _tier(self, role_ids: ConcurrentStableSet[int]) -> str:
        """判定主体层级（命中豁免角色类型即系统管理员层级）。

        Args:
            role_ids: 角色主键集合。

        Returns:
            str: 层级标记（`standard` / `system_admin`）。
        """
        for role in await self._roles.list_by_ids(role_ids):
            if role.role_type in self._exempt_role_types:
                return TIER_SYSTEM_ADMIN
        return TIER_STANDARD

    async def _data_scope_rules(
        self, role_ids: ConcurrentStableSet[int]
    ) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
        """取角色数据范围规则（多角色并集，读注入与写校验共用）。

        Args:
            role_ids: 角色主键集合。

        Returns:
            ConcurrentStableList[ConcurrentStableDict[str, object]]: 规则列表（字典 / 策略 / 配置）。
        """
        rules: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
        if not role_ids:
            return rules
        for row in await self._data_scopes.list_by_roles(role_ids):
            item: ConcurrentStableDict[str, object] = ConcurrentStableDict()
            item.set("dict_type_id", row.dict_type_id)
            item.set("policy_type", row.policy_type)
            item.set("config", list(row.config))
            rules.add(item)
        return rules


PLATFORM_TIER = TIER_PLATFORM_ADMIN
"""平台层层级标记（无租户上下文的运营请求；导出便于上层判定）。"""


def _index_metadata(
    snapshot: MenuSnapshot,
) -> tuple[
    ConcurrentStableDict[int, ConcurrentStableList[int]],
    ConcurrentStableDict[int, str],
]:
    """由菜单快照建两类索引（菜单 → 关联表单 ID、权限码 → 权限码字符串）。

    Args:
        snapshot: 菜单元数据快照（未按用户过滤）。

    Returns:
        tuple[ConcurrentStableDict[int, ConcurrentStableList[int]], ConcurrentStableDict[int, str]]:
        （菜单关联表单 ID，权限码字符串）。
    """
    menu_forms: ConcurrentStableDict[int, ConcurrentStableList[int]] = ConcurrentStableDict()
    permission_codes: ConcurrentStableDict[int, str] = ConcurrentStableDict()
    for menu in snapshot.menus:
        form_ids: ConcurrentStableList[int] = ConcurrentStableList()
        for form in menu.forms:
            form_ids.add(form.id)
            for button in form.buttons:
                permission_codes.set(button.permission_id, button.permission_code)
        if form_ids:
            menu_forms.set(menu.id, form_ids)
    return menu_forms, permission_codes
