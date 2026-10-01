"""租户注册只读契约：`GET /api/v1/tenant-registry?code=…`（或 `?domain=…`）。

- 提供方：租户与配置服务（`sys_tenant` 所有权方）；消费方：全部服务的租户解析（缓存未命中回源）。
- 语义：未知租户 → `TenantNotFoundError`（404 / 80001）；停用 → `TenantSuspendedError`（403 / 80002）；
  正常 → 统一响应包裹的注册快照（编码 / 名称 / 域名 / 状态 / 到期）。
- 取数走平台服务库只读会话（`get_platform_read_db`）；本接口为**内部契约**，真实鉴权随 07_03；
- `db_basis` 经对照表 `sys_tenant_database` 取数；缺对照行回落当前 `code` 并记 WARNING。
"""

from typing import Annotated

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter
from bms_core.api.deps import get_platform_read_db
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import ParamError, TenantNotFoundError, TenantSuspendedError
from bms_core.core.logging import get_logger
from bms_core.db.session import DbSession
from bms_core.schemas.common import ApiResponse
from bms_tenant.models.tenant import SysTenant
from bms_tenant.repositories.tenant_registry import TenantRegistryRepository

router = BaseRouter(key="tenant_registry", prefix="/tenant-registry", tags=["tenant"])

_LOGGER = get_logger("bms.tenant_registry")

SessionDep = Annotated[DbSession, Depends(get_platform_read_db)]
CodeQuery = Annotated[str | None, Query(description="租户编码（与 domain / tenant_id 三选一）")]
DomainQuery = Annotated[str | None, Query(description="子域名（与 code / tenant_id 三选一）")]
TenantIdQuery = Annotated[str | None, Query(description="租户主键雪花 id 字符串（与 code / domain 三选一）")]

_ACTIVE_STATUS = "active"


@router.get("")
async def get_tenant_registry(
    session: SessionDep,
    code: CodeQuery = None,
    domain: DomainQuery = None,
    tenant_id: TenantIdQuery = None,
) -> ApiResponse:
    """取租户注册快照（按编码 / 域名 / 主键三选一）。

    Args:
        session: 平台服务库只读会话。
        code: 租户编码。
        domain: 子域名。
        tenant_id: 租户主键雪花 id 字符串。

    Returns:
        ApiResponse: 统一响应（data 为注册快照）。

    Raises:
        ParamError: 未提供或多于一个来源（10001）。
        TenantNotFoundError: 未知租户（404 / 80001）。
        TenantSuspendedError: 租户已停用（403 / 80002）。
    """
    provided = [value for value in (code, domain, tenant_id) if value]
    if len(provided) != 1:
        raise ParamError("租户注册查询需且仅需提供 code / domain / tenant_id 之一")
    repository = TenantRegistryRepository(session)
    if code:
        row = await repository.by_code(code)
    elif domain:
        row = await repository.by_domain(domain)
    else:
        if not str(tenant_id).isdigit():
            raise ParamError("tenant_id 须为雪花 id 十进制字符串")
        row = await repository.by_id(int(str(tenant_id)))
    if row is None:
        raise TenantNotFoundError(f"未知租户：{code or domain or tenant_id}")
    if row.status != _ACTIVE_STATUS:
        raise TenantSuspendedError(f"租户已停用：{row.code}")
    db_basis = await repository.db_basis(int(row.id))
    if not db_basis:
        _LOGGER.warning("tenant_db_basis_missing", tenant_id=int(row.id), code=row.code)
    return ApiResponse.ok(dict(_snapshot(row, db_basis)))


def _snapshot(row: SysTenant, db_basis: str | None = None) -> ConcurrentStableDict[str, object]:
    """注册行 → 契约响应载荷。

    Args:
        row: 注册行。
        db_basis: 库名基（对照表）；缺行回落当前 `code`。

    Returns:
        ConcurrentStableDict[str, object]: 载荷（编码 / 名称 / 域名 / 状态 / 到期 / 主键 / 库名基）。
    """
    return ConcurrentStableDict(
        {
            "code": row.code,
            "name": row.name,
            "domain": row.domain,
            "status": row.status,
            "expire_at": row.expire_at.isoformat() if row.expire_at else None,
            "tenant_id": row.id,
            "db_basis": db_basis or row.code,
        }
    )
