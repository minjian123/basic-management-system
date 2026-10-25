"""平台服务：权限数据来源（直查本库，`04_01` 下沉后注入基座引擎）。

平台是权限数据的**所有者**（角色域 5 表在 platform 租户库、菜单 / 权限码元数据在 platform 平台库），
故其数据来源实现直接查本库，不经任何跨服务契约：

- `load_subject`：主体链解析器（直接角色 ∪ mdm 岗位 / 部门链角色）→ 角色集合 → 角色类型 / 授权行 /
  数据范围规则 / 字段收窄（经字段权限 provider 接缝求值）；
- `load_metadata`：`MenuFormService` 快照 → 菜单 → 表单索引、权限码 id → 权限码索引。

**只做取数与映射**：聚合 / 快照 / 缓存全部在基座 `bms_core.permission.engine`——本模块不实现算法，
故与 identity 侧「经契约取数」实现共用同一套判定口径。

**会话口径**：来源是应用级单例（登记在进程级注册表），库会话是请求级资源——故每次取数按当前租户
上下文自行开启只读会话并在返回前关闭，不跨请求持有连接。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import cast

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope
from bms_core.i18n.base import DEFAULT_LOCALE
from bms_core.permission.field import BaseFieldPermissionProvider
from bms_core.permission.resolver import BaseRoleResolver
from bms_core.permission.sources import (
    BasePermissionDataSource,
    DataScopeRule,
    PermissionGrant,
    PermissionMetadata,
    PermissionSubjectData,
)
from bms_core.permission.subject import PermissionSubjectService
from bms_platform.domains.menu_form.public import MenuSnapshot
from bms_platform.domains.permission_meta.permission.metadata import build_menu_metadata_service
from bms_platform.domains.role.public import (
    PERM_TYPE_FORM,
    PERM_TYPE_MENU,
    PERM_TYPE_PERMISSION,
    DataScopeRepository,
    RolePermissionRepository,
    RoleRepository,
)

DEFAULT_METADATA_TTL = 300
"""元数据快照缓存有效期（秒；与权限快照 TTL 同口径）。"""

_PERM_TYPES: ConcurrentStableList[str] = ConcurrentStableList((PERM_TYPE_MENU, PERM_TYPE_FORM, PERM_TYPE_PERMISSION))
"""授权类型取值（与 `sys_role_permission.perm_type` 一致）。"""

ResolversFactory = Callable[[DbSession], tuple[BaseRoleResolver, ...]]
"""解析器工厂：`租户库会话 → 解析器元组`（解析器需要会话，故按会话构造）。"""

FieldProviderFactory = Callable[[DbSession, DbSession], BaseFieldPermissionProvider]
"""字段权限 provider 工厂：`(租户库会话, 平台库会话) → provider`。"""


class PlatformPermissionDataSource(BasePermissionDataSource):
    """平台侧数据来源：直查本库（租户库角色域 + 平台库菜单元数据）。"""

    key: str = "platform_permission_data_source"

    def __init__(
        self,
        *,
        registry: EngineRegistry,
        cache: CacheRegion,
        resolvers_factory: ResolversFactory,
        field_provider_factory: FieldProviderFactory | None = None,
        ttl: int = DEFAULT_METADATA_TTL,
    ) -> None:
        """初始化。

        Args:
            registry: 数据库引擎注册表（按当前租户上下文开库）。
            cache: 缓存能力域（菜单元数据快照缓存）。
            resolvers_factory: 解析器工厂（`租户库会话 → 解析器元组`）。
            field_provider_factory: 字段权限 provider 工厂 `(租户库会话, 平台库会话) → provider`；
                None 表示字段全开。
            ttl: 元数据快照缓存有效期（秒）。
        """
        self._registry = registry
        self._cache = cache
        self._resolvers_factory = resolvers_factory
        self._field_provider_factory = field_provider_factory
        self._ttl = ttl

    async def load_subject(self, *, user_id: int) -> PermissionSubjectData:
        """取用户的聚合输入（角色 / 类型 / 授权 / 数据范围规则 / 字段收窄）。

        Args:
            user_id: 用户主键。

        Returns:
            PermissionSubjectData: 聚合输入。
        """
        async with (
            session_scope(self._registry, read_only=True) as tenant_session,
            session_scope(self._registry, db_key=PLATFORM_DB_KEY, read_only=True) as platform_session,
        ):
            role_ids = await PermissionSubjectService(self._resolvers_factory(tenant_session)).resolve_role_ids(user_id)  # pyright: ignore[reportArgumentType]  # 08_05：注解落集合类，值形态由契约/外部决定
            data = PermissionSubjectData(role_ids=role_ids)
            if not role_ids:
                return data
            for role in await RoleRepository(tenant_session).list_by_ids(role_ids):
                data.role_types.set(role.id, role.role_type)
            for row in await RolePermissionRepository(tenant_session).list_by_roles(role_ids):
                if row.perm_type in _PERM_TYPES:
                    data.grants.add(PermissionGrant(perm_type=row.perm_type, target_id=row.target_id))
            for row in await DataScopeRepository(tenant_session).list_by_roles(role_ids):
                data.data_scope_rules.add(
                    DataScopeRule(
                        data_source_key=row.data_source_key,
                        policy_type=row.policy_type,
                        config=_stable_rows(row.config),
                    )
                )
            provider = self._build_field_provider(tenant_session, platform_session)
            if provider is not None:
                data.field_perms = await provider.resolve(role_ids=role_ids, form_ids=ConcurrentStableSet[int]())
            return data

    async def load_metadata(self, *, locale: str = DEFAULT_LOCALE) -> PermissionMetadata:
        """取权限元数据（菜单 → 表单、权限码 id → 权限码）。

        Args:
            locale: 语言标识（元数据按 locale 本地化，仅影响展示名）。

        Returns:
            PermissionMetadata: 元数据索引。
        """
        async with session_scope(self._registry, db_key=PLATFORM_DB_KEY, read_only=True) as platform_session:
            metadata = build_menu_metadata_service(platform_session, self._cache)
            snapshot = await metadata.load_snapshot(locale=locale, tenant_id=None, ttl=self._ttl)
        return _index_metadata(snapshot)

    def _build_field_provider(
        self, tenant_session: DbSession, platform_session: DbSession
    ) -> BaseFieldPermissionProvider | None:
        """按登记的工厂构造字段权限求值器（未登记 → None，字段全开）。

        Args:
            tenant_session: 租户库会话。
            platform_session: 平台库会话。

        Returns:
            BaseFieldPermissionProvider | None: 求值器；未登记工厂为 None。
        """
        factory = self._field_provider_factory
        if factory is None:
            return None
        return factory(tenant_session, platform_session)


def _stable_rows(raw: object) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """把 `config`（JSON 行列表）规整为保序映射列表。

    Args:
        raw: 原始 `config`（`StableJson` 解出的列表 / 元组）。

    Returns:
        ConcurrentStableList[ConcurrentStableDict[str, object]]: 规则行列表。
    """
    rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    # `StableJson` 读回的是基座集合类（`ConcurrentStableList` / `ConcurrentStableDict`），
    # 不是内建 `list` / `dict`——故按 `Sequence` / `Mapping` 协议判定（内建容器同样满足）。
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        return rows
    for item in cast("Sequence[object]", raw):
        if not isinstance(item, Mapping):
            continue
        stable: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        for key, value in cast("Mapping[object, object]", item).items():
            stable.set(str(key), value)
        rows.add(stable)
    return rows


def _index_metadata(snapshot: MenuSnapshot) -> PermissionMetadata:
    """由菜单快照建两类索引（菜单 → 关联表单 ID、权限码 id → 权限码字符串）。

    Args:
        snapshot: 菜单元数据快照（未按用户过滤）。

    Returns:
        PermissionMetadata: 元数据索引。
    """
    metadata = PermissionMetadata(version=snapshot.version)
    for menu in snapshot.menus:
        form_ids: ConcurrentStableList[int] = ConcurrentStableList()
        for form in menu.forms:
            form_ids.add(form.id)
            for button in form.buttons:
                metadata.permission_codes.set(button.permission_id, button.permission_code)
        if form_ids:
            metadata.menu_forms.set(menu.id, form_ids)
    return metadata
