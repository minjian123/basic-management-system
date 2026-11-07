"""作用域资源类型运营面（07D `01_01`）：`/api/v1/scope-resource-types`（查询 / 运营期停用恢复）。

- **查询**（`GET`）：未退役的全类型清单（含已停用，运营核对与恢复用）；登录态或东西向服务身份；
- **停用 / 恢复**（`PATCH /{resource_type_key}`）：只切运营态 `admin_status`，不改声明态 `status`；
  幂等；字段级变更进审计链（操作人取登录态）；
- **鉴权**：读挂 `scope-resource:query`、写挂 `scope-resource:manage`（与能力分配授权同口径）；
- **只读派生**：`effective_status` 由「声明态 + 运营态」派生，不在库里另存一份。
"""

from typing import Annotated

from fastapi import Depends, Path

from bms_core.api.base import AuthContext, BaseRouter, require_auth_or_service
from bms_core.api.deps import get_platform_read_db, get_platform_uow
from bms_core.audit.base import AuditCapturer, get_audit_capturer
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.permission.base import require_permission
from bms_core.resource_scope import SCOPE_RESOURCE_ENABLED, ScopeResourceTypeRecord
from bms_core.schemas.common import ApiResponse
from bms_platform.domains.platform_registry.schemas.scope_resource import (
    ScopeResourceTypeResponse,
    ScopeResourceTypeStatusRequest,
)
from bms_platform.domains.platform_registry.services.scope_resource import ScopeResourceTypeService

router = BaseRouter(
    key="scope-resource-types",
    prefix="/scope-resource-types",
    tags=["scope-resource"],
    dependencies=[Depends(require_auth_or_service)],
)

ReadDbDep = Annotated[DbSession, Depends(get_platform_read_db)]
UowDep = Annotated[DbUnitOfWork, Depends(get_platform_uow)]
AuditDep = Annotated[AuditCapturer, Depends(get_audit_capturer)]
ContextDep = Annotated[AuthContext, Depends(require_auth_or_service)]
KeyPath = Annotated[str, Path(description="类型标识（{module_key}.{kind}，如 msg.topic）")]

_REQUIRE_QUERY = Depends(require_permission("scope-resource:query"))
_REQUIRE_MANAGE = Depends(require_permission("scope-resource:manage"))


@router.get("", dependencies=[_REQUIRE_QUERY])
async def list_scope_resource_types(session: ReadDbDep) -> ApiResponse:
    """作用域资源类型清单（只读，未退役全量；含已停用项）。

    需要 `scope-resource:query` 权限。

    Args:
        session: 平台库只读会话。

    Returns:
        ApiResponse: 统一响应，data 为类型记录数组。
    """
    records = await ScopeResourceTypeService(session).list_records()
    return ApiResponse.ok(ConcurrentStableList(_response(record) for record in records).to_list())


@router.patch("/{resource_type_key}", dependencies=[_REQUIRE_MANAGE])
async def set_scope_resource_type_status(
    resource_type_key: KeyPath,
    req: ScopeResourceTypeStatusRequest,
    uow: UowDep,
    audit: AuditDep,
    context: ContextDep,
) -> ApiResponse:
    """设置运营态（停用 / 恢复；只改运营态，不动产品声明）。

    需要 `scope-resource:manage` 权限；幂等（同值不写库、不记审计）；变更后重建进程内视图。

    Args:
        resource_type_key: 类型标识（`{module_key}.{kind}`）。
        req: 运营态变更请求。
        uow: 平台库工作单元（写事务边界）。
        audit: 审计捕获器。
        context: 入站身份（操作人取 `user_id`）。

    Returns:
        ApiResponse: 统一响应，data 为变更后的类型记录。

    Raises:
        ParamError: 运营态取值非法 / 类型已退役（10001）。
        NotFoundError: 类型未登记（10002）。
    """
    service = ScopeResourceTypeService(uow.session, audit=audit, uow=uow)
    record = await service.set_admin_status(resource_type_key, req.admin_status, actor=context.user_id)
    return ApiResponse.ok(_response(record))


def _response(record: ScopeResourceTypeRecord) -> ScopeResourceTypeResponse:
    """记录值对象 → 运营面响应（`effective_status` 由声明态 + 运营态派生）。

    Args:
        record: 类型记录。

    Returns:
        ScopeResourceTypeResponse: 运营面响应。
    """
    return ScopeResourceTypeResponse(
        resource_type_key=record.resource_type_key,
        name=record.name,
        name_pattern=record.name_pattern,
        max_length=record.max_length,
        retention_days=record.retention_days,
        removal_policy=record.removal_policy,
        product_key=record.product_key,
        status=record.status,
        admin_status=record.admin_status,
        effective_status=SCOPE_RESOURCE_ENABLED if record.is_active() else "disabled",
        declaration_version=record.declaration_version,
    )
