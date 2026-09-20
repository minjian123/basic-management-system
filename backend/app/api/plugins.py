"""插件清单只读路由：展示各能力注册实现与当前 provider（无写接口）。"""

from typing import Annotated, cast

from fastapi import Path, Request

from app.api.base import BaseRouter
from app.core.assembly import PLUGIN_WIRINGS
from app.core.exceptions import NotFoundError
from app.core.plugin import NULL_PLUGIN_NAME, PluginImpl, plugin_registry_snapshot
from app.schemas.common import ApiResponse
from app.schemas.plugin import PluginGroupResponse, PluginImplementationResponse

router = BaseRouter(key="plugins", prefix="/plugins", tags=["plugin"])

_PORT_VERSIONS: dict[str, str] = {wiring.plugin_key: wiring.port.contract_version for wiring in PLUGIN_WIRINGS}
"""登记能力 → 端口契约版本（工厂实现报端口版本）。"""


def _group(plugin_key: str, provider: str, implementations: dict[str, PluginImpl]) -> PluginGroupResponse:
    """组装单个能力分组（实现按 `plugin_name` 升序；不含密钥）。

    Args:
        plugin_key: 能力域键。
        provider: 当前选中的实现名。
        implementations: 已注册实现（`plugin_name → 实现`）。

    Returns:
        PluginGroupResponse: 分组响应。
    """
    port_version = _PORT_VERSIONS[plugin_key]
    items: list[PluginImplementationResponse] = []
    for name in sorted(implementations):
        impl = implementations[name]
        version = getattr(impl, "contract_version", None) if isinstance(impl, type) else None
        items.append(
            PluginImplementationResponse(
                plugin_name=name,
                contract_version=version if isinstance(version, str) else port_version,
                status="active" if name == provider else "registered",
            )
        )
    return PluginGroupResponse(plugin_key=plugin_key, provider=provider, implementations=items)


@router.get("")
async def list_plugins(request: Request) -> ApiResponse:
    """插件清单（按能力分组，只读）。

    Args:
        request: 请求对象。

    Returns:
        ApiResponse: 统一响应，data 为能力分组数组（`plugin_key` 升序）。
    """
    providers = cast("dict[str, str]", request.app.state.plugin_providers)
    snapshot = plugin_registry_snapshot()
    groups = [
        _group(plugin_key, providers.get(plugin_key, NULL_PLUGIN_NAME), dict(snapshot[plugin_key]))
        for plugin_key in sorted(_PORT_VERSIONS)
        if plugin_key in snapshot
    ]
    return ApiResponse.ok(groups)


@router.get("/{plugin_key}")
async def get_plugin(
    request: Request,
    plugin_key: Annotated[str, Path(description="能力域键（如 object_storage）")],
) -> ApiResponse:
    """单能力插件明细（只读）。

    Args:
        request: 请求对象。
        plugin_key: 能力域键。

    Returns:
        ApiResponse: 统一响应，data 为单能力分组。

    Raises:
        NotFoundError: 未登记能力（10002 / 404，全局处理器统一转响应）。
    """
    snapshot = plugin_registry_snapshot()
    if plugin_key not in _PORT_VERSIONS or plugin_key not in snapshot:
        raise NotFoundError(f"插件能力不存在：{plugin_key}")
    providers = cast("dict[str, str]", request.app.state.plugin_providers)
    return ApiResponse.ok(_group(plugin_key, providers.get(plugin_key, NULL_PLUGIN_NAME), dict(snapshot[plugin_key])))
