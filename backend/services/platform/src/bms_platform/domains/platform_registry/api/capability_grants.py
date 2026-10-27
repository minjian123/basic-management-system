"""能力分配授权管理面（07B `02_04`）：`/api/v1/capability-grants`（查询 / 授予 / 撤销）。

- **权威**：分配记录是平台对「能力 × 消费方」的授权，`sys_capability_grant` 为唯一权威（平台库）；
- **两个来源**：产品声明的默认消费方在装载期落库（`source=declared`），本端点的人工授予 / 撤销为
  `source=manual` 覆盖，声明装载不再改动人工介入过的记录；
- **撤销不删行**：`DELETE` 为软撤销（`status=disabled` + `revoked_at`），保留授权历史；
- **鉴权**：模块级 `require_auth`；读挂 `capability-grant:query`、写挂 `capability-grant:manage`；
- **审计**：授予 / 撤销经 `AuditCapturer.capture` 留痕（当前为占位实现，真实落库归 29-审计合规）；
- **派生**：变更后清授权视图快照并刷新有效授权数指标（撤销在 TTL 内有界生效）。
"""

from typing import Annotated

from fastapi import Depends, Path, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import get_platform_read_db, get_platform_uow
from bms_core.audit.base import AuditCapturer, get_audit_capturer
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.metrics.base import BaseMetrics, get_metrics
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery, BasePageResponse
from bms_platform.domains.platform_registry.schemas.capability_grant import (
    CapabilityGrantCreateRequest,
    CapabilityGrantResponse,
)
from bms_platform.domains.platform_registry.services.capability_grant import CapabilityGrantService

router = BaseRouter(
    key="capability-grants",
    prefix="/capability-grants",
    tags=["capability-grant"],
    dependencies=[Depends(require_auth)],
)

ReadDbDep = Annotated[DbSession, Depends(get_platform_read_db)]
UowDep = Annotated[DbUnitOfWork, Depends(get_platform_uow)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
AuditDep = Annotated[AuditCapturer, Depends(get_audit_capturer)]
MetricsDep = Annotated[BaseMetrics, Depends(get_metrics)]
CapabilityQuery = Annotated[str | None, Query(description="能力名筛选；缺省全部")]
ConsumerQuery = Annotated[str | None, Query(description="消费方标识筛选；缺省全部")]
StatusQuery = Annotated[str | None, Query(description="状态筛选（enabled / disabled）；缺省全部")]
SourceQuery = Annotated[str | None, Query(description="来源筛选（declared / manual）；缺省全部")]
GrantIdPath = Annotated[int, Path(description="授权记录主键（雪花 ID）")]

_REQUIRE_QUERY = Depends(require_permission("capability-grant:query"))
_REQUIRE_MANAGE = Depends(require_permission("capability-grant:manage"))


@router.get("", dependencies=[_REQUIRE_QUERY])
async def list_capability_grants(
    session: ReadDbDep,
    query: PageDep,
    audit: AuditDep,
    capability_name: CapabilityQuery = None,
    consumer_key: ConsumerQuery = None,
    status: StatusQuery = None,
    source: SourceQuery = None,
) -> ApiResponse:
    """授权记录清单（只读，分页 + 筛选）。

    需要 `capability-grant:query` 权限；只读会话取平台库（授权记录跨租户共享）。

    Args:
        session: 平台库只读会话。
        query: 分页与排序请求（排序白名单校验、非法忽略）。
        audit: 审计捕获器（占位注入；只读端点不产生审计事件）。
        capability_name: 能力名筛选。
        consumer_key: 消费方筛选。
        status: 状态筛选。
        source: 来源筛选。

    Returns:
        ApiResponse: 统一响应，data 为分页结构 `{list, total, page, size}`。
    """
    rows, total = await CapabilityGrantService(session, audit=audit).page(
        query,
        capability_name=capability_name,
        consumer_key=consumer_key,
        status=status,
        source=source,
    )
    page = BasePageResponse[CapabilityGrantResponse](
        list=ConcurrentStableList(CapabilityGrantResponse.model_validate(row) for row in rows),
        total=total,
        page=query.page,
        size=query.size,
    )
    return ApiResponse.ok(page)


@router.post("", dependencies=[_REQUIRE_MANAGE])
async def grant_capability(
    req: CapabilityGrantCreateRequest,
    uow: UowDep,
    audit: AuditDep,
    metrics: MetricsDep,
) -> ApiResponse:
    """人工授予（同一「能力 × 消费方」幂等 UPSERT；临时授权必填有效期与理由）。

    需要 `capability-grant:manage` 权限；授予后清授权视图快照，撤销 / 授予在有界周期内生效。

    Args:
        req: 授予请求（能力名 / 消费方 / 可选有效期与理由）。
        uow: 平台库工作单元（写事务边界）。
        audit: 审计捕获器。
        metrics: 指标器（刷新有效授权数）。

    Returns:
        ApiResponse: 统一响应，data 为授权记录。

    Raises:
        ParamError: 能力未登记 / 消费方未登记 / 有效期非法 / 临时授权缺理由（10001）。
    """
    service = CapabilityGrantService(uow.session, audit=audit, metrics=metrics, uow=uow)
    row = await service.grant(
        capability_name=req.capability_name,
        consumer_key=req.consumer_key,
        expire_at=req.expire_at,
        note=req.note,
    )
    return ApiResponse.ok(CapabilityGrantResponse.model_validate(row))


@router.delete("/{grant_id}", dependencies=[_REQUIRE_MANAGE])
async def revoke_capability(
    grant_id: GrantIdPath,
    uow: UowDep,
    audit: AuditDep,
    metrics: MetricsDep,
) -> ApiResponse:
    """撤销授权（软撤销：置 `disabled` + `revoked_at`，保留授权历史；重复撤销幂等）。

    需要 `capability-grant:manage` 权限。

    Args:
        grant_id: 授权记录主键。
        uow: 平台库工作单元（写事务边界）。
        audit: 审计捕获器。
        metrics: 指标器（刷新有效授权数）。

    Returns:
        ApiResponse: 统一响应，data 为撤销后的授权记录。

    Raises:
        NotFoundError: 记录不存在（10002）。
    """
    service = CapabilityGrantService(uow.session, audit=audit, metrics=metrics, uow=uow)
    row = await service.revoke(grant_id)
    return ApiResponse.ok(CapabilityGrantResponse.model_validate(row))
