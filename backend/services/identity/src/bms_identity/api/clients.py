"""认证与身份服务端点：客户端注册与管理最小接口（`/api/v1/open/clients`）。

- 鉴权：`require_auth` + `require_permission("open:manage")`（权限基座当前为 Null = RBAC 前超管口径）。
- 数据源：identity 服务租户库 `sys_client`；响应永不返回 secret 与哈希，明文仅创建 / 重置返回一次。
"""

from __future__ import annotations

import json
from typing import Annotated, cast

from fastapi import Depends, Path, Request

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import get_audit_capturer, get_password_hasher, get_tenant
from bms_core.audit.base import AuditCapturer
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import AuthError
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import session_scope
from bms_core.db.tenant import TenantContext
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery, BasePageResponse
from bms_core.security.base import BasePasswordHasher
from bms_identity.models.client import SysClient
from bms_identity.schemas.oidc import (
    ClientCreated,
    ClientCreateRequest,
    ClientItem,
    ClientSecretReset,
    ClientStatusRequest,
)
from bms_identity.services.clients import ClientService

router = BaseRouter(
    key="open_clients",
    prefix="/open/clients",
    tags=["open-clients"],
    dependencies=[Depends(require_auth), Depends(require_permission("open:manage"))],
)

TenantDep = Annotated[TenantContext | None, Depends(get_tenant)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
HasherDep = Annotated[BasePasswordHasher, Depends(get_password_hasher)]
AuditDep = Annotated[AuditCapturer, Depends(get_audit_capturer)]
ClientIdPath = Annotated[int, Path(description="客户端主键")]


def _require_tenant(tenant: TenantContext | None) -> TenantContext:
    """取生效租户（缺失即认证失败）。

    Args:
        tenant: 请求上下文租户。

    Returns:
        TenantContext: 生效租户。

    Raises:
        AuthError: 缺少租户标识（20001/401）。
    """
    if tenant is None:
        raise AuthError("缺少租户标识")
    return tenant


def _item(row: SysClient) -> ClientItem:
    """客户端行 → 展示项（不返回 secret 与哈希）。

    Args:
        row: 客户端行。

    Returns:
        ClientItem: 展示项。
    """
    return ClientItem(
        id=row.id,
        client_id=row.client_id,
        name=row.name,
        redirect_uris=_load_list(row.redirect_uris),
        grant_types=_load_list(row.grant_types),
        scopes=_load_list(row.scopes),
        ip_whitelist=_load_list(row.ip_whitelist),
        status=row.status,
    )


def _load_list(raw: str | None) -> ConcurrentStableList[str]:
    """解析 JSON 数组字段（非法返回空列表）。

    Args:
        raw: 列原文。

    Returns:
        ConcurrentStableList[str]: 字符串列表。
    """
    try:
        parsed = json.loads(raw or "[]")
    except ValueError:
        return ConcurrentStableList()
    return (
        ConcurrentStableList(str(item) for item in cast("list[object]", parsed))
        if isinstance(parsed, list)
        else ConcurrentStableList()
    )


async def _run_list(
    request: Request,
    tenant: TenantContext,
    hasher: BasePasswordHasher,
    audit: AuditCapturer,
    query: BasePageQuery,
    status: str | None,
    name: str | None,
) -> BasePageResponse[ClientItem]:
    """执行分页查询（会话作用域内）。

    Args:
        request: 请求对象。
        tenant: 生效租户。
        hasher: 口令哈希实现。
        audit: 审计捕获占位。
        query: 分页请求。
        status: 状态过滤。
        name: 名称过滤。

    Returns:
        BasePageResponse: 分页响应。
    """
    registry: EngineRegistry = request.app.state.engine_registry
    async with session_scope(registry, db_key=tenant.db_key, factory=request.app.state.session_factory) as session:
        service = ClientService(session=session, uow=DbUnitOfWork(session), password_hasher=hasher, audit=audit)
        rows, total = await service.list(query, status=status, name=name)
    return BasePageResponse[ClientItem](
        list=[_item(row) for row in rows],
        total=total,
        page=query.page,
        size=query.size,
    )


@router.post("")
async def create_client(
    request: Request,
    req: ClientCreateRequest,
    tenant_ctx: TenantDep,
    hasher: HasherDep,
    audit: AuditDep,
) -> ApiResponse[ClientCreated]:
    """注册客户端（返回 `client_id` 与明文 secret 一次）。

    Args:
        request: 请求对象。
        req: 注册请求。
        tenant_ctx: 请求上下文租户。
        hasher: 口令哈希实现。
        audit: 审计捕获占位。

    Returns:
        ApiResponse: 统一响应，data 为凭据（`ClientCreated`）。
    """
    tenant = _require_tenant(tenant_ctx)
    registry: EngineRegistry = request.app.state.engine_registry
    async with session_scope(registry, db_key=tenant.db_key, factory=request.app.state.session_factory) as session:
        service = ClientService(session=session, uow=DbUnitOfWork(session), password_hasher=hasher, audit=audit)
        created = await service.create(
            name=req.name,
            redirect_uris=req.redirect_uris,
            grant_types=req.grant_types,
            scopes=req.scopes,
            ip_whitelist=req.ip_whitelist,
            public=req.public,
        )
    item = _item(created.client)
    return ApiResponse.ok(
        ClientCreated(
            client_id=item.client_id,
            client_secret=created.secret,
            name=item.name,
            redirect_uris=item.redirect_uris,
            grant_types=item.grant_types,
            scopes=item.scopes,
            ip_whitelist=item.ip_whitelist,
            status=item.status,
        )
    )


@router.get("")
async def list_clients(
    request: Request,
    tenant_ctx: TenantDep,
    hasher: HasherDep,
    audit: AuditDep,
    query: PageDep,
    status: str | None = None,
    name: str | None = None,
) -> ApiResponse[BasePageResponse[ClientItem]]:
    """客户端分页列表（可选 status / name 筛选）。

    Args:
        request: 请求对象。
        tenant_ctx: 请求上下文租户。
        hasher: 口令哈希实现。
        audit: 审计捕获占位。
        query: 分页请求。
        status: 状态过滤（可选）。
        name: 名称模糊过滤（可选）。

    Returns:
        ApiResponse: 统一响应，data 为分页客户端。
    """
    tenant = _require_tenant(tenant_ctx)
    page = await _run_list(request, tenant, hasher, audit, query, status, name)
    return ApiResponse.ok(page)


@router.get("/{client_id}")
async def get_client(
    request: Request,
    client_id: ClientIdPath,
    tenant_ctx: TenantDep,
    hasher: HasherDep,
    audit: AuditDep,
) -> ApiResponse[ClientItem]:
    """客户端详情。

    Args:
        request: 请求对象。
        client_id: 客户端主键。
        tenant_ctx: 请求上下文租户。
        hasher: 口令哈希实现。
        audit: 审计捕获占位。

    Returns:
        ApiResponse: 统一响应，data 为客户端项。
    """
    tenant = _require_tenant(tenant_ctx)
    registry: EngineRegistry = request.app.state.engine_registry
    async with session_scope(registry, db_key=tenant.db_key, factory=request.app.state.session_factory) as session:
        service = ClientService(session=session, uow=DbUnitOfWork(session), password_hasher=hasher, audit=audit)
        row = await service.get(client_id)
    return ApiResponse.ok(_item(row))


@router.post("/{client_id}/status")
async def set_client_status(
    request: Request,
    req: ClientStatusRequest,
    client_id: ClientIdPath,
    tenant_ctx: TenantDep,
    hasher: HasherDep,
    audit: AuditDep,
) -> ApiResponse[ClientItem]:
    """启停客户端。

    Args:
        request: 请求对象。
        req: 启停请求。
        client_id: 客户端主键。
        tenant_ctx: 请求上下文租户。
        hasher: 口令哈希实现。
        audit: 审计捕获占位。

    Returns:
        ApiResponse: 统一响应，data 为更新后的客户端项。
    """
    tenant = _require_tenant(tenant_ctx)
    registry: EngineRegistry = request.app.state.engine_registry
    async with session_scope(registry, db_key=tenant.db_key, factory=request.app.state.session_factory) as session:
        service = ClientService(session=session, uow=DbUnitOfWork(session), password_hasher=hasher, audit=audit)
        row = await service.set_status(client_id, req.status)
    return ApiResponse.ok(_item(row))


@router.post("/{client_id}/reset-secret")
async def reset_client_secret(
    request: Request,
    client_id: ClientIdPath,
    tenant_ctx: TenantDep,
    hasher: HasherDep,
    audit: AuditDep,
) -> ApiResponse[ClientSecretReset]:
    """重置客户端密钥（新明文仅本次返回）。

    Args:
        request: 请求对象。
        client_id: 客户端主键。
        tenant_ctx: 请求上下文租户。
        hasher: 口令哈希实现。
        audit: 审计捕获占位。

    Returns:
        ApiResponse: 统一响应，data 为新凭据（`ClientSecretReset`）。
    """
    tenant = _require_tenant(tenant_ctx)
    registry: EngineRegistry = request.app.state.engine_registry
    async with session_scope(registry, db_key=tenant.db_key, factory=request.app.state.session_factory) as session:
        service = ClientService(session=session, uow=DbUnitOfWork(session), password_hasher=hasher, audit=audit)
        reset = await service.reset_secret(client_id)
    return ApiResponse.ok(ClientSecretReset(client_id=reset.client.client_id, client_secret=reset.secret))
