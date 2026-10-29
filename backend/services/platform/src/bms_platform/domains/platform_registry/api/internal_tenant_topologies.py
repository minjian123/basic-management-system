"""内部拓扑快照（07C `02_02`）：`/api/v1/platform/internal/tenant-topologies`（服务间读取）。

- **用途**：其它进程的第二段解析（业务域 → 部署单元与库）需要全量拓扑快照，而权威只在平台库；
  各服务在装配期拉取本端点并常驻进程内（`bms_core.collaboration.bootstrap.bootstrap_remote_topologies`）；
- **鉴权**：双模 `require_auth_or_service`——服务身份可读全量（拓扑是不含租户业务数据的全局配置，
  所有服务都需要它）；登录态需 `tenant-topology:query` 权限码（运维排障）；
- **暴露面**：只回解析必需的三列（`domain_key` / `unit_key` / `status`）+ 租户与版本；
  `note` / 审计 / 操作人等运营字段留在管理面（`/api/v1/tenant-topologies`）；
- 不是第二份事实源：只读 `TenantTopologyService.snapshot()`，不落库、不缓存。
"""

from typing import Annotated

from fastapi import Depends, Request

from bms_core.api.base import AuthContext, BaseRouter, require_auth_or_service
from bms_core.api.deps import get_platform_read_db
from bms_core.collaboration.topology import DEFAULT_TOPOLOGY_TENANT
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db.session import DbSession
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_platform.domains.platform_registry.schemas.tenant_topology import (
    TopologySnapshotItem,
    TopologySnapshotResponse,
    TopologySnapshotRow,
)
from bms_platform.domains.platform_registry.services.tenant_topology import TenantTopologyService

router = BaseRouter(
    key="platform_internal_tenant_topologies",
    prefix="/platform/internal/tenant-topologies",
    tags=["platform-internal"],
    dependencies=[Depends(require_auth_or_service)],
)

ReadDbDep = Annotated[DbSession, Depends(get_platform_read_db)]
ContextDep = Annotated[AuthContext, Depends(require_auth_or_service)]


@router.get("")
async def topology_snapshot(request: Request, session: ReadDbDep, context: ContextDep) -> ApiResponse:
    """下发拓扑全量快照（各租户当前版本 + 默认版本）。

    Args:
        request: 请求对象（登录态分支的权限码校验用）。
        session: 平台库只读会话。
        context: 入站身份（服务身份或登录态）。

    Returns:
        ApiResponse: 统一响应，data 为 `{default_version, snapshots}`。

    Raises:
        PermissionError: 登录态缺少权限码（30001 / 403）。
    """
    if context.source != "service":
        await require_permission("tenant-topology:query")(request)
    snapshots = await TenantTopologyService(session).snapshot()
    items: ConcurrentStableList[TopologySnapshotItem] = ConcurrentStableList()
    default_version = 0
    for snapshot in snapshots:
        if snapshot.tenant_id == DEFAULT_TOPOLOGY_TENANT:
            default_version = snapshot.version
        rows: ConcurrentStableList[TopologySnapshotRow] = ConcurrentStableList(
            TopologySnapshotRow(domain_key=domain, unit_key=entry.unit_key, status=entry.status)
            for domain, entry in snapshot.entries.to_list()
        )
        items.add(TopologySnapshotItem(tenant_id=snapshot.tenant_id, version=snapshot.version, rows=rows))
    return ApiResponse.ok(TopologySnapshotResponse(default_version=default_version, snapshots=items))
