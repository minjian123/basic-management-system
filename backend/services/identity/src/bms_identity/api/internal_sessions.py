"""认证与身份服务内部端点：按用户撤销全部会话（服务间调用，不经网关）。

- **鉴权**：`require_service("platform")`——仅接受签发方为 **platform 服务**的有效服务 JWT
  （`aud=service`）；用户票据与网关服务票据（`sub=gateway`）一律拒；
- **租户**：由服务 JWT 的 `tenant` claim 经全局租户中间件解析租户库（同 `platform` 内部端点口径）；
- **复用**：`SessionService.revoke_user_sessions`（阶段六已交付的会话撤销原语：`revoked_at` 落库 +
  refresh 黑名单 + Redis 会话标记删除 + 广播占位），本端点不改其语义；
- **消费方**：platform 用户管理（停用 / 删除 / 重置密码的**即时失效会话**，见阶段七 `02_01` 详细设计）；
- **契约**：计入 identity 公开契约（`deploy/contracts/identity.json`）。
"""

from typing import Annotated

from fastapi import Depends, Request

from bms_core.api.base import BaseRouter, require_service
from bms_core.api.deps import (
    get_realtime_publisher,
    get_session_security,
    get_session_store,
    get_tenant,
)
from bms_core.core.exceptions import AuthError
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import session_scope
from bms_core.db.tenant import TenantContext
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.schemas.common import ApiResponse
from bms_core.security.base import BaseSessionSecurity
from bms_core.session.base import BaseSessionStore
from bms_core.ws.base import BaseRealtimePublisher
from bms_identity.schemas.session import RevokeUserSessionsRequest, RevokeUserSessionsResult
from bms_identity.services.session import SessionService

PLATFORM_SERVICE = "platform"
"""允许调用本内部端点的调用方服务标识（平台服务）。"""

router = BaseRouter(
    key="identity_internal_sessions",
    prefix="/identity/internal/sessions",
    tags=["identity-internal"],
    dependencies=[Depends(require_service(PLATFORM_SERVICE))],
)

SecurityDep = Annotated[BaseSessionSecurity, Depends(get_session_security)]
StoreDep = Annotated[BaseSessionStore, Depends(get_session_store)]
PublisherDep = Annotated[BaseRealtimePublisher, Depends(get_realtime_publisher)]
TenantDep = Annotated[TenantContext | None, Depends(get_tenant)]


def _require_tenant(tenant_ctx: TenantContext | None) -> TenantContext:
    """取请求租户上下文（缺失抛认证错误）。

    Args:
        tenant_ctx: 请求上下文租户。

    Returns:
        TenantContext: 租户上下文。

    Raises:
        AuthError: 缺少租户标识 / 缺少租户主键（20001 / 401）。
    """
    if tenant_ctx is None:
        raise AuthError("缺少租户标识")
    if tenant_ctx.tenant_id is None:
        raise AuthError("租户缺少主键标识")
    return tenant_ctx


@router.post("/revoke-user")
async def revoke_user_sessions(
    request: Request,
    req: RevokeUserSessionsRequest,
    security: SecurityDep,
    store: StoreDep,
    publisher: PublisherDep,
    tenant_ctx: TenantDep,
) -> ApiResponse[RevokeUserSessionsResult]:
    """按用户撤销其全部在线会话（即时失效）。

    Args:
        request: 请求对象（取引擎注册表与会话工厂）。
        req: 撤销请求（用户 ID + 原因）。
        security: 会话安全原语。
        store: 会话标记存储。
        publisher: 实时推送器。
        tenant_ctx: 请求上下文租户。

    Returns:
        ApiResponse: 统一响应，data 为被撤销的在线会话数。
    """
    tenant = _require_tenant(tenant_ctx)
    registry: EngineRegistry = request.app.state.engine_registry
    factory = request.app.state.session_factory
    async with session_scope(registry, db_key=tenant.db_key, factory=factory) as session:
        service = SessionService(
            session=session,
            uow=DbUnitOfWork(session),
            security=security,
            store=store,
            publisher=publisher,
        )
        revoked = await service.revoke_user_sessions(req.user_id, tenant=str(tenant.tenant_id), reason=req.reason)
    return ApiResponse.ok(RevokeUserSessionsResult(revoked=len(revoked)))
