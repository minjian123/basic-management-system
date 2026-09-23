"""租户注册只读契约：`GET /api/v1/tenant-registry?code=…`（或 `?domain=…`）。

- 提供方：租户与配置服务（`sys_tenant` 所有权方）；消费方：全部服务的租户解析（缓存未命中回源）。
- 语义：未知租户 → `TenantNotFoundError`（404 / 80001）；停用 → `TenantSuspendedError`（403 / 80002）；
  正常 → 统一响应包裹的注册快照（编码 / 名称 / 域名 / 状态 / 到期）。
- 取数走平台服务库只读会话（`get_platform_read_db`）；本接口为**内部契约**，真实鉴权随 07_03。
"""

from typing import Annotated

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter
from bms_core.api.deps import get_platform_read_db
from bms_core.core.exceptions import ParamError, TenantNotFoundError, TenantSuspendedError
from bms_core.db.session import DbSession
from bms_core.schemas.common import ApiResponse
from bms_tenant.models.tenant import SysTenant
from bms_tenant.repositories.tenant_registry import TenantRegistryRepository

router = BaseRouter(key="tenant_registry", prefix="/tenant-registry", tags=["tenant"])

SessionDep = Annotated[DbSession, Depends(get_platform_read_db)]
CodeQuery = Annotated[str | None, Query(description="租户编码（与 domain 二选一）")]
DomainQuery = Annotated[str | None, Query(description="子域名（与 code 二选一）")]

_ACTIVE_STATUS = "active"


@router.get("")
async def get_tenant_registry(
    session: SessionDep,
    code: CodeQuery = None,
    domain: DomainQuery = None,
) -> ApiResponse:
    """取租户注册快照（按编码或域名二选一）。

    Args:
        session: 平台服务库只读会话。
        code: 租户编码。
        domain: 子域名。

    Returns:
        ApiResponse: 统一响应（data 为注册快照）。

    Raises:
        ParamError: 未提供 code / domain（10001）。
        TenantNotFoundError: 未知租户（404 / 80001）。
        TenantSuspendedError: 租户已停用（403 / 80002）。
    """
    if bool(code) == bool(domain):
        raise ParamError("租户注册查询需且仅需提供 code 或 domain 之一")
    repository = TenantRegistryRepository(session)
    row = await repository.by_code(code) if code else await repository.by_domain(domain or "")
    if row is None:
        raise TenantNotFoundError(f"未知租户：{code or domain}")
    if row.status != _ACTIVE_STATUS:
        raise TenantSuspendedError(f"租户已停用：{row.code}")
    return ApiResponse.ok(_snapshot(row))


def _snapshot(row: SysTenant) -> dict[str, object]:
    """注册行 → 契约响应载荷。

    Args:
        row: 注册行。

    Returns:
        dict[str, object]: 载荷（编码 / 名称 / 域名 / 状态 / 到期 / 主键）。
    """
    return {
        "code": row.code,
        "name": row.name,
        "domain": row.domain,
        "status": row.status,
        "expire_at": row.expire_at.isoformat() if row.expire_at else None,
        "tenant_id": row.id,
    }
