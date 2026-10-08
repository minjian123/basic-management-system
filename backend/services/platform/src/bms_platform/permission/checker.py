"""平台服务：真实权限校验器（`[permission].provider = "rbac"`）。

判定口径（《02_04 详细设计》§5.4）：

1. **请求级预加载**：基座校验依赖调 `aprepare`（异步）——本实现按当前请求解析主体链、计算用户权限快照
   并落 contextvar `current_permission_snapshot`；
2. **同步判定**：`check(code)` 只读快照——`tier` 豁免（超管 / 系统管理员 → 恒真）→ 码集命中 →
   **校验链**（`bms_core.permission.guard`，基础版空链）逐环节放行；
3. **无用户上下文**（服务身份 / 平台运营请求）：鉴权由认证链与服务白名单承担，本实现按**平台层层级**豁免
   （`tier=platform_admin`），避免内部通道被误拒。

请求态经 contextvar 承载（校验器是应用级单例，`resolve_plugin` 复用唯一实例）；两个库会话来自请求：
租户库经依赖注入的工作单元、平台库（菜单元数据）经 `session_scope(db_key="platform", read_only=True)`。
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, cast

from fastapi import Request

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.context import current_tenant_id, current_user_id
from bms_core.core.factory import BasePluginFactory
from bms_core.core.plugin import default_plugin_registry, register_plugin
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.session import session_scope
from bms_core.permission.base import BasePermissionChecker
from bms_core.permission.guard import PermissionGuardContext, guards_allow
from bms_core.permission.profile import DEFAULT_PROFILE
from bms_core.permission.snapshot import TIER_PLATFORM_ADMIN, PermissionSnapshot
from bms_core.servicecall.base import BaseServiceClient
from bms_platform.models.role import ROLE_TYPE_SYSTEM
from bms_platform.permission.metadata import build_menu_metadata_service
from bms_platform.repositories.role import (
    DataScopeRepository,
    RolePermissionRepository,
    RoleRepository,
    UserRoleRepository,
)
from bms_platform.services.permission import DEFAULT_SNAPSHOT_TTL, PermissionService
from bms_platform.services.permission_subject import (
    DirectRoleResolver,
    OrgRoleResolver,
    PermissionSubjectService,
)

RBAC_PROVIDER_NAME = "rbac"
"""真实权限校验器实现名（`[permission].provider`）。"""

current_permission_snapshot: ContextVar[PermissionSnapshot | None] = ContextVar(
    "current_permission_snapshot", default=None
)
"""当前请求的用户权限快照（`aprepare` 写入、`check` 只读；请求间隔离）。"""

_PREPARED_STATE_ATTR = "permission_prepared"
"""请求标记属性：同一请求内只预加载一次（多权限码端点复用）。"""

_REGISTERED_REGISTRIES: ConcurrentStableList[object] = ConcurrentStableList()
"""已登记 `rbac` 的注册表实例清单（按实例幂等；注册表重置后需重新登记）。"""


class RbacPermissionChecker(BasePermissionChecker):
    """真实权限校验器（主体链 → 权限快照 → 两级校验 + 校验链）。

    实现名 `rbac` **不在类上声明** `plugin_name`（避免「导入即自动登记」与工厂重名）——
    登记一律经 `RbacPermissionCheckerFactory`（需注入档位与选项）。
    """

    def __init__(
        self,
        *,
        profile: str = DEFAULT_PROFILE,
        ttl: int = DEFAULT_SNAPSHOT_TTL,
        exempt_role_types: tuple[str, ...] = (ROLE_TYPE_SYSTEM,),
        require_org_roles: bool = False,
    ) -> None:
        """初始化。

        Args:
            profile: 引擎档位（缺省 `smb`）。
            ttl: 权限快照缓存有效期（秒）。
            exempt_role_types: 豁免层级判定的角色类型（缺省 `system`，即系统管理员）。
            require_org_roles: 跨服务角色解析严格模式（`false` 表示不可达即降级）。
        """
        self._profile = profile
        self._ttl = ttl
        self._exempt_role_types = exempt_role_types
        self._require_org_roles = require_org_roles

    def check(self, code: str) -> bool:
        """同步判定当前请求是否持权限码（只读预加载快照）。

        Args:
            code: 权限码（业务码或 `业务:动作`）。

        Returns:
            bool: 允许为 True（未预加载时从严拒绝，提示依赖漏挂）。
        """
        snapshot = current_permission_snapshot.get()
        if snapshot is None:
            return False
        if snapshot.exempt:
            return True
        if not snapshot.holds(code):
            return False
        context = PermissionGuardContext(
            code=code,
            user_id=current_user_id.get(),
            tenant_id=current_tenant_id.get(),
            snapshot=snapshot,
        )
        return guards_allow(context)

    async def aprepare(self, *, request: Request) -> None:
        """请求级预加载：计算并缓存当前用户权限快照。

        依赖自取（基座不注入）：缓存 / 引擎注册表 / 服务客户端取自 `request.app.state`；
        租户库会话按当前租户上下文开启，平台库会话显式按平台库键开启（均为只读）。

        Args:
            request: 当前请求。
        """
        if getattr(request.state, _PREPARED_STATE_ATTR, False):
            return
        setattr(request.state, _PREPARED_STATE_ATTR, True)
        user_id = current_user_id.get()
        if user_id is None:
            current_permission_snapshot.set(PermissionSnapshot(profile=self._profile, tier=TIER_PLATFORM_ADMIN))
            return
        tenant_id = current_tenant_id.get()
        registry: Any = request.app.state.engine_registry
        cache = cast("CacheRegion", request.app.state.cache)
        service_client = cast("BaseServiceClient", request.app.state.service_client)
        async with (
            session_scope(registry, read_only=True) as session,
            session_scope(registry, db_key=PLATFORM_DB_KEY, read_only=True) as platform_session,
        ):
            resolvers = (
                DirectRoleResolver(UserRoleRepository(session)),
                OrgRoleResolver(service_client, require_roles=self._require_org_roles),
            )
            service = PermissionService(
                roles=RoleRepository(session),
                permissions=RolePermissionRepository(session),
                data_scopes=DataScopeRepository(session),
                metadata=build_menu_metadata_service(platform_session, cache),
                subject=PermissionSubjectService(resolvers),
                cache=cache,
                profile=self._profile,
                ttl=self._ttl,
                exempt_role_types=self._exempt_role_types,
            )
            snapshot = await service.snapshot_for(user_id=user_id, tenant_id=tenant_id)
        current_permission_snapshot.set(snapshot)


class RbacPermissionCheckerFactory(BasePluginFactory[RbacPermissionChecker]):
    """真实权限校验器工厂（装配期登记 `[permission].provider = "rbac"`）。"""

    plugin_key: str = "permission"
    plugin_name: str = RBAC_PROVIDER_NAME

    def __init__(self, settings: Settings) -> None:
        """初始化。

        必填 `settings`（非零参）：`BaseFactory` 同为 `BasePluggable`，零参可实例化的工厂类会被
        **自动登记**为能力实现（登记的 `impl` 是工厂类本身，注册表调用它产出的是工厂实例而非
        产出物）——必填构造参数是「工厂只经显式登记生效」的既有约定。

        Args:
            settings: 应用配置（读 `[permission]` 的档位与选项）。
        """
        self._profile = settings.permission.profile or DEFAULT_PROFILE
        raw_options: Any = settings.permission.options
        self._options: Any = raw_options if isinstance(raw_options, dict) else {}

    def create(self, options: object = None) -> RbacPermissionChecker:
        """构造真实校验器（选项缺省回落实现缺省值）。

        Args:
            options: 未使用（选项在工厂初始化时读取）。

        Returns:
            RbacPermissionChecker: 校验器实例。
        """
        del options
        raw_ttl = self._options.get("snapshot_ttl_seconds")
        ttl = raw_ttl if isinstance(raw_ttl, int) and not isinstance(raw_ttl, bool) else DEFAULT_SNAPSHOT_TTL
        raw_types = self._options.get("exempt_role_types")
        exempt = (
            tuple(str(item) for item in cast("Any", raw_types))
            if isinstance(raw_types, list | tuple)
            else (ROLE_TYPE_SYSTEM,)
        )
        return RbacPermissionChecker(
            profile=self._profile,
            ttl=ttl,
            exempt_role_types=exempt,
            require_org_roles=bool(self._options.get("require_org_roles", False)),
        )


def register_rbac_permission(settings: Settings) -> None:
    """登记真实校验器工厂（服务装配期调用，**须在建注册表之前**）。

    **按注册表实例幂等**（插件注册表是进程级、且可被测试重置）：同一注册表只登记一次；
    换个注册表实例（重置 / 替换）则重新登记，避免重置后 `rbac` 丢失。

    Args:
        settings: 应用配置（读 `[permission]` 的档位与选项）。
    """
    registry = default_plugin_registry()
    if any(item is registry for item in _REGISTERED_REGISTRIES):
        return
    register_plugin("permission", RBAC_PROVIDER_NAME, RbacPermissionCheckerFactory(settings))
    _REGISTERED_REGISTRIES.add(registry)
