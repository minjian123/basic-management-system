"""主体链权限计算引擎（域 `permission`）：判定之外的全部**计算**。

主流程五步（《02_04 详细设计》§11.2「主流程不变式」）：

1. **角色收敛**：解析器并集去重（`permission/subject.py`，来源经注册表注入）——由**数据来源实现**在
   `load_subject` 内调用，引擎只消费收敛结果（这样解析器链接缝留在基座、数据访问留在服务侧）；
2. **权限聚合**：授权行 → 权限码集合 + 入口授权集合（**两段解析**：菜单 / 表单 → 入口；权限码 → `业务码:动作码`）；
3. **快照**：`permission/snapshot.py::PermissionSnapshot`（码集 + 数据范围 + 字段权限 + `tier` / `profile`）；
4. **缓存**：键 `bms:{租户}:perm:{用户}:{版本}`（`permission/version.py`），租户级版本变更即换键；
5. **供数**：两级校验点 / 字段权限 / 数据范围 / 权限概要四处消费。

**数据访问全部经接缝**（`permission/sources.py`）：本模块不 import 任何服务包、不碰任何 ORM，故可随
引擎一并下沉共享基座；服务侧只提供数据来源实现（platform 直查本库、identity 经契约取数）。

聚合口径（与下沉前一致）：

- **菜单授权**：菜单入口计入 `granted_menu_ids`，并连带其关联表单计入 `granted_form_ids`（入口可见性）；
- **表单授权**：表单计入 `granted_form_ids`（入口可见性）；
- **权限码授权**：`perm_type="permission"` 的 `target_id` 经元数据的权限码索引解析为 `业务码:动作码`；
  未进索引的权限码不计入（与「按钮即授权入口」的界面口径一致）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.i18n.base import DEFAULT_LOCALE
from bms_core.permission.profile import DEFAULT_PROFILE
from bms_core.permission.snapshot import (
    TIER_PLATFORM_ADMIN,
    TIER_STANDARD,
    TIER_SYSTEM_ADMIN,
    PermissionSnapshot,
)
from bms_core.permission.sources import (
    BasePermissionDataSource,
    PermissionMetadata,
    PermissionSubjectData,
)
from bms_core.permission.version import permission_user_cache_key, permission_version_key

DEFAULT_SNAPSHOT_TTL = 300
"""权限快照缓存有效期（秒；缺省口径，可经 `[permission].options.snapshot_ttl_seconds` 覆盖）。"""

PERM_TYPE_MENU = "menu"
"""授权类型：菜单入口（仅菜单入口；勾选连带授予其表单查看权限）。"""

PERM_TYPE_FORM = "form"
"""授权类型：表单（「查看」= 表单权限；可由菜单入口连带或表单级直接授予）。"""

PERM_TYPE_PERMISSION = "permission"
"""授权类型：权限码（业务码 × 动作码组合，默认无）。"""

ROLE_TYPE_SYSTEM = "system"
"""角色类型：系统管理员（缺省豁免层级判定依据；与 platform 侧 `SEPARATION_ROLE_TYPES` 同值）。"""


@dataclass(frozen=True)
class _Granted(BaseValueObject):
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


class PermissionEngine(BaseFrameworkObject):
    """主体链权限计算引擎：角色收敛 → 权限聚合 → 快照与缓存（数据访问经接缝）。"""

    def __init__(
        self,
        *,
        source: BasePermissionDataSource,
        cache: CacheRegion,
        profile: str = DEFAULT_PROFILE,
        ttl: int = DEFAULT_SNAPSHOT_TTL,
        exempt_role_types: tuple[str, ...] = (ROLE_TYPE_SYSTEM,),
        locale: str = DEFAULT_LOCALE,
    ) -> None:
        """初始化。

        Args:
            source: 权限数据来源（角色 / 类型 / 授权 / 数据范围 / 字段收窄 / 元数据）。
            cache: 缓存能力域（快照缓存 + 权限版本）。
            profile: 引擎档位（缺省 `smb`）。
            ttl: 快照缓存有效期（秒）。
            exempt_role_types: 豁免层级判定的角色类型（缺省 `system`，即系统管理员）。
            locale: 元数据语言标识（仅影响展示名，不影响索引）。
        """
        self._source = source
        self._cache = cache
        self._profile = profile
        self._ttl = ttl
        self._exempt_role_types = exempt_role_types
        self._locale = locale

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
        data = await self._source.load_subject(user_id=user_id)
        granted = await self._aggregate(data)
        return PermissionSnapshot(
            version=version,
            profile=self._profile,
            tier=self._tier(data),
            permission_codes=granted.permission_codes,
            granted_menu_ids=granted.menu_ids,
            granted_form_ids=granted.form_ids,
            data_scopes=self._data_scope_rules(data),
            field_perms=data.field_perms,
        )

    async def invalidate(self, *, tenant_id: str | None, user_ids: tuple[int, ...] | None = None) -> int:
        """失效权限快照：租户权限版本 +1；给定用户时顺带删除其旧版本键。

        Args:
            tenant_id: 租户标识（版本键作用域）。
            user_ids: 受影响用户主键（None 表示全租户，仅版本 +1）。

        Returns:
            int: 递增后的权限版本号。
        """
        return await invalidate_permission_cache(self._cache, tenant_id=tenant_id, user_ids=user_ids)

    async def _aggregate(self, data: PermissionSubjectData) -> _Granted:
        """聚合授权行为权限码集合与入口授权集合（两段解析）。

        Args:
            data: 聚合输入（授权行 + 角色集合）。

        Returns:
            _Granted: 权限码集合 + 菜单入口 / 表单授权集合。
        """
        granted = _Granted()
        if not data.role_ids:
            return granted
        metadata = await self._source.load_metadata(locale=self._locale)
        _merge_grants(data, metadata, granted)
        return granted

    def _tier(self, data: PermissionSubjectData) -> str:
        """判定主体层级（命中豁免角色类型即系统管理员层级）。

        Args:
            data: 聚合输入（角色类型映射）。

        Returns:
            str: 层级标记（`standard` / `system_admin`）。
        """
        for role_id in data.role_ids:
            role_type = data.role_types.get(role_id)
            if role_type is not None and role_type in self._exempt_role_types:
                return TIER_SYSTEM_ADMIN
        return TIER_STANDARD

    @staticmethod
    def _data_scope_rules(data: PermissionSubjectData) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
        """取角色数据范围规则（多角色并集，读注入与写校验共用）。

        Args:
            data: 聚合输入（数据范围规则）。

        Returns:
            ConcurrentStableList[ConcurrentStableDict[str, object]]: 规则列表（字典 / 策略 / 配置）。
        """
        rules: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
        for rule in data.data_scope_rules:
            item: ConcurrentStableDict[str, object] = ConcurrentStableDict()
            item.set("data_source_key", rule.data_source_key)
            item.set("policy_type", rule.policy_type)
            item.set("config", list(rule.config))
            rules.add(item)
        return rules


PLATFORM_TIER = TIER_PLATFORM_ADMIN
"""平台层层级标记（无租户上下文的运营请求；导出便于上层判定）。"""


def _merge_grants(data: PermissionSubjectData, metadata: PermissionMetadata, granted: _Granted) -> None:
    """把授权行按两段解析并入聚合结果（菜单连带表单、权限码经索引解析）。

    Args:
        data: 聚合输入（授权行）。
        metadata: 元数据索引（菜单 → 表单、权限码 id → 权限码）。
        granted: 聚合结果（就地写入）。
    """
    for row in data.grants:
        if row.perm_type == PERM_TYPE_MENU:
            granted.menu_ids.add(row.target_id)
            for form_id in metadata.menu_forms.get(row.target_id, ConcurrentStableList[int]()):
                granted.form_ids.add(form_id)
        elif row.perm_type == PERM_TYPE_FORM:
            granted.form_ids.add(row.target_id)
        elif row.perm_type == PERM_TYPE_PERMISSION:
            code = metadata.permission_codes.get(row.target_id)
            if code is not None:
                granted.permission_codes.add(code)
