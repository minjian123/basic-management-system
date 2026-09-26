"""认证与身份服务端点：会话管理（在线列表 / 详情 / 强制踢出）。

- 端点挂 `require_auth` + `require_permission("session:query" | "session:kick")`；permission 基座当前
  为 Null（恒定通过）= RBAC 前平台超管口径，RBAC 就绪后自动收口。
- 列表仅未撤销未过期会话；详情返回任意记录（含已撤销）；踢出即时生效（删标记 + 吊销 refresh + 落库）。
"""

from datetime import datetime
from typing import Annotated

from fastapi import Depends, Query, Request

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import (
    get_realtime_publisher,
    get_session_security,
    get_session_store,
    get_tenant,
)
from bms_core.core.context import current_user_id
from bms_core.core.exceptions import AuthError
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope
from bms_core.db.tenant import TenantContext
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery, BasePageResponse
from bms_core.security.base import BaseSessionSecurity
from bms_core.session.base import BaseSessionStore
from bms_core.ws.base import BaseRealtimePublisher
from bms_identity.models.session import SysSession
from bms_identity.schemas.session import KickResult, SessionItem
from bms_identity.services.session import SessionService

router = BaseRouter(
    key="session",
    prefix="/sessions",
    tags=["session"],
    dependencies=[Depends(require_auth)],
)

