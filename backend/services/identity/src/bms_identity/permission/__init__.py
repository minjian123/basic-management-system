"""认证与身份服务：权限能力接入（`04_01` 下沉后）。

identity 的 `require_permission` 此前解析到基座 `NullPermissionChecker`（恒放行）——本模块把真实校验
接进来：

- **登记数据来源**：identity 不持有权限数据，注入「经 platform 内部只读契约取数」实现
  （`permission/source.py`）；
- **登记真实校验器**：委托基座 `register_rbac_permission`（实现随基座分发，与 platform 同源同口径）。

接入后 identity 已挂码的 5 个端点由恒放行转为真实判定：`session:query` / `session:kick` /
`open:manage` / `idp:manage` / `sso:bind`。
"""

from __future__ import annotations

from typing import cast

from fastapi import Request

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.plugin import default_plugin_registry
from bms_core.permission.rbac import register_rbac_permission
from bms_core.permission.sources import register_permission_data_source_factory
from bms_core.servicecall.base import BaseServiceClient
from bms_identity.permission.source import PlatformContractPermissionDataSource

__all__ = [
    "IDENTITY_DATA_SOURCE_KEY",
    "build_identity_source",
    "register_identity_permission",
]

IDENTITY_DATA_SOURCE_KEY = "platform_contract_permission_data_source"
"""identity 侧数据来源标识（与 `PlatformContractPermissionDataSource.key` 一致）。"""

_REGISTERED_REGISTRIES: ConcurrentStableList[object] = ConcurrentStableList()
"""已登记 identity 侧权限装配的注册表实例清单（按实例幂等；注册表重置后需重新登记）。"""


def register_identity_permission(settings: Settings) -> None:
    """登记 identity 侧权限装配（真实校验器 + 数据来源工厂）。

    幂等口径分两层：**插件注册**按注册表实例幂等（注册表构建后只读）；**数据来源登记**每次补齐
    （数据来源是模块级注册表、可被用例隔离重置，且不属于插件注册表）。

    Args:
        settings: 应用配置（读 `[permission]` 的档位与选项）。
    """
    register_permission_data_source_factory(IDENTITY_DATA_SOURCE_KEY, build_identity_source)
    registry = default_plugin_registry()
    if any(item is registry for item in _REGISTERED_REGISTRIES):
        return
    register_rbac_permission(settings)
    _REGISTERED_REGISTRIES.add(registry)


async def build_identity_source(request: Request) -> PlatformContractPermissionDataSource:
    """按当前请求构造 identity 侧数据来源（服务间客户端取自应用装配）。

    Args:
        request: 当前请求（取 `app.state.service_client`）。

    Returns:
        PlatformContractPermissionDataSource: 经契约取数的数据来源实例。
    """
    client = cast("BaseServiceClient", request.app.state.service_client)
    return PlatformContractPermissionDataSource(client)
