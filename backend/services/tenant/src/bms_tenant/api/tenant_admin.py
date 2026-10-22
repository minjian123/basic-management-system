"""租户管理面路由：`/api/v1/tenants`（列表 / 详情 / 开通 / 修改 / 停用启用 / 配额 / 模块；任务 `04_01`）。

- **鉴权**：模块级 `require_auth`；各端点挂 `require_permission("tenant:*")`。平台超管的平台租户以
  `platform_admin` 角色类型豁免（全权限），低权限平台角色按授权集合。
- **数据访问**：`sys_tenant*` 一律走 tenant 服务平台库（`get_platform_*`），不读请求租户库。
- **开通**：同步 + `Idempotency-Key`（成功回放 / 失败可重试 / 进行中 82003）。
- **停用**：状态置 `suspended` + 事件 + 引擎回收 + 按租户撤销会话 + 租户源缓存失效。
"""

from typing import Annotated, cast

from fastapi import Depends, Header, Path, Query, Request

from bms_core.api.base import AuthContext, BaseRouter, page_query, require_auth
from bms_core.api.deps import (
    get_cache_region,
    get_idempotency_store,
    get_outbox_store,
    get_service_client,
    get_tenant_source,
)
from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import (
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.config import Settings
from bms_core.core.exceptions import TenantStateConflictError
from bms_core.core.logging import get_logger
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, get_platform_read_db, get_platform_write_db
from bms_core.db.tenant import TenantLookup
from bms_core.idempotency.base import IDEMPOTENCY_HEADER, IdempotencyStore, build_idempotency_key
from bms_core.outbox.base import BaseOutboxStore
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery
from bms_core.servicecall.base import BaseServiceClient, ServiceCallPolicy, ServiceRequest
from bms_tenant.schemas.tenant_admin import (
    TenantCreateRequest,
    TenantDetail,
    TenantList,
    TenantModuleItemList,
    TenantModuleOptionList,
    TenantModuleUpdateRequest,
    TenantProvisionResult,
    TenantQuotaItemList,
    TenantQuotaUpdateRequest,
    TenantUpdateRequest,
)
from bms_tenant.services.provisioning import TenantProvisionService
from bms_tenant.services.tenant_admin import TenantAdminService
from bms_tenant.services.tenant_module import ModuleCatalog, TenantModuleService
from bms_tenant.services.tenant_quota import TenantQuotaService

router = BaseRouter(key="tenant_admin", prefix="/tenants", tags=["tenant"], dependencies=[Depends(require_auth)])

_LOGGER = get_logger("bms.tenant_admin")

AuthDep = Annotated[AuthContext, Depends(require_auth)]
WriteDep = Annotated[DbSession, Depends(get_platform_write_db)]
ReadDep = Annotated[DbSession, Depends(get_platform_read_db)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
ClientDep = Annotated[BaseServiceClient, Depends(get_service_client)]
CacheDep = Annotated[CacheRegion, Depends(get_cache_region)]
OutboxDep = Annotated[BaseOutboxStore, Depends(get_outbox_store)]
IdempotencyDep = Annotated[IdempotencyStore, Depends(get_idempotency_store)]
SourceDep = Annotated[TenantLookup, Depends(get_tenant_source)]
TenantIdPath = Annotated[int, Path(description="租户主键")]
ModuleKeyPath = Annotated[str, Path(description="模块标识")]
CodeQuery = Annotated[str | None, Query(description="租户编码（模糊）")]
NameQuery = Annotated[str | None, Query(description="租户名称（模糊）")]
StatusQuery = Annotated[str | None, Query(description="状态筛选（provisioning/active/suspended）")]
IdempotencyKeyHeader = Annotated[
    str | None,
    Header(alias=IDEMPOTENCY_HEADER, description="幂等键（可选；重复开通回放首次结果）"),
]

_REQUIRE_QUERY = Depends(require_permission("tenant:query"))
_REQUIRE_CREATE = Depends(require_permission("tenant:create"))
_REQUIRE_UPDATE = Depends(require_permission("tenant:update"))
_REQUIRE_MANAGE = Depends(require_permission("tenant:manage"))
_REQUIRE_QUOTA = Depends(require_permission("tenant:quota"))


def _settings(request: Request) -> Settings:
    """取应用配置。

    Args:
        request: 请求对象。

    Returns:
        Settings: 应用配置。
    """
    return request.app.state.settings


def _modules(
    session: DbSession, client: BaseServiceClient, cache: CacheRegion, settings: Settings
) -> TenantModuleService:
    """构造租户模块服务。

    Args:
        session: 平台库会话。
        client: 服务间调用客户端。
        cache: 缓存域。
        settings: 应用配置。

    Returns:
        TenantModuleService: 模块服务。
    """
    del settings
    return TenantModuleService(session=session, catalog=ModuleCatalog(client=client, cache=cache), cache=cache)


def _quotas(session: DbSession, request: Request) -> TenantQuotaService:
    """构造租户配额服务。

    Args:
        session: 平台库会话。
        request: 请求对象（取配置）。

    Returns:
        TenantQuotaService: 配额服务。
    """
    return TenantQuotaService(session, _settings(request))


def _admin(session: DbSession, request: Request, client: BaseServiceClient, cache: CacheRegion) -> TenantAdminService:
    """构造租户管理服务。

    Args:
        session: 平台库会话。
        request: 请求对象。
        client: 服务间调用客户端。
        cache: 缓存域。

    Returns:
        TenantAdminService: 管理服务。
    """
    return TenantAdminService(
        session=session,
        modules=_modules(session, client, cache, _settings(request)),
        quotas=_quotas(session, request),
        outbox=_outbox(request),
    )


def _outbox(request: Request) -> BaseOutboxStore:
    """取应用级发件箱。

    Args:
        request: 请求对象。

    Returns:
        BaseOutboxStore: 发件箱。
    """
    return request.app.state.outbox_store


@router.get("/module-options", dependencies=[_REQUIRE_QUERY])
async def module_options(
    request: Request, client: ClientDep, cache: CacheDep, session: ReadDep
) -> ApiResponse[TenantModuleOptionList]:
    """开通向导模块选项（目录全量 + 可勾选标记）。

    Args:
        request: 请求对象。
        client: 服务间调用客户端。
        cache: 缓存域。
        session: 平台库只读会话。

    Returns:
        ApiResponse: 统一响应（data 为选项清单）。
    """
    service = _modules(session, client, cache, _settings(request))
    return ApiResponse.ok(TenantModuleOptionList(items=await service.options()))


@router.get("", dependencies=[_REQUIRE_QUERY])
async def list_tenants(
    request: Request,
    session: ReadDep,
    query: PageDep,
    client: ClientDep,
    cache: CacheDep,
    code: CodeQuery = None,
    name: NameQuery = None,
    status: StatusQuery = None,
) -> ApiResponse[TenantList]:
    """业务租户分页列表（平台租户排除）。

    Args:
        request: 请求对象。
        session: 平台库只读会话。
        query: 分页请求。
        client: 服务间调用客户端。
        cache: 缓存域。
        code: 编码模糊筛选。
        name: 名称模糊筛选。
        status: 状态筛选。

    Returns:
        ApiResponse: 统一响应（data 为分页结果）。
    """
    service = _admin(session, request, client, cache)
    return ApiResponse.ok(await service.list(page=query.page, size=query.size, code=code, name=name, status=status))


@router.post("", status_code=201, dependencies=[_REQUIRE_CREATE])
async def create_tenant(
    request: Request,
    req: TenantCreateRequest,
    session: WriteDep,
    client: ClientDep,
    cache: CacheDep,
    auth: AuthDep,
    idempotency: IdempotencyDep,
    idempotency_key: IdempotencyKeyHeader = None,
) -> ApiResponse[TenantProvisionResult]:
    """开通租户（同步全流程；支持幂等键）。

    Args:
        request: 请求对象。
        req: 开通请求。
        session: 平台库写会话。
        client: 服务间调用客户端。
        cache: 缓存域。
        auth: 登录态（操作人）。
        idempotency: 幂等存储。
        idempotency_key: 幂等键请求头。

    Returns:
        ApiResponse: 统一响应（data 为开通结果，含初始口令）。
    """
    modules = _modules(session, client, cache, _settings(request))
    quotas = _quotas(session, request)
    admin = _admin(session, request, client, cache)
    service = TenantProvisionService(
        session=session,
        settings=_settings(request),
        modules=modules,
        quotas=quotas,
        outbox=_outbox(request),
        admin=admin,
    )
    key = build_idempotency_key(key=idempotency_key) if idempotency_key else None
    if key is not None and not await idempotency.begin(key):
        payload = await idempotency.load(key)
        if payload is None:
            raise TenantStateConflictError("开通请求处理中，请稍后重试")
        if payload.get("status") != "failed":
            return ApiResponse.ok(TenantProvisionResult.model_validate(payload))
    try:
        result = await service.create(req, actor_id=auth.user_id)
    except Exception:
        if key is not None:
            await idempotency.save(key, {"status": "failed"})
        raise
    if key is not None:
        await idempotency.save(key, result.model_dump(mode="json"))
    source = request.app.state.tenant_source
    _invalidate(source, result.tenant.code, result.tenant.domain)
    return ApiResponse.ok(result)


@router.get("/{tenant_id}", dependencies=[_REQUIRE_QUERY])
async def get_tenant(
    request: Request, tenant_id: TenantIdPath, session: ReadDep, client: ClientDep, cache: CacheDep
) -> ApiResponse[TenantDetail]:
    """租户详情（含配额与模块清单）。

    Args:
        request: 请求对象。
        tenant_id: 租户主键。
        session: 平台库只读会话。
        client: 服务间调用客户端。
        cache: 缓存域。

    Returns:
        ApiResponse: 统一响应（data 为详情）。
    """
    return ApiResponse.ok(await _admin(session, request, client, cache).detail(tenant_id))


@router.put("/{tenant_id}", dependencies=[_REQUIRE_UPDATE])
async def update_tenant(
    request: Request,
    req: TenantUpdateRequest,
    tenant_id: TenantIdPath,
    session: WriteDep,
    client: ClientDep,
    cache: CacheDep,
) -> ApiResponse[TenantDetail]:
    """修改租户（名称 / 域名 / 到期时间）。

    Args:
        request: 请求对象。
        req: 修改请求。
        tenant_id: 租户主键。
        session: 平台库写会话。
        client: 服务间调用客户端。
        cache: 缓存域。

    Returns:
        ApiResponse: 统一响应（data 为更新后的详情）。
    """
    result = await _admin(session, request, client, cache).update(tenant_id, req)
    _invalidate(request.app.state.tenant_source, result.code, result.domain)
    return ApiResponse.ok(result)


@router.post("/{tenant_id}/suspend", dependencies=[_REQUIRE_MANAGE])
async def suspend_tenant(
    request: Request, tenant_id: TenantIdPath, session: WriteDep, client: ClientDep, cache: CacheDep, source: SourceDep
) -> ApiResponse[TenantDetail]:
    """停用租户（事件 + 引擎回收 + 按租户撤销会话 + 缓存失效）。

    Args:
        request: 请求对象。
        tenant_id: 租户主键。
        session: 平台库写会话。
        client: 服务间调用客户端。
        cache: 缓存域。
        source: 租户源（缓存失效）。

    Returns:
        ApiResponse: 统一响应（data 为停用后的详情）。
    """
    admin = _admin(session, request, client, cache)
    row = await admin.tenant_row(tenant_id)
    result = await admin.suspend(tenant_id)
    registry: EngineRegistry = request.app.state.engine_registry
    basis = row.code
    for service in _tenant_services():
        await registry.release(f"tenant_{service}_{basis}")
    revoked = await _revoke_sessions(client, basis)
    _invalidate(source, result.code, result.domain)
    _LOGGER.info("tenant_suspended", tenant_id=tenant_id, revoked_sessions=revoked)
    return ApiResponse.ok(result)


@router.post("/{tenant_id}/activate", dependencies=[_REQUIRE_MANAGE])
async def activate_tenant(
    request: Request, tenant_id: TenantIdPath, session: WriteDep, client: ClientDep, cache: CacheDep, source: SourceDep
) -> ApiResponse[TenantDetail]:
    """启用租户（事件 + 缓存失效）。

    Args:
        request: 请求对象。
        tenant_id: 租户主键。
        session: 平台库写会话。
        client: 服务间调用客户端。
        cache: 缓存域。
        source: 租户源（缓存失效）。

    Returns:
        ApiResponse: 统一响应（data 为启用后的详情）。
    """
    result = await _admin(session, request, client, cache).activate(tenant_id)
    _invalidate(source, result.code, result.domain)
    return ApiResponse.ok(result)


@router.get("/{tenant_id}/quotas", dependencies=[_REQUIRE_QUERY])
async def get_quotas(request: Request, tenant_id: TenantIdPath, session: ReadDep) -> ApiResponse[TenantQuotaItemList]:
    """配额与用量。

    Args:
        request: 请求对象。
        tenant_id: 租户主键。
        session: 平台库只读会话。

    Returns:
        ApiResponse: 统一响应（data 为配额项）。
    """
    return ApiResponse.ok(TenantQuotaItemList(items=await _quotas(session, request).list_items(tenant_id)))


@router.put("/{tenant_id}/quotas", dependencies=[_REQUIRE_QUOTA])
async def put_quotas(
    request: Request, req: TenantQuotaUpdateRequest, tenant_id: TenantIdPath, session: WriteDep
) -> ApiResponse[TenantQuotaItemList]:
    """配置配额限额（整组覆盖；未列出的维度保持原值）。

    Args:
        request: 请求对象。
        req: 配额配置请求。
        tenant_id: 租户主键。
        session: 平台库写会话。

    Returns:
        ApiResponse: 统一响应（data 为更新后的配额项）。
    """
    result = await _quotas(session, request).update_limits(tenant_id, req.items)
    await session.commit()
    return ApiResponse.ok(TenantQuotaItemList(items=result))


@router.get("/{tenant_id}/modules", dependencies=[_REQUIRE_QUERY])
async def get_modules(
    request: Request, tenant_id: TenantIdPath, session: ReadDep, client: ClientDep, cache: CacheDep
) -> ApiResponse[TenantModuleItemList]:
    """租户模块清单（三态）。

    Args:
        request: 请求对象。
        tenant_id: 租户主键。
        session: 平台库只读会话。
        client: 服务间调用客户端。
        cache: 缓存域。

    Returns:
        ApiResponse: 统一响应（data 为模块项）。
    """
    service = _modules(session, client, cache, _settings(request))
    return ApiResponse.ok(TenantModuleItemList(items=await service.list_items(tenant_id)))


@router.put("/{tenant_id}/modules/{module_key}", dependencies=[_REQUIRE_MANAGE])
async def put_module(
    request: Request,
    req: TenantModuleUpdateRequest,
    tenant_id: TenantIdPath,
    module_key: ModuleKeyPath,
    session: WriteDep,
    client: ClientDep,
    cache: CacheDep,
    auth: AuthDep,
) -> ApiResponse[TenantModuleItemList]:
    """租户模块开关（目录校验 + 状态切换）。

    Args:
        request: 请求对象。
        req: 开关请求。
        tenant_id: 租户主键。
        module_key: 模块标识。
        session: 平台库写会话。
        client: 服务间调用客户端。
        cache: 缓存域。
        auth: 登录态（操作人）。

    Returns:
        ApiResponse: 统一响应（data 为更新后的模块清单）。
    """
    service = _modules(session, client, cache, _settings(request))
    await service.switch(tenant_id, module_key, req.status, opened_by=auth.user_id)
    await session.commit()
    return ApiResponse.ok(TenantModuleItemList(items=await service.list_items(tenant_id)))


def _tenant_services() -> ConcurrentStableList[str]:
    """取需回收引擎的服务标识。

    Returns:
        tuple[str, ...]: 服务标识。
    """
    from bms_core.tenant.provisioning import enabled_tenant_services

    return ConcurrentStableList(enabled_tenant_services())


async def _revoke_sessions(client: BaseServiceClient, tenant_code: str) -> int:
    """调 identity 内部端点按租户撤销全部会话（失败仅告警）。

    Args:
        client: 服务间调用客户端。
        tenant_code: 租户编码。

    Returns:
        int: 吊销会话数（失败为 0）。
    """
    try:
        response = await client.call(
            ServiceRequest(
                service="identity",
                method="POST",
                path="/api/v1/identity/internal/sessions/revoke-tenant",
                json_body=ConcurrentStableFrozenDict({"tenant_code": tenant_code}),
                tenant_id=tenant_code,
                policy=ServiceCallPolicy(scopes=ConcurrentStableFrozenList(("session_revoke",))),
            )
        )
    except Exception as exc:
        _LOGGER.warning("tenant_session_revoke_failed", tenant_code=tenant_code, error=type(exc).__name__)
        return 0
    payload = response.payload()
    if response.status_code != 200 or not isinstance(payload, dict):
        _LOGGER.warning("tenant_session_revoke_bad_response", tenant_code=tenant_code, status=response.status_code)
        return 0
    data = cast("dict[str, object]", payload).get("data")
    if not isinstance(data, dict):
        return 0
    raw = cast("dict[str, object]", data).get("revoked", 0)
    return int(raw) if isinstance(raw, int | str) else 0


def _invalidate(source: TenantLookup, code: str | None, domain: str | None) -> None:
    """失效租户源缓存并递增版本（写路径统一口径）。

    Args:
        source: 租户源。
        code: 租户编码。
        domain: 子域名。
    """
    invalidate = getattr(source, "invalidate", None)
    if callable(invalidate):
        invalidate(code, domain=domain)
    bump = getattr(source, "bump_version", None)
    if callable(bump):
        bump()
