"""基座内建真实权限校验器（`[permission].provider = "rbac"`，域 `permission`）。

判定口径（《02_04 详细设计》§5.4，下沉后不变）：

1. **请求级预加载**：基座校验依赖调 `aprepare`（异步）——按当前请求取用户权限快照并落 contextvar
   `current_permission_snapshot`；
2. **同步判定**：`check(code)` 只读快照——`tier` 豁免（超管 / 系统管理员 → 恒真）→ 码集命中 →
   **校验链**（`permission/guard.py`，基础版空链）逐环节放行；
3. **无用户上下文**（服务身份 / 平台运营请求）：鉴权由认证链与服务白名单承担，本实现按**平台层层级**
   豁免（`tier=platform_admin`），避免内部通道被误拒。

**数据访问经接缝**（`permission/sources.py`）：本模块只依赖 `BasePermissionDataSource` 与
`CacheRegion`，不 import 任何服务包、不碰任何 ORM——故随引擎一并落在共享基座。
服务侧在 `prepare_settings` 里登记自己的数据来源实现（platform 直查本库、identity 经契约取数）；
**provider 配了 `rbac` 却没登记数据来源即启动拒启**（不静默放行、不静默全拒）。
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import Request

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.context import current_tenant_id, current_user_id
from bms_core.core.exceptions import PluginError
from bms_core.core.factory import BasePluginFactory
from bms_core.core.plugin import default_plugin_registry, register_plugin
from bms_core.i18n.base import DEFAULT_LOCALE
from bms_core.permission.base import BasePermissionChecker
from bms_core.permission.engine import DEFAULT_SNAPSHOT_TTL, PermissionEngine
from bms_core.permission.guard import PermissionGuardContext, guards_allow
from bms_core.permission.profile import DEFAULT_PROFILE
from bms_core.permission.snapshot import (
    TIER_PLATFORM_ADMIN,
    PermissionSnapshot,
    get_current_permission_snapshot,
    set_current_permission_snapshot,
)
from bms_core.permission.sources import (
    BasePermissionDataSource,
    current_permission_data_source,
    current_permission_data_source_factory,
    has_permission_data_source,
)

RBAC_PROVIDER_NAME = "rbac"
"""真实权限校验器实现名（`[permission].provider`）。"""

"""当前请求的用户权限快照由**基座契约位**承载（`permission/snapshot.py::current_permission_snapshot`）：
`aprepare` 写入、`check` 与各消费方（字段权限标记 / 数据范围注入 / 权限概要）只读，请求间隔离。
"""

_PREPARED_STATE_ATTR = "permission_prepared"
"""请求标记属性：同一请求内只预加载一次（多权限码端点复用）。"""

_REGISTERED_REGISTRIES: ConcurrentStableList[object] = ConcurrentStableList()
"""已登记 `rbac` 的注册表实例清单（按实例幂等；注册表重置后需重新登记）。"""

_MISSING_SOURCE_MESSAGE = (
    "`[permission].provider = rbac` 但未登记权限数据来源：服务须在 prepare_settings 中调用 "
    "register_permission_data_source（platform 直查本库 / identity 经 platform 内部契约取数）"
)
"""数据来源缺失的拒启提示（启动期与请求期共用同一口径）。"""


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
        exempt_role_types: tuple[str, ...] = ("system",),
        locale: str = DEFAULT_LOCALE,
    ) -> None:
        """初始化。

        Args:
            profile: 引擎档位（缺省 `smb`）。
            ttl: 权限快照缓存有效期（秒）。
            exempt_role_types: 豁免层级判定的角色类型（缺省 `system`，即系统管理员）。
            locale: 元数据语言标识（仅影响展示名，不影响索引）。
        """
        self._profile = profile
        self._ttl = ttl
        self._exempt_role_types = exempt_role_types
        self._locale = locale

    def check(self, code: str) -> bool:
        """同步判定当前请求是否持权限码（只读预加载快照）。

        Args:
            code: 权限码（业务码或 `业务:动作`）。

        Returns:
            bool: 允许为 True（未预加载时从严拒绝，提示依赖漏挂）。
        """
        snapshot = get_current_permission_snapshot()
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

        依赖自取（基座不注入）：缓存取自 `request.app.state`；数据来源取自进程级注册表
        （服务在 `prepare_settings` 登记）。无用户上下文 → 平台层快照（豁免）。

        Args:
            request: 当前请求。

        Raises:
            PluginError: 未登记数据来源（provider 配了 `rbac` 却没有取数实现）。
        """
        if getattr(request.state, _PREPARED_STATE_ATTR, False):
            return
        setattr(request.state, _PREPARED_STATE_ATTR, True)
        user_id = current_user_id.get()
        if user_id is None:
            set_current_permission_snapshot(PermissionSnapshot(profile=self._profile, tier=TIER_PLATFORM_ADMIN))
            return
        source = await _resolve_source(request)
        engine = PermissionEngine(
            source=source,
            cache=cast("CacheRegion", request.app.state.cache),
            profile=self._profile,
            ttl=self._ttl,
            exempt_role_types=self._exempt_role_types,
            locale=self._locale,
        )
        snapshot = await engine.snapshot_for(user_id=user_id, tenant_id=current_tenant_id.get())
        set_current_permission_snapshot(snapshot)


async def _resolve_source(request: Request) -> BasePermissionDataSource:
    """取本次请求的数据来源（请求级工厂优先，其次实例型）。

    Args:
        request: 当前请求（工厂需要请求态会话）。

    Returns:
        BasePermissionDataSource: 数据来源实例。

    Raises:
        PluginError: 未登记任何数据来源（provider 配了 `rbac` 却没有取数实现）。
    """
    factory = current_permission_data_source_factory()
    if factory is not None:
        return await factory(request)
    source = current_permission_data_source()
    if source is None:
        raise PluginError(_MISSING_SOURCE_MESSAGE)
    return source


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
        # `options` 是基座契约集合（`ConcurrentStableDict`，`Mapping` 子类），直接持有原集合
        self._options: ConcurrentStableDict[str, object] = settings.permission.options

    def create(self, options: object = None) -> RbacPermissionChecker:
        """构造真实校验器（选项缺省回落实现缺省值）。

        Args:
            options: 未使用（选项在工厂初始化时读取）。

        Returns:
            RbacPermissionChecker: 校验器实例。

        Raises:
            PluginError: 未登记权限数据来源（`provider = rbac` 但服务未注入取数实现）。
        """
        del options
        if not has_permission_data_source():
            raise PluginError(_MISSING_SOURCE_MESSAGE)
        raw_ttl = self._options.get("snapshot_ttl_seconds")
        ttl = raw_ttl if isinstance(raw_ttl, int) and not isinstance(raw_ttl, bool) else DEFAULT_SNAPSHOT_TTL
        raw_types = self._options.get("exempt_role_types")
        exempt = (
            tuple(str(item) for item in cast("Any", raw_types)) if isinstance(raw_types, list | tuple) else ("system",)
        )
        raw_locale = self._options.get("locale")
        locale = raw_locale if isinstance(raw_locale, str) and raw_locale else DEFAULT_LOCALE
        return RbacPermissionChecker(
            profile=self._profile,
            ttl=ttl,
            exempt_role_types=exempt,
            locale=locale,
        )


def register_rbac_permission(settings: Settings) -> None:
    """登记真实校验器工厂（基座装配期调用，**须在建注册表之前**）。

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
