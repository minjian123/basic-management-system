"""平台服务：真实权限校验器装配（`[permission].provider = "rbac"`）。

**实现已下沉共享基座**（`bms_core.permission.rbac.RbacPermissionChecker`，任务 `04_01`）——本模块只剩
平台侧的三件装配事：

1. **登记数据来源**：平台是权限数据所有者，注入「直查本库」实现（`permission/source.py`）——
   会话与缓存是请求级资源，故以**请求级工厂**形态登记（基座校验器 `aprepare` 时回调）；
2. **登记字段权限 provider 工厂**：字段收窄项在租户库、字段键在平台库，两库合流需要请求级会话，
   故仍以工厂形态登记（接缝 `bms_core.permission.field`）；
3. **登记真实校验器**：委托基座 `register_rbac_permission`。

校验器本体、请求级预加载与判定口径均在基座；identity 等其余服务复用同一实现，只换数据来源。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from fastapi import Request

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.plugin import default_plugin_registry
from bms_core.db.registry import EngineRegistry
from bms_core.permission.field import register_field_permission_provider_factory
from bms_core.permission.rbac import (
    RBAC_PROVIDER_NAME,
    RbacPermissionChecker,
    register_rbac_permission,
)
from bms_core.permission.sources import register_permission_data_source_factory
from bms_core.servicecall.base import BaseServiceClient
from bms_platform.domains.permission_meta.permission.source import DEFAULT_METADATA_TTL, PlatformPermissionDataSource
from bms_platform.domains.role.public import (
    DEFAULT_FIELD_PERMISSION_PROVIDER_KEY,
    DirectRoleResolver,
    OrgRoleResolver,
    UserRoleRepository,
    build_static_field_provider,
)

__all__ = [
    "RBAC_PROVIDER_NAME",
    "RbacPermissionChecker",
    "build_platform_source",
    "register_platform_permission",
]

PLATFORM_DATA_SOURCE_KEY = "platform_permission_data_source"
"""平台侧数据来源标识（与 `PlatformPermissionDataSource.key` 一致）。"""

_REGISTERED_REGISTRIES: ConcurrentStableList[object] = ConcurrentStableList()
"""已登记平台侧权限装配的注册表实例清单（按实例幂等；注册表重置后需重新登记）。"""


def register_platform_permission(settings: Settings) -> None:
    """登记平台侧权限装配（真实校验器 + 数据来源工厂 + 字段权限 provider 工厂）。

    幂等口径分两层：**插件注册**按注册表实例幂等（注册表构建后只读）；**数据来源 / 字段权限工厂**
    每次补齐（两者是模块级注册表、可被用例隔离重置，且不属于插件注册表）。

    Args:
        settings: 应用配置（读 `[permission]` 的档位与选项）。
    """
    register_field_permission_provider_factory(DEFAULT_FIELD_PERMISSION_PROVIDER_KEY, build_static_field_provider)
    register_permission_data_source_factory(PLATFORM_DATA_SOURCE_KEY, build_platform_source)
    registry = default_plugin_registry()
    if any(item is registry for item in _REGISTERED_REGISTRIES):
        return
    register_rbac_permission(settings)
    _REGISTERED_REGISTRIES.add(registry)


async def build_platform_source(request: Request) -> PlatformPermissionDataSource:
    """按当前请求构造平台侧数据来源（基座校验器 `aprepare` 经注册的工厂回调本函数）。

    Args:
        request: 当前请求（取引擎注册表 / 缓存 / 服务客户端 / 权限选项）。

    Returns:
        PlatformPermissionDataSource: 直查本库的数据来源实例。
    """
    settings: Any = request.app.state.settings
    registry = cast("EngineRegistry", request.app.state.engine_registry)
    cache = cast("CacheRegion", request.app.state.cache)
    service_client = cast("BaseServiceClient", request.app.state.service_client)
    ttl = DEFAULT_METADATA_TTL
    require_org = False
    # `options` 是基座契约集合 `ConcurrentStableDict`（非内建 dict），按 Mapping 读取
    raw_options: object = settings.permission.options
    if isinstance(raw_options, Mapping):
        options = cast("Mapping[str, object]", raw_options)
        raw_ttl = options.get("snapshot_ttl_seconds")
        if isinstance(raw_ttl, int) and not isinstance(raw_ttl, bool):
            ttl = raw_ttl
        require_org = bool(options.get("require_org_roles", False))
    return PlatformPermissionDataSource(
        registry=registry,
        cache=cache,
        resolvers_factory=lambda session: (
            DirectRoleResolver(UserRoleRepository(session)),
            OrgRoleResolver(service_client, require_roles=require_org),
        ),
        field_provider_factory=build_static_field_provider,
        ttl=ttl,
    )
