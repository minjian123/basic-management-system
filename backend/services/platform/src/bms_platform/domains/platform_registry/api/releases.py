"""发布清单管理面（07C `04_01`）：`/api/v1/releases`（最近发布 / 分页 / 明细）。

- **只读**：发布与回滚是部署编排动作（`ops.release`），管理面不放写入口——避免出现「网页点一下发布」这种
  绕过校验链的路径；
- **用途**：回答「这个单元跑的是哪一版」——按单元查最近 N 次发布与逐域明细；
- **鉴权**：模块级 `require_auth`；读挂 `release-manifest:query`；
- **不下发前端**：本端点是运维面，前端不需要知道发布批次与结构 revision。
"""

from typing import Annotated

from fastapi import Depends, Path, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import get_platform_read_db
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db.session import DbSession
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery, BasePageResponse
from bms_platform.domains.platform_registry.dto import ReleaseDomainEntry, ReleaseManifestSnapshot
from bms_platform.domains.platform_registry.schemas.release import (
    ReleaseDomainEntryResponse,
    ReleaseManifestListResponse,
    ReleaseManifestResponse,
)
from bms_platform.domains.platform_registry.services.release import ReleaseService

router = BaseRouter(
    key="releases",
    prefix="/releases",
    tags=["release"],
    dependencies=[Depends(require_auth)],
)

ReadDbDep = Annotated[DbSession, Depends(get_platform_read_db)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
UnitQuery = Annotated[str | None, Query(description="部署单元筛选；缺省全部")]
ScopeQuery = Annotated[int | None, Query(description="作用范围筛选（0 = 全局）；缺省全部")]
StatusQuery = Annotated[str | None, Query(description="状态筛选（released / rolled_back / failed）；缺省全部")]
LimitQuery = Annotated[int, Query(ge=1, le=50, description="返回条数上限")]
ManifestIdPath = Annotated[int, Path(description="发布清单主键")]

_REQUIRE_QUERY = Depends(require_permission("release-manifest:query"))


def _entry(row: ReleaseDomainEntry) -> ReleaseDomainEntryResponse:
    """把域明细 DTO 转为响应模型。

    Args:
        row: 域明细 DTO。

    Returns:
        ReleaseDomainEntryResponse: 响应模型。
    """
    return ReleaseDomainEntryResponse(
        domain_key=row.domain_key,
        service_key=row.service_key,
        service_version=row.service_version,
        contract_version=row.contract_version,
        schema_revision=row.schema_revision,
        note=row.note,
    )


def _manifest(row: ReleaseManifestSnapshot) -> ReleaseManifestResponse:
    """把发布快照 DTO 转为响应模型。

    Args:
        row: 发布快照。

    Returns:
        ReleaseManifestResponse: 响应模型。
    """
    return ReleaseManifestResponse(
        id=row.id,
        unit_key=row.unit_key,
        tenant_scope=row.tenant_scope,
        manifest_version=row.manifest_version,
        topology_version=row.topology_version,
        status=row.status,
        released_at=row.released_at,
        rolled_back_from=row.rolled_back_from,
        note=row.note,
        domains=ConcurrentStableList(_entry(entry) for entry in row.domains),
    )


@router.get("", dependencies=[_REQUIRE_QUERY])
async def list_releases(
    session: ReadDbDep,
    query: PageDep,
    unit_key: UnitQuery = None,
    tenant_scope: ScopeQuery = None,
    status: StatusQuery = None,
) -> ApiResponse:
    """发布记录清单（只读，分页 + 筛选）。

    需要 `release-manifest:query` 权限；列表不取逐域明细（明细走单条查询），避免大结果集放大。

    Args:
        session: 平台库只读会话。
        query: 分页与排序请求（排序白名单校验、非法忽略）。
        unit_key: 部署单元筛选。
        tenant_scope: 作用范围筛选。
        status: 状态筛选。

    Returns:
        ApiResponse: 统一响应，data 为分页结构 `{list, total, page, size}`。
    """
    rows, total = await ReleaseService(session).page(query, unit_key=unit_key, tenant_scope=tenant_scope, status=status)
    page = BasePageResponse[ReleaseManifestResponse](
        list=ConcurrentStableList(_manifest(row) for row in rows),
        total=total,
        page=query.page,
        size=query.size,
    )
    return ApiResponse.ok(page)


@router.get("/recent", dependencies=[_REQUIRE_QUERY])
async def recent_releases(
    session: ReadDbDep,
    unit_key: Annotated[str, Query(description="部署单元标识")],
    tenant_scope: Annotated[int, Query(description="作用范围（0 = 全局）")] = 0,
    limit: LimitQuery = 10,
) -> ApiResponse:
    """按单元查最近若干次发布（含逐域明细）。

    需要 `release-manifest:query` 权限；「这个单元跑的是哪一版」直接看首条。

    Args:
        session: 平台库只读会话。
        unit_key: 部署单元标识。
        tenant_scope: 作用范围（`0` = 全局）。
        limit: 返回条数上限。

    Returns:
        ApiResponse: 统一响应，data 为发布快照数组（批次号降序）。
    """
    rows = await ReleaseService(session).recent(unit_key, tenant_scope, limit=limit)
    payload = ReleaseManifestListResponse(
        items=ConcurrentStableList(_manifest(row) for row in rows),
    )
    return ApiResponse.ok(payload)


@router.get("/{manifest_id}", dependencies=[_REQUIRE_QUERY])
async def get_release(manifest_id: ManifestIdPath, session: ReadDbDep) -> ApiResponse:
    """按主键取一次发布（含逐域明细）。

    需要 `release-manifest:query` 权限。

    Args:
        manifest_id: 发布清单主键。
        session: 平台库只读会话。

    Returns:
        ApiResponse: 统一响应，data 为发布快照。

    Raises:
        NotFoundError: 发布清单不存在（10002）。
    """
    return ApiResponse.ok(_manifest(await ReleaseService(session).get(manifest_id)))
