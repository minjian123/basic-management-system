"""授权视图的进程引导（07B `02_04` / `03_01`）：来源登记 + 承载域视图预热。

分工：

- **平台进程**：来源是「本库直读」（平台库即授权唯一权威），由平台侧 `capability_grant_bootstrap`
  装配并直接调用本模块的 `warm_capability_grant_views()` 预热，失败转**拒启**；
- **产品进程**：来源是远端拉取（`RemoteCapabilityGrantSource`，经平台内部出口
  `/api/v1/internal/capability-grants`），统一调 `bootstrap_remote_capability_grants()`——
  登记来源 + 预热**本服务承载域**的 `provider` 视图，失败**告警 + 置降级标记**（不拒启），
  被收编端点首访时仍 fail-closed（`CatalogError`，不留越权口子）。

为什么产品侧不拒启：产品进程的管面与登录态出口不依赖授权面，平台重启窗口内把整个产品拖下水属过度耦合；
「未预热」由 `app.state.grant_view_degraded` 与启动 WARNING 可观测，与 `02_06` 目录快照降级同口径。
"""

from typing import cast

from fastapi import FastAPI

from bms_core.collaboration.grant import (
    RemoteCapabilityGrantSource,
    ensure_grant_view,
    register_capability_grant_source,
)
from bms_core.core.config import Settings
from bms_core.core.exceptions import CatalogError
from bms_core.core.logging import get_logger
from bms_core.servicecall.base import BaseServiceClient
from bms_core.services.module_registry import domain_service_view

__all__ = [
    "GRANT_VIEW_DEGRADED_FLAG",
    "bootstrap_remote_capability_grants",
    "warm_capability_grant_views",
]

GRANT_VIEW_DEGRADED_FLAG = "grant_view_degraded"
"""授权视图降级标记（`app.state` 属性名；启动预热失败时置 True，观测与排障用）。"""

_LOGGER = get_logger("bms_core.collaboration.bootstrap")


async def warm_capability_grant_views(service_key: str, *, consumer: bool = True) -> None:
    """预热本服务承载域与服务自身的授权视图（首访不依赖惰性加载）。

    Args:
        service_key: 本服务标识（`[app].service`；空表示只按承载域预热）。
        consumer: 是否并预热「本服务作为消费方」的视图（产品进程只用 `provider` 维，传 False）。

    Raises:
        CatalogError: 来源未登记或加载失败（由调用方决定拒启或降级）。
    """
    for domain, carrier in domain_service_view().items():
        if carrier == service_key:
            await ensure_grant_view(provider=domain)
    if consumer and service_key:
        await ensure_grant_view(consumer=service_key)


async def bootstrap_remote_capability_grants(app: FastAPI) -> None:
    """产品进程引导：登记远端授权视图来源并预热本服务承载域视图。

    失败语义分两类：

    - **装配缺失**（`app.state.service_client` 未登记）：抛 `CatalogError`——属配置漂移，拒启；
    - **来源不可达**（平台未就绪 / 出口异常）：告警 + 置 `app.state.grant_view_degraded = True`，
      不拒启；被收编端点首访时 `ensure_grant_view` 仍抛 `CatalogError`（fail-closed）。

    签名与 `StartupHook` 同口径（`Awaitable[None]`）：产品侧可直接登记为启动钩子，无需包一层；
    预热结果经 `app.state.grant_view_degraded` 观测。

    Args:
        app: 应用实例（取配置 / 服务身份 / 服务间调用客户端）。

    Raises:
        CatalogError: 应用装配缺服务间调用客户端（配置漂移）。
    """
    client = cast("BaseServiceClient | None", getattr(app.state, "service_client", None))
    if client is None:
        raise CatalogError("授权视图远端来源缺少服务间调用客户端（应用装配未登记 app.state.service_client）")
    service_key = _service_key(app)
    register_capability_grant_source(RemoteCapabilityGrantSource(client))
    try:
        await warm_capability_grant_views(service_key, consumer=False)
    except Exception as exc:
        _LOGGER.warning(
            "capability_grant_view_unavailable",
            service=service_key,
            error=type(exc).__name__,
            detail=str(exc),
        )
        app.state.grant_view_degraded = True
        return
    app.state.grant_view_degraded = False


def _service_key(app: FastAPI) -> str:
    """取本服务标识（装配期已把解析结果回写进 `[app].service`）。

    Args:
        app: 应用实例。

    Returns:
        str: 服务标识（配置缺失时为空串，此时只按承载域预热）。
    """
    return cast("Settings", app.state.settings).app.service
