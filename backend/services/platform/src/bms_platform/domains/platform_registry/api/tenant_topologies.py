"""租户部署拓扑管理面（07C `02_01`）：`/api/v1/tenant-topologies`（分页 / 导出 / 整批写入）。

- **权威**：`sys_tenant_topology` 是「某租户的某业务域由哪个部署单元承载」的唯一权威（平台库）；
- **整批写入**：`PUT` 在一个事务内替换该租户当前版本（软删旧行 + 插新行 + 版本递增），写入即生效；
- **鉴权**：模块级 `require_auth`；读挂 `tenant-topology:query`、写挂 `tenant-topology:manage`；
- **审计**：整批替换经 `AuditCapturer.capture` 留痕（租户 / 版本 / 域数），不逐行记；
- **不下发前端**：本端点是运维与部署编排面，前端不需要知道部署单元。
"""

from typing import Annotated

from fastapi import Depends, Path, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import get_platform_read_db, get_platform_uow
from bms_core.audit.base import AuditCapturer, get_audit_capturer
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery, BasePageResponse
from bms_platform.domains.platform_registry.schemas.tenant_topology import (
    TenantTopologyExportResponse,
    TenantTopologyRowRequest,
    TenantTopologyRowResponse,
    TenantTopologyWriteRequest,
)
from bms_platform.domains.platform_registry.services.tenant_topology import (
    TenantTopologyService,
    TopologyRow,
)

router = BaseRouter(
    key="tenant-topologies",
    prefix="/tenant-topologies",
    tags=["tenant-topology"],
    dependencies=[Depends(require_auth)],
)

ReadDbDep = Annotated[DbSession, Depends(get_platform_read_db)]
UowDep = Annotated[DbUnitOfWork, Depends(get_platform_uow)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
AuditDep = Annotated[AuditCapturer, Depends(get_audit_capturer)]
TenantIdPath = Annotated[int, Path(description="租户主键（0 = 平台级默认拓扑）")]
TenantQuery = Annotated[int | None, Query(description="租户筛选；缺省全部")]
DomainQuery = Annotated[str | None, Query(description="业务域筛选；缺省全部")]
UnitQuery = Annotated[str | None, Query(description="部署单元筛选；缺省全部")]

_REQUIRE_QUERY = Depends(require_permission("tenant-topology:query"))
_REQUIRE_MANAGE = Depends(require_permission("tenant-topology:manage"))


@router.get("", dependencies=[_REQUIRE_QUERY])
async def list_topologies(
    session: ReadDbDep,
    query: PageDep,
    tenant_id: TenantQuery = None,
    domain_key: DomainQuery = None,
    unit_key: UnitQuery = None,
) -> ApiResponse:
    """拓扑记录清单（只读，分页 + 筛选）。

    需要 `tenant-topology:query` 权限；只读会话取平台库（拓扑跨租户共享）。

    Args:
        session: 平台库只读会话。
        query: 分页与排序请求（排序白名单校验、非法忽略）。
        tenant_id: 租户筛选。
        domain_key: 业务域筛选。
        unit_key: 部署单元筛选。

    Returns:
        ApiResponse: 统一响应，data 为分页结构 `{list, total, page, size}`。
    """
    rows, total = await TenantTopologyService(session).page(
        query, tenant_id=tenant_id, domain_key=domain_key, unit_key=unit_key
    )
    page = BasePageResponse[TenantTopologyRowResponse](
        list=ConcurrentStableList(TenantTopologyRowResponse.model_validate(row) for row in rows),
        total=total,
        page=query.page,
        size=query.size,
    )
    return ApiResponse.ok(page)


@router.get("/{tenant_id}", dependencies=[_REQUIRE_QUERY])
async def export_topology(tenant_id: TenantIdPath, session: ReadDbDep) -> ApiResponse:
    """按租户导出当前版本（部署编排 / 迁移输入）。

    需要 `tenant-topology:query` 权限；该租户无记录时回退默认拓扑（`tenant_id=0`）。

    Args:
        tenant_id: 租户主键（0 = 默认拓扑）。
        session: 平台库只读会话。

    Returns:
        ApiResponse: 统一响应，data 为 `{tenant_id, version, rows}`。

    Raises:
        NotFoundError: 该租户与默认拓扑都没有记录（10002）。
    """
    version, rows = await TenantTopologyService(session).export(tenant_id)
    payload = TenantTopologyExportResponse(
        tenant_id=tenant_id,
        version=version,
        rows=ConcurrentStableList(TenantTopologyRowResponse.model_validate(row) for row in rows),
    )
    return ApiResponse.ok(payload)


@router.put("/{tenant_id}", dependencies=[_REQUIRE_MANAGE])
async def replace_topology(
    tenant_id: TenantIdPath,
    req: TenantTopologyWriteRequest,
    uow: UowDep,
    audit: AuditDep,
) -> ApiResponse:
    """整批替换某租户的拓扑（`rows` 或 `template` 二选一；写入即生效）。

    需要 `tenant-topology:manage` 权限。整批替换语义：旧行软删除、新行同版本写入、版本递增；
    失败即整体回滚（不会出现半新半旧的中间态）。

    Args:
        tenant_id: 租户主键（0 = 默认拓扑）。
        req: 写入请求。
        uow: 平台库工作单元（写事务边界）。
        audit: 审计捕获器。

    Returns:
        ApiResponse: 统一响应，data 为生效后的 `{tenant_id, version, rows}`。

    Raises:
        ParamError: 参数非法 / 域未登记 / 单元命名非法 / 未知模板 / 默认拓扑缺域（10001）。
        ConflictError: 同域重复或版本回退（10003）。
    """
    service = TenantTopologyService(uow.session, audit=audit)
    version, rows = await service.replace(
        tenant_id,
        rows=_rows_of(req.rows),
        template=req.template,
        version=req.version,
        note=req.note,
    )
    await uow.commit()
    payload = TenantTopologyExportResponse(
        tenant_id=tenant_id,
        version=version,
        rows=ConcurrentStableList(TenantTopologyRowResponse.model_validate(row) for row in rows),
    )
    return ApiResponse.ok(payload)


def _rows_of(rows: ConcurrentStableList[TenantTopologyRowRequest] | None) -> ConcurrentStableList[TopologyRow] | None:
    """把请求行转为服务层待写入行（None 透传，供「rows / template 二选一」判定）。

    Args:
        rows: 请求行（可空）。

    Returns:
        ConcurrentStableList[TopologyRow] | None: 服务层行；请求未给行时为 None。
    """
    if rows is None:
        return None
    return ConcurrentStableList(
        TopologyRow(domain_key=row.domain_key, unit_key=row.unit_key, status=row.status, note=row.note) for row in rows
    )
