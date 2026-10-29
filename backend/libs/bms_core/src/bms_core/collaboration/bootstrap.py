"""授权视图与部署拓扑的进程引导（07B `02_04` / `03_01`、07C `02_02`）。

分工：

- **平台进程**：来源是「本库直读」（平台库即授权 / 拓扑唯一权威），由平台侧启动钩子装配并直接装载
  （授权见 `capability_grant_bootstrap`，拓扑见 `bootstrap_tenant_topologies`），失败转**拒启**；
- **其它进程**：来源是远端拉取——授权走 `RemoteCapabilityGrantSource`（`/api/v1/platform/internal/capability-grants`），
  统一调 `bootstrap_remote_capability_grants()`；拓扑走 `bootstrap_remote_topologies()`
  （`/api/v1/platform/internal/tenant-topologies`），装配期拉取全量快照后登记第二段解析与承载集合。
  两者失败均**告警 + 置降级标记**（不拒启）：产品进程的管面与登录态出口不依赖这两份视图，
  平台重启窗口内把整个产品拖下水属过度耦合；「未装载」由 `app.state.*_degraded` 与启动 `WARNING`
  可观测，此时行为等同改造前。

**装配缺失仍拒启**：`app.state.service_client` 未登记属配置漂移，不给隐式降级。
"""

from typing import cast

from fastapi import FastAPI

from bms_core.collaboration.grant import (
    RemoteCapabilityGrantSource,
    ensure_grant_view,
    register_capability_grant_source,
)
from bms_core.collaboration.topology import (
    TenantTopologyResolver,
    TopologyResolverResource,
    TopologySnapshot,
    register_instance_context,
    register_topology_resolver,
    register_topology_snapshot,
    snapshots_from_payload,
)
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import CatalogError
from bms_core.core.logging import get_logger
from bms_core.db.keys import PLATFORM_SERVICE_KEY
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest
from bms_core.services.module_registry import domain_service_view

__all__ = [
    "GRANT_VIEW_DEGRADED_FLAG",
    "TOPOLOGY_DEGRADED_FLAG",
    "TOPOLOGY_SNAPSHOT_PATH",
    "bootstrap_remote_capability_grants",
    "bootstrap_remote_topologies",
    "warm_capability_grant_views",
]

GRANT_VIEW_DEGRADED_FLAG = "grant_view_degraded"
"""授权视图降级标记（`app.state` 属性名；启动预热失败时置 True，观测与排障用）。"""

TOPOLOGY_DEGRADED_FLAG = "topology_degraded"
"""部署拓扑降级标记（`app.state` 属性名；快照拉取失败 / 为空时置 True，此时沿用过渡实现）。"""

TOPOLOGY_SNAPSHOT_PATH = "/api/v1/platform/internal/tenant-topologies"
"""拓扑全量快照的内部出口路径（服务间读取，`require_auth_or_service`）。"""

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


async def bootstrap_remote_topologies(app: FastAPI) -> None:
    """装配期引导：拉取平台拓扑全量快照，登记第二段解析实现与本实例承载集合（07C `02_02`）。

    拓扑快照是「业务域 → 部署单元与库」的解析依据，只有平台进程能直读本库；其它进程经内部出口
    `GET /api/v1/platform/internal/tenant-topologies` 取全量快照常驻进程内（拓扑只在发布时变化）。

    失败语义分三类：

    - **开关关闭**（`[topology].distribute = false`，单测环境）：跳过并记 INFO，沿用 07B 过渡实现；
    - **装配缺失**（`app.state.service_client` 未登记）：抛 `CatalogError`——配置漂移，拒启；
    - **平台未就绪 / 快照为空 / 出口异常**：告警 + 置 `app.state.topology_degraded = True`，
      保留过渡实现、不拒启（行为等同改造前，不会错址）。

    `[topology].units` 内出现未登记单元时 `CatalogError` **拒启**（配置漂移，不降级）。

    Args:
        app: 应用实例（取配置 / 服务身份 / 服务间调用客户端 / 资源管理器）。

    Raises:
        CatalogError: 应用装配缺服务间调用客户端，或承载单元未在默认拓扑登记。
    """
    settings = cast("Settings", app.state.settings)
    if not settings.topology.distribute:
        _LOGGER.info("tenant_topology_distribute_skipped", reason="topology.distribute=false")
        return
    service_key = _service_key(app)
    if service_key == PLATFORM_SERVICE_KEY:
        # 平台自己就是权威：本库快照由平台启动钩子装载（`02_01`），不走 HTTP
        return
    client = cast("BaseServiceClient | None", getattr(app.state, "service_client", None))
    if client is None:
        raise CatalogError("拓扑快照分发缺少服务间调用客户端（应用装配未登记 app.state.service_client）")
    try:
        snapshots = await _fetch_topology_snapshots(client)
    except Exception as exc:
        _LOGGER.warning(
            "tenant_topology_unavailable",
            service=service_key,
            error=type(exc).__name__,
            detail=str(exc),
        )
        app.state.topology_degraded = True
        return
    if not snapshots:
        _LOGGER.warning("tenant_topology_empty", service=service_key, detail="平台尚未自举默认拓扑")
        app.state.topology_degraded = True
        return
    for snapshot in snapshots:
        register_topology_snapshot(snapshot)
    register_topology_resolver(TenantTopologyResolver())
    register_instance_context(service_key, settings.topology.units)
    app.state.resources.register(TopologyResolverResource())
    app.state.topology_degraded = False
    _LOGGER.info("tenant_topology_distributed", service=service_key, snapshots=len(snapshots))


async def _fetch_topology_snapshots(client: BaseServiceClient) -> ConcurrentStableList[TopologySnapshot]:
    """经内部出口拉取拓扑全量快照。

    Args:
        client: 服务间调用客户端。

    Returns:
        ConcurrentStableList[TopologySnapshot]: 各租户快照（含默认拓扑）。

    Raises:
        CatalogError: 出口不可达或响应非法。
    """
    response = await client.call(
        ServiceRequest(service=PLATFORM_SERVICE_KEY, method="GET", path=TOPOLOGY_SNAPSHOT_PATH)
    )
    if response.status_code != 200:
        raise CatalogError(f"拓扑快照出口不可达（HTTP {response.status_code}）：{PLATFORM_SERVICE_KEY}")
    return snapshots_from_payload(response.payload())
