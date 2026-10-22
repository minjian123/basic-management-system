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

import asyncio
import contextlib
from typing import Any, cast

from fastapi import Request

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.context import current_tenant_id, current_user_id
from bms_core.core.exceptions import PluginError
from bms_core.core.factory import BasePluginFactory
from bms_core.core.logging import get_logger
from bms_core.core.plugin import default_plugin_registry, register_plugin
from bms_core.i18n.base import DEFAULT_LOCALE
from bms_core.permission.base import BasePermissionChecker
from bms_core.permission.cache import (
    DEFAULT_IDLE_SWEEP_INTERVAL,
    DEFAULT_IDLE_TIMEOUT,
    OPTION_IDLE_SWEEP_INTERVAL,
    OPTION_IDLE_TIMEOUT,
    PermissionCacheStore,
    configure_permission_cache_store,
    current_permission_cache_store,
    int_option,
)
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

    **闲置注销巡检**：`setup()` 起周期任务、`aclose()` 停（装配期由 `assemble_plugins` 调用并登记
    `ResourceManager`，关闭时逆序回收）——每轮注销超过 `idle_timeout` 不活动的用户快照。
    """

    def __init__(
        self,
        *,
        profile: str = DEFAULT_PROFILE,
        ttl: int = DEFAULT_SNAPSHOT_TTL,
        exempt_role_types: ConcurrentStableList[str] = ConcurrentStableList(("system",)),  # noqa: B008
        locale: str = DEFAULT_LOCALE,
        store: PermissionCacheStore | None = None,
        idle_timeout: int = DEFAULT_IDLE_TIMEOUT,
        sweep_interval: float = DEFAULT_IDLE_SWEEP_INTERVAL,
    ) -> None:
        """初始化。

        Args:
            profile: 引擎档位（缺省 `smb`）。
            ttl: 层1 用户条目与层3 快照的有效期（秒）。
            exempt_role_types: 豁免层级判定的角色类型（缺省 `system`，即系统管理员）。
            locale: 元数据语言标识（仅影响展示名，不影响索引）。
            store: 进程内三层缓存仓（None 表示进程级单份实例）。
            idle_timeout: 活动用户闲置注销阈值（秒；<= 0 表示不注销）。
            sweep_interval: 闲置注销巡检周期（秒；<= 0 表示不起后台任务）。
        """
        self._profile = profile
        self._ttl = ttl
        self._exempt_role_types = exempt_role_types
        self._locale = locale
        self._store = store if store is not None else current_permission_cache_store()
        self._idle_timeout = idle_timeout
        self._sweep_interval = sweep_interval
        self._task: asyncio.Task[None] | None = None

    @property
    def store(self) -> PermissionCacheStore:
        """三层进程内缓存仓（排障 / 运维观测用）。

        Returns:
            PermissionCacheStore: 本校验器使用的缓存仓实例。
        """
        return self._store

    @property
    def idle_timeout(self) -> int:
        """闲置注销阈值（秒；<= 0 表示不注销）。

        Returns:
            int: 阈值秒数。
        """
        return self._idle_timeout

    @property
    def sweep_interval(self) -> float:
        """闲置注销巡检周期（秒；<= 0 表示不起后台任务）。

        Returns:
            float: 周期秒数。
        """
        return self._sweep_interval

    @property
    def sweep_task(self) -> asyncio.Task[None] | None:
        """当前巡检任务（未启用为 None；排障 / 用例断言用）。

        Returns:
            asyncio.Task[None] | None: 巡检任务。
        """
        return self._task

    async def setup(self) -> None:
        """启动闲置快照注销巡检（幂等；阈值或周期非正即不启用后台任务）。"""
        if self._task is not None or self._idle_timeout <= 0 or self._sweep_interval <= 0:
            return
        self._task = asyncio.create_task(self._sweep_forever())

    async def aclose(self) -> None:
        """停止闲置快照注销巡检（幂等）。"""
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _sweep_forever(self) -> None:
        """周期注销闲置用户快照（单轮失败只记日志，不终止巡检）。"""
        while True:
            await asyncio.sleep(self._sweep_interval)
            try:
                evicted = self._store.sweep_idle(self._idle_timeout)
            except Exception as exc:
                get_logger("bms").warning("permission_idle_sweep_failed", detail=f"{type(exc).__name__}: {exc}")
                continue
            if evicted:
                get_logger("bms").info("permission_idle_swept", users=evicted)

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
            store=self._store,
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
        store = configure_permission_cache_store(self._options, snapshot_ttl=ttl)
        idle_timeout = int_option(self._options, OPTION_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT)
        sweep_interval = int_option(self._options, OPTION_IDLE_SWEEP_INTERVAL, DEFAULT_IDLE_SWEEP_INTERVAL)
        stats = store.stats()
        get_logger("bms").info(
            "permission_cache_configured",
            snapshot_ttl=ttl,
            snapshot_max_items=stats["snapshot_max_items"],
            subject_max_items=stats["subject_max_items"],
            metadata_max_items=stats["metadata_max_items"],
            rule_max_items=stats["rule_max_items"],
            rule_max_elements=stats["rule_max_elements"],
            idle_timeout_seconds=idle_timeout,
            idle_sweep_seconds=sweep_interval,
        )
        return RbacPermissionChecker(
            profile=self._profile,
            ttl=ttl,
            exempt_role_types=exempt,  # pyright: ignore[reportArgumentType]  # 08_05：注解落集合类，值形态由契约/外部决定
            locale=locale,
            store=store,
            idle_timeout=idle_timeout,
            sweep_interval=sweep_interval,
        )


def register_rbac_permission(settings: Settings) -> None:
    """登记真实校验器工厂（基座装配期调用，**须在建注册表之前**）。

    **按注册表实例幂等**（插件注册表是进程级、且可被测试重置）：同一注册表只登记一次；
    换个注册表实例（重置 / 替换）则重新登记，避免重置后 `rbac` 丢失。

    Args:
        settings: 应用配置（读 `[permission]` 的档位与选项）。
    """
    registry = default_plugin_registry()
    # 幂等键取「注册表是否已构建」（`reset()` 后需用当前配置重新登记，见 assembly 同名说明）
    if registry.is_built:
        return
    register_plugin("permission", RBAC_PROVIDER_NAME, RbacPermissionCheckerFactory(settings))