SecurityDep = Annotated[BaseSessionSecurity, Depends(get_session_security)]
StoreDep = Annotated[BaseSessionStore, Depends(get_session_store)]
PublisherDep = Annotated[BaseRealtimePublisher, Depends(get_realtime_publisher)]
TenantDep = Annotated[TenantContext | None, Depends(get_tenant)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
UserIdQuery = Annotated[int | None, Query(description="用户 ID（精确）")]
DeviceQuery = Annotated[str | None, Query(description="设备标识（模糊）")]
IpQuery = Annotated[str | None, Query(description="登录 IP（模糊）")]
LoginFromQuery = Annotated[datetime | None, Query(description="登录时间下界（UTC，闭区间）")]
LoginToQuery = Annotated[datetime | None, Query(description="登录时间上界（UTC，闭区间）")]

_REQUIRE_QUERY = Depends(require_permission("session:query"))
_REQUIRE_KICK = Depends(require_permission("session:kick"))


def _build_service(
    *,
    session: DbSession,
    security: BaseSessionSecurity,
    store: BaseSessionStore,
    publisher: BaseRealtimePublisher,
) -> SessionService:
    """构造会话管理服务。

    Args:
        session: 认证服务租户库会话。
        security: 会话安全原语。
        store: 会话标记存储。
        publisher: 实时推送器。

    Returns:
        SessionService: 会话管理服务实例。
    """
    return SessionService(
        session=session,
        uow=DbUnitOfWork(session),
        security=security,
        store=store,
        publisher=publisher,
    )


def _to_item(record: SysSession) -> SessionItem:
    """会话记录 → 契约。

    Args:
        record: 会话记录。

    Returns:
        SessionItem: 会话行契约。
    """
    return SessionItem(
        session_id=record.session_id,
        user_id=record.user_id,
        device=record.device,
        ip=record.ip,
        login_at=record.login_at,
        expires_at=record.expires_at,
        revoked_at=record.revoked_at,
    )


def _require_tenant(tenant_ctx: TenantContext | None) -> TenantContext:
    """取请求租户上下文（缺失抛认证错误）。

    Args:
        tenant_ctx: 请求上下文租户。

    Returns:
        TenantContext: 租户上下文。

    Raises:
        AuthError: 缺少租户标识（20001 / 401）。
    """
    if tenant_ctx is None:
        raise AuthError("缺少租户标识")
    return tenant_ctx


@router.get("", dependencies=[_REQUIRE_QUERY])
async def list_sessions(
    request: Request,
    query: PageDep,
    security: SecurityDep,
    store: StoreDep,
    publisher: PublisherDep,
    tenant_ctx: TenantDep,
    user_id: UserIdQuery = None,
    device: DeviceQuery = None,
    ip: IpQuery = None,
    login_from: LoginFromQuery = None,
    login_to: LoginToQuery = None,
) -> ApiResponse[BasePageResponse[SessionItem]]:
    """在线会话列表（仅未撤销未过期；筛选 + 分页）。

    Args:
        request: 请求对象（取引擎注册表与会话工厂）。
        query: 分页与排序参数。
        security: 会话安全原语。
        store: 会话标记存储。
        publisher: 实时推送器。
        tenant_ctx: 请求上下文租户。
        user_id: 用户 ID（精确）。
        device: 设备标识（模糊）。
        ip: 登录 IP（模糊）。
        login_from: 登录时间下界（UTC）。
        login_to: 登录时间上界（UTC）。

    Returns:
        ApiResponse: 统一响应，data 为分页会话列表。
    """
    tenant = _require_tenant(tenant_ctx)
    registry: EngineRegistry = request.app.state.engine_registry
    factory = request.app.state.session_factory
    async with session_scope(registry, db_key=tenant.db_key, factory=factory) as session:
        service = _build_service(session=session, security=security, store=store, publisher=publisher)
        items, total = await service.list_sessions(
            query, user_id=user_id, device=device, ip=ip, login_from=login_from, login_to=login_to
        )
    return ApiResponse.ok(
        BasePageResponse[SessionItem](
            list=[_to_item(item) for item in items], total=total, page=query.page, size=query.size
        )
    )


@router.get("/{session_id}", dependencies=[_REQUIRE_QUERY])
async def get_session(
    request: Request,
    session_id: str,
    security: SecurityDep,
    store: StoreDep,
    publisher: PublisherDep,
    tenant_ctx: TenantDep,
) -> ApiResponse[SessionItem]:
    """会话详情（含已撤销会话，供 revoked 状态查询）。

    Args:
        request: 请求对象。
        session_id: 会话 id。
        security: 会话安全原语。
        store: 会话标记存储。
        publisher: 实时推送器。
        tenant_ctx: 请求上下文租户。

    Returns:
        ApiResponse: 统一响应，data 为会话行。
    """
    tenant = _require_tenant(tenant_ctx)
    registry: EngineRegistry = request.app.state.engine_registry
    factory = request.app.state.session_factory
    async with session_scope(registry, db_key=tenant.db_key, factory=factory) as session:
        service = _build_service(session=session, security=security, store=store, publisher=publisher)
        record = await service.detail(session_id)
        item = _to_item(record)
    return ApiResponse.ok(item)


@router.post("/{session_id}/kick", dependencies=[_REQUIRE_KICK])
async def kick_session(
    request: Request,
    session_id: str,
    security: SecurityDep,
    store: StoreDep,
    publisher: PublisherDep,
    tenant_ctx: TenantDep,
) -> ApiResponse[KickResult]:
    """强制踢出会话（即时生效：删标记 + 吊销 refresh + `revoked_at` 落库 + 广播占位）。

    Args:
        request: 请求对象。
        session_id: 会话 id。
        security: 会话安全原语。
        store: 会话标记存储。
        publisher: 实时推送器。
        tenant_ctx: 请求上下文租户。

    Returns:
        ApiResponse: 统一响应，data 为踢出结果（会话 id / 撤销时间 / 原因）。
    """
    tenant = _require_tenant(tenant_ctx)
    registry: EngineRegistry = request.app.state.engine_registry
    factory = request.app.state.session_factory
    async with session_scope(registry, db_key=tenant.db_key, factory=factory) as session:
        service = _build_service(session=session, security=security, store=store, publisher=publisher)
        return ApiResponse.ok(await service.kick(session_id, tenant=tenant.tenant_code, actor=current_user_id.get()))
