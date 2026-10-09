"""平台服务端点：`/api/v1/roles`（角色 CRUD / 用户分配 / 授权 / 字段权限 / 数据权限）。

- **鉴权**：模块级 `require_auth`；读挂 `role:query`、写挂 `role:create` / `role:update` / `role:delete`，
  分配与授权挂 `role:grant`（当前 `NullPermissionChecker` 恒放行，`02_04` 注入真实检查器后自动收口）；
- **双库依赖**：角色域 5 表与 `sys_user` / `sys_dict_*` 在 **platform 服务租户库**（`get_uow`）；
  授权引用的菜单 / 表单 / 动作 / 字段元数据在 **platform 服务平台库**（`get_platform_uow`）——
  同服务、跨库，校验在同服务内完成（不经内部端点）；
- **写口径**：授权 / 字段 / 数据权限为**全量覆盖**（单事务先删后插）；分配为**幂等 upsert**；
  成功一次权限版本 +1（`bms:{租户}:permission:version`）；
- **幂等键**：`POST /roles/{id}/users` 与 `PUT /roles/{id}/permissions` 读 `Idempotency-Key` 头
  （缺失即跳过；范式同 `api/icon.py`），重复请求复用首次结果；
- **契约**：计入 platform 公开契约（`deploy/contracts/platform.json`）。
"""

from typing import Annotated, cast

from fastapi import Depends, Header, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import (
    current_tenant_id_of,
    get_cache_region,
    get_config_source,
    get_idempotency_store,
    get_platform_uow,
    get_service_client,
    get_tenant,
    get_uow,
)
from bms_core.cache.base import CacheRegion
from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_core.db.session import DbSession
from bms_core.db.tenant import TenantContext, current_tenant_id_str
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.idempotency.base import IDEMPOTENCY_HEADER, IdempotencyStore, build_idempotency_key
from bms_core.permission.base import BasePermissionChecker, get_permission_checker, require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery, BasePageResponse
from bms_core.servicecall.base import BaseServiceClient
from bms_core.transaction.base import (
    BaseTransactionManager,
    BaseTransactionParticipant,
    get_transaction_manager,
    get_transaction_participant,
)
from bms_platform.models.role import ROLE_TYPE_CUSTOM, SysDataScope, SysRole, SysRoleField, SysRolePermission
from bms_platform.models.user import SysUser
from bms_platform.repositories.role import (
    DataScopeRepository,
    RoleFieldRepository,
    RolePermissionRepository,
    RoleRepository,
    UserRoleRepository,
)
from bms_platform.repositories.user import UserRepository
from bms_platform.schemas.role import (
    AssignedUserItem,
    RoleAssignedUsers,
    RoleAssignmentsRequest,
    RoleAssignmentsResult,
    RoleAssignRequest,
    RoleCreateRequest,
    RoleDataScopeEntryItem,
    RoleDataScopeRequest,
    RoleDataScopes,
    RoleDetail,
    RoleFieldEntryItem,
    RoleFieldRequest,
    RoleFields,
    RoleItem,
    RolePermissionEntryItem,
    RolePermissionRequest,
    RolePermissions,
    RoleType,
    RoleUpdateRequest,
)
from bms_platform.services.role import ROLE_STATUSES, RoleService
from bms_platform.services.role_assign import RoleAssignService
from bms_platform.services.role_assignments import RoleAssignmentsService, RoleAssignmentWriter
from bms_platform.services.role_grant import (
    DataScopeGrantEntry,
    FieldGrantEntry,
    MenuMetadataChecker,
    PermissionGrantEntry,
    RoleGrantService,
)

router = BaseRouter(
    key="platform_roles",
    prefix="/roles",
    tags=["roles"],
    dependencies=[Depends(require_auth)],
)

UowDep = Annotated[UnitOfWork, Depends(get_uow)]
PlatformUowDep = Annotated[UnitOfWork, Depends(get_platform_uow)]
ConfigDep = Annotated[BaseConfigSource, Depends(get_config_source)]
CacheDep = Annotated[CacheRegion, Depends(get_cache_region)]
IdempotencyDep = Annotated[IdempotencyStore, Depends(get_idempotency_store)]
TenantDep = Annotated[TenantContext | None, Depends(get_tenant)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
ServiceClientDep = Annotated[BaseServiceClient, Depends(get_service_client)]
ManagerDep = Annotated[BaseTransactionManager, Depends(get_transaction_manager)]
ParticipantDep = Annotated[BaseTransactionParticipant, Depends(get_transaction_participant)]
CheckerDep = Annotated[BasePermissionChecker, Depends(get_permission_checker)]
KeywordQuery = Annotated[str | None, Query(description="关键字（角色码 / 名称；用户账号 / 姓名）")]
StatusQuery = Annotated[str | None, Query(description="状态（enabled/disabled）")]
IdempotencyKeyHeader = Annotated[
    str | None,
    Header(alias=IDEMPOTENCY_HEADER, description="幂等键（可选；重复提交复用首次结果）"),
]

_REQUIRE_QUERY = Depends(require_permission("role:query"))
_REQUIRE_CREATE = Depends(require_permission("role:create"))
_REQUIRE_UPDATE = Depends(require_permission("role:update"))
_REQUIRE_DELETE = Depends(require_permission("role:delete"))
_REQUIRE_GRANT = Depends(require_permission("role:grant"))


def _role_service(uow: UnitOfWork, config: BaseConfigSource) -> RoleService:
    """构造角色服务（请求级租户库会话）。

    Args:
        uow: 请求级工作单元（platform 服务租户库）。
        config: 系统参数取数。

    Returns:
        RoleService: 角色服务实例。
    """
    session = cast("DbSession", uow.session)
    return RoleService(RoleRepository(session), UserRoleRepository(session), uow, config)


def _assign_service(uow: UnitOfWork, cache: CacheRegion) -> RoleAssignService:
    """构造角色分配服务（请求级租户库会话）。

    Args:
        uow: 请求级工作单元（platform 服务租户库）。
        cache: 缓存能力域（权限版本 +1）。

    Returns:
        RoleAssignService: 角色分配服务实例。
    """
    session = cast("DbSession", uow.session)
    return RoleAssignService(RoleRepository(session), UserRoleRepository(session), UserRepository(session), uow, cache)


def _grant_service(uow: UnitOfWork, platform_uow: UnitOfWork, cache: CacheRegion) -> RoleGrantService:
    """构造角色授权服务（租户库写事务 + 平台库只读元数据校验双会话）。

    Args:
        uow: 请求级工作单元（platform 服务租户库）。
        platform_uow: 平台库工作单元（授权目标元数据校验，只读）。
        cache: 缓存能力域（权限版本 +1）。

    Returns:
        RoleGrantService: 角色授权服务实例。
    """
    session = cast("DbSession", uow.session)
    return RoleGrantService(
        RoleRepository(session),
        RolePermissionRepository(session),
        RoleFieldRepository(session),
        DataScopeRepository(session),
        MenuMetadataChecker(cast("DbSession", platform_uow.session)),
        uow,
        cache,
    )


def _require_status(status: str | None) -> None:
    """校验状态筛选值。

    Args:
        status: 状态（可空）。

    Raises:
        ParamError: 取值非法（10001）。
    """
    if status is not None and status not in ROLE_STATUSES:
        raise ParamError(f"角色状态非法：{status}")


def _is_builtin(role: SysRole) -> bool:
    """是否内置角色（按 `role_type` 判定，非 `custom` 即内置）。

    Args:
        role: 角色记录。

    Returns:
        bool: 内置为 True。
    """
    return role.role_type != ROLE_TYPE_CUSTOM


def _role_item(role: SysRole, *, builtin: bool, subject_count: int) -> RoleItem:
    """角色记录 → 列表行。

    Args:
        role: 角色记录。
        builtin: 是否内置角色。
        subject_count: 已分配用户数。

    Returns:
        RoleItem: 角色列表行。
    """
    return RoleItem(
        id=role.id,
        code=role.code,
        name=role.name,
        status=role.status,
        role_type=cast("RoleType", role.role_type),
        builtin=builtin,
        subject_count=subject_count,
    )


def _role_detail(role: SysRole, *, builtin: bool, subject_count: int) -> RoleDetail:
    """角色记录 → 详情（含版本与审计字段）。

    Args:
        role: 角色记录。
        builtin: 是否内置角色。
        subject_count: 已分配用户数。

    Returns:
        RoleDetail: 角色详情。
    """
    return RoleDetail(
        id=role.id,
        code=role.code,
        name=role.name,
        status=role.status,
        role_type=cast("RoleType", role.role_type),
        builtin=builtin,
        subject_count=subject_count,
        version=role.version,
        created_at=role.created_at,
        created_by=role.created_by,
        updated_at=role.updated_at,
        updated_by=role.updated_by,
    )


def _assigned_user(user: SysUser) -> AssignedUserItem:
    """用户记录 → 已分配用户行。

    Args:
        user: 用户记录。

    Returns:
        AssignedUserItem: 已分配用户行。
    """
    return AssignedUserItem(user_id=user.id, username=user.username, name=user.name, status=user.status)


def _permission_item(row: SysRolePermission) -> RolePermissionEntryItem:
    """授权记录 → 授权条目行。

    Args:
        row: 授权记录。

    Returns:
        RolePermissionEntryItem: 授权条目行。
    """
    return RolePermissionEntryItem(
        id=row.id, perm_type=row.perm_type, target_id=row.target_id, source_menu_id=row.source_menu_id
    )


def _field_item(row: SysRoleField) -> RoleFieldEntryItem:
    """字段权限记录 → 字段权限条目行。

    Args:
        row: 字段权限记录。

    Returns:
        RoleFieldEntryItem: 字段权限条目行。
    """
    return RoleFieldEntryItem(
        id=row.id,
        form_id=row.form_id,
        field_id=row.field_id,
        visible=row.visible,
        editable=row.editable,
        source_menu_id=row.source_menu_id,
    )


def _data_scope_item(row: SysDataScope) -> RoleDataScopeEntryItem:
    """数据权限记录 → 数据权限条目行。

    Args:
        row: 数据权限记录。

    Returns:
        RoleDataScopeEntryItem: 数据权限条目行。
    """
    return RoleDataScopeEntryItem(
        id=row.id,
        dict_type_id=row.dict_type_id,
        policy_type=row.policy_type,
        config=ConcurrentStableList(row.config or ()),
    )


# ------------------------------------------------------------------ 角色 CRUD


@router.get("", dependencies=[_REQUIRE_QUERY])
async def list_roles(
    query: PageDep,
    uow: UowDep,
    config: ConfigDep,
    kw: KeywordQuery = None,
    status: StatusQuery = None,
) -> ApiResponse[BasePageResponse[RoleItem]]:
    """角色列表（关键字 / 状态筛选 + 分页；含内置标记与主体数）。

    Args:
        query: 分页与排序参数。
        uow: 请求级工作单元。
        config: 系统参数取数。
        kw: 关键字（角色码 / 名称）。
        status: 状态（enabled/disabled）。

    Returns:
        ApiResponse: 统一响应，data 为分页角色列表。
    """
    _require_status(status)
    service = _role_service(uow, config)
    rows, total = await service.list_roles(query, keyword=kw, status=status)
    counts = await service.subject_counts(ConcurrentStableList(row.id for row in rows))
    items = ConcurrentStableList(
        _role_item(row, builtin=_is_builtin(row), subject_count=counts.get(row.id) or 0) for row in rows
    )
    return ApiResponse.ok(BasePageResponse[RoleItem](list=items, total=total, page=query.page, size=query.size))


@router.post("", dependencies=[_REQUIRE_CREATE])
async def create_role(req: RoleCreateRequest, uow: UowDep, config: ConfigDep) -> ApiResponse[RoleDetail]:
    """新增角色（角色码唯一 + 格式校验；内置角色码不可自建）。

    Args:
        req: 新增请求（角色码 / 名称 / 状态）。
        uow: 请求级工作单元。
        config: 系统参数取数。

    Returns:
        ApiResponse: 统一响应，data 为角色详情。
    """
    service = _role_service(uow, config)
    role = await service.create_role(code=req.code, name=req.name, status=req.status)
    return ApiResponse.ok(_role_detail(role, builtin=_is_builtin(role), subject_count=0))


@router.get("/{role_id}", dependencies=[_REQUIRE_QUERY])
async def get_role(role_id: int, uow: UowDep, config: ConfigDep) -> ApiResponse[RoleDetail]:
    """角色详情（含乐观锁版本与审计字段）。

    Args:
        role_id: 角色主键。
        uow: 请求级工作单元。
        config: 系统参数取数。

    Returns:
        ApiResponse: 统一响应，data 为角色详情。
    """
    service = _role_service(uow, config)
    role = await service.detail(role_id)
    counts = await service.subject_counts(ConcurrentStableList((role_id,)))
    return ApiResponse.ok(_role_detail(role, builtin=_is_builtin(role), subject_count=counts.get(role_id) or 0))


@router.put("/{role_id}", dependencies=[_REQUIRE_UPDATE])
async def update_role(role_id: int, req: RoleUpdateRequest, uow: UowDep, config: ConfigDep) -> ApiResponse[RoleDetail]:
    """修改角色（角色码 / 名称 / 状态；乐观锁 + 内置角色保护）。

    Args:
        role_id: 角色主键。
        req: 修改请求（角色码 / 名称 / 状态 / 版本）。
        uow: 请求级工作单元。
        config: 系统参数取数。

    Returns:
        ApiResponse: 统一响应，data 为角色详情。
    """
    service = _role_service(uow, config)
    role = await service.update_role(role_id, code=req.code, name=req.name, status=req.status, version=req.version)
    counts = await service.subject_counts(ConcurrentStableList((role_id,)))
    return ApiResponse.ok(_role_detail(role, builtin=_is_builtin(role), subject_count=counts.get(role_id) or 0))


@router.delete("/{role_id}", dependencies=[_REQUIRE_DELETE])
async def delete_role(role_id: int, uow: UowDep, config: ConfigDep) -> ApiResponse[None]:
    """删除角色（内置保护 + 用户分配保护）。

    Args:
        role_id: 角色主键。
        uow: 请求级工作单元。
        config: 系统参数取数。

    Returns:
        ApiResponse: 统一响应（data 为空）。
    """
    await _role_service(uow, config).delete_role(role_id)
    return ApiResponse.ok(None)


# ------------------------------------------------------------------ 用户分配


@router.get("/{role_id}/users", dependencies=[_REQUIRE_QUERY])
async def list_assigned_users(
    role_id: int,
    query: PageDep,
    uow: UowDep,
    cache: CacheDep,
    kw: KeywordQuery = None,
    status: StatusQuery = None,
) -> ApiResponse[BasePageResponse[AssignedUserItem]]:
    """角色已分配用户列表（同库取用户账号 / 姓名 / 状态）。

    Args:
        role_id: 角色主键。
        query: 分页与排序参数。
        uow: 请求级工作单元。
        cache: 缓存能力域（依赖注入占位）。
        kw: 关键字（用户账号 / 姓名）。
        status: 用户状态（enabled/disabled）。

    Returns:
        ApiResponse: 统一响应，data 为分页用户列表。
    """
    rows, total = await _assign_service(uow, cache).list_assigned(role_id, query, keyword=kw, status=status)
    items = ConcurrentStableList(_assigned_user(row) for row in rows)
    return ApiResponse.ok(BasePageResponse[AssignedUserItem](list=items, total=total, page=query.page, size=query.size))


@router.post("/{role_id}/users", dependencies=[_REQUIRE_GRANT])
async def assign_users(
    role_id: int,
    req: RoleAssignRequest,
    uow: UowDep,
    cache: CacheDep,
    idempotency: IdempotencyDep,
    tenant: TenantDep,
    idempotency_key: IdempotencyKeyHeader = None,
) -> ApiResponse[RoleAssignedUsers]:
    """批量分配用户（幂等 upsert；可按幂等键复用首次结果）。

    Args:
        role_id: 角色主键。
        req: 分配请求（用户主键清单）。
        uow: 请求级工作单元。
        cache: 缓存能力域（权限版本 +1）。
        idempotency: 幂等基座（首次结果复用）。
        tenant: 解析链租户上下文（幂等键作用域位）。
        idempotency_key: 幂等键请求头（可选）。

    Returns:
        ApiResponse: 统一响应，data 为分配后的用户清单。
    """
    service = _assign_service(uow, cache)
    tenant_id = current_tenant_id_str()
    key = build_idempotency_key(key=idempotency_key, tenant=current_tenant_id_of(tenant)) if idempotency_key else ""
    if key and not await idempotency.begin(key):
        payload = await idempotency.load(key)
        if payload is not None:
            return ApiResponse.ok(RoleAssignedUsers.model_validate(payload))
    users = await service.assign_users(role_id, req.user_ids, tenant_id=tenant_id)
    result = RoleAssignedUsers(items=ConcurrentStableList(_assigned_user(row) for row in users))
    if key:
        await idempotency.save(key, result.model_dump(mode="json"))
    return ApiResponse.ok(result)


@router.delete("/{role_id}/users/{user_id}", dependencies=[_REQUIRE_GRANT])
async def unassign_user(role_id: int, user_id: int, uow: UowDep, cache: CacheDep) -> ApiResponse[None]:
    """解绑用户（软删分配行；未分配时幂等无操作）。

    Args:
        role_id: 角色主键。
        user_id: 用户主键。
        uow: 请求级工作单元。
        cache: 缓存能力域（权限版本 +1）。

    Returns:
        ApiResponse: 统一响应（data 为空）。
    """
    await _assign_service(uow, cache).unassign_user(role_id, user_id, tenant_id=current_tenant_id_str())
    return ApiResponse.ok(None)


# ------------------------------------------------------------------ 授权（菜单 / 表单 / 操作）


@router.get("/{role_id}/permissions", dependencies=[_REQUIRE_QUERY])
async def list_permissions(
    role_id: int, uow: UowDep, platform_uow: PlatformUowDep, cache: CacheDep
) -> ApiResponse[RolePermissions]:
    """角色授权条目（菜单 / 表单 / 操作，含来源）。

    Args:
        role_id: 角色主键。
        uow: 请求级工作单元。
        platform_uow: 平台库工作单元（元数据校验器构造，本端点只读）。
        cache: 缓存能力域。

    Returns:
        ApiResponse: 统一响应，data 为授权条目清单。
    """
    rows = await _grant_service(uow, platform_uow, cache).list_permission_entries(role_id)
    return ApiResponse.ok(RolePermissions(items=ConcurrentStableList(_permission_item(row) for row in rows)))


@router.put("/{role_id}/permissions", dependencies=[_REQUIRE_GRANT])
async def replace_permissions(
    role_id: int,
    req: RolePermissionRequest,
    uow: UowDep,
    platform_uow: PlatformUowDep,
    cache: CacheDep,
    idempotency: IdempotencyDep,
    idempotency_key: IdempotencyKeyHeader = None,
) -> ApiResponse[RolePermissions]:
    """全量覆盖角色授权（单事务先删后插；可按幂等键复用首次结果）。

    Args:
        role_id: 角色主键。
        req: 授权全量请求（条目清单）。
        uow: 请求级工作单元。
        platform_uow: 平台库工作单元（授权目标校验）。
        cache: 缓存能力域（权限版本 +1）。
        idempotency: 幂等基座（首次结果复用）。
        idempotency_key: 幂等键请求头（可选）。

    Returns:
        ApiResponse: 统一响应，data 为重建后的授权条目清单。
    """
    service = _grant_service(uow, platform_uow, cache)
    entries = ConcurrentStableList(
        PermissionGrantEntry(perm_type=entry.perm_type, target_id=entry.target_id, source_menu_id=entry.source_menu_id)
        for entry in req.entries
    )
    tenant_id = current_tenant_id_str()
    key = build_idempotency_key(key=idempotency_key, tenant=tenant_id) if idempotency_key else ""
    if key and not await idempotency.begin(key):
        payload = await idempotency.load(key)
        if payload is not None:
            return ApiResponse.ok(RolePermissions.model_validate(payload))
    rows = await service.replace_permissions(role_id, entries, tenant_id=tenant_id)
    result = RolePermissions(items=ConcurrentStableList(_permission_item(row) for row in rows))
    if key:
        await idempotency.save(key, result.model_dump(mode="json"))
    return ApiResponse.ok(result)


# ------------------------------------------------------------------ 字段权限


@router.get("/{role_id}/fields", dependencies=[_REQUIRE_QUERY])
async def list_fields(
    role_id: int, uow: UowDep, platform_uow: PlatformUowDep, cache: CacheDep
) -> ApiResponse[RoleFields]:
    """角色字段权限条目（仅收窄项）。

    Args:
        role_id: 角色主键。
        uow: 请求级工作单元。
        platform_uow: 平台库工作单元（元数据校验器构造，本端点只读）。
        cache: 缓存能力域。

    Returns:
        ApiResponse: 统一响应，data 为字段权限条目清单。
    """
    rows = await _grant_service(uow, platform_uow, cache).list_field_entries(role_id)
    return ApiResponse.ok(RoleFields(items=ConcurrentStableList(_field_item(row) for row in rows)))


@router.put("/{role_id}/fields", dependencies=[_REQUIRE_GRANT])
async def replace_fields(
    role_id: int, req: RoleFieldRequest, uow: UowDep, platform_uow: PlatformUowDep, cache: CacheDep
) -> ApiResponse[RoleFields]:
    """全量覆盖角色字段权限（单事务先删后插）。

    Args:
        role_id: 角色主键。
        req: 字段权限全量请求。
        uow: 请求级工作单元。
        platform_uow: 平台库工作单元（字段归属校验）。
        cache: 缓存能力域（权限版本 +1）。

    Returns:
        ApiResponse: 统一响应，data 为重建后的字段权限条目清单。
    """
    entries = ConcurrentStableList(
        FieldGrantEntry(
            form_id=entry.form_id,
            field_id=entry.field_id,
            visible=entry.visible,
            editable=entry.editable,
            source_menu_id=entry.source_menu_id,
        )
        for entry in req.entries
    )
    rows = await _grant_service(uow, platform_uow, cache).replace_fields(
        role_id, entries, tenant_id=current_tenant_id_str()
    )
    return ApiResponse.ok(RoleFields(items=ConcurrentStableList(_field_item(row) for row in rows)))


# ------------------------------------------------------------------ 数据权限


@router.get("/{role_id}/data-permissions", dependencies=[_REQUIRE_QUERY])
async def list_data_scopes(
    role_id: int, uow: UowDep, platform_uow: PlatformUowDep, cache: CacheDep
) -> ApiResponse[RoleDataScopes]:
    """角色数据权限条目（按字典 × 策略）。

    Args:
        role_id: 角色主键。
        uow: 请求级工作单元。
        platform_uow: 平台库工作单元（元数据校验器构造，本端点只读）。
        cache: 缓存能力域。

    Returns:
        ApiResponse: 统一响应，data 为数据权限条目清单。
    """
    rows = await _grant_service(uow, platform_uow, cache).list_data_scope_entries(role_id)
    return ApiResponse.ok(RoleDataScopes(items=ConcurrentStableList(_data_scope_item(row) for row in rows)))


@router.put("/{role_id}/data-permissions", dependencies=[_REQUIRE_GRANT])
async def replace_data_scopes(
    role_id: int, req: RoleDataScopeRequest, uow: UowDep, platform_uow: PlatformUowDep, cache: CacheDep
) -> ApiResponse[RoleDataScopes]:
    """全量覆盖角色数据权限（单事务先删后插）。

    Args:
        role_id: 角色主键。
        req: 数据权限全量请求。
        uow: 请求级工作单元。
        platform_uow: 平台库工作单元（元数据校验器构造）。
        cache: 缓存能力域（权限版本 +1）。

    Returns:
        ApiResponse: 统一响应，data 为重建后的数据权限条目清单。
    """
    entries = ConcurrentStableList(
        DataScopeGrantEntry(dict_type_id=entry.dict_type_id, policy_type=entry.policy_type, config=entry.config)
        for entry in req.entries
    )
    rows = await _grant_service(uow, platform_uow, cache).replace_data_scopes(
        role_id, entries, tenant_id=current_tenant_id_str()
    )
    return ApiResponse.ok(RoleDataScopes(items=ConcurrentStableList(_data_scope_item(row) for row in rows)))


# ------------------------------------------------------------------ 保存编排（角色本体 + 分配）


@router.put("/{role_id}/assignments", dependencies=[_REQUIRE_GRANT])
async def apply_role_assignments(
    role_id: int,
    req: RoleAssignmentsRequest,
    uow: UowDep,
    config: ConfigDep,
    cache: CacheDep,
    client: ServiceClientDep,
    manager: ManagerDep,
    participant: ParticipantDep,
    checker: CheckerDep,
    idem_key: IdempotencyKeyHeader = None,
) -> ApiResponse[RoleAssignmentsResult]:
    """角色保存编排（分段全量覆盖；跨服务原子）。

    `provider = "xa"` 时经 TM 全局事务（platform 分支进程内 + 组织域分支经参与端点）；
    `provider = null`（dev / test）时顺序提交（platform 本地事务 → 组织域内部写通道）。
    权限码**分段校验**：`role` 段另需 `role:update`（端点级挂 `role:grant`）。

    Args:
        role_id: 角色主键。
        req: 分段全量覆盖请求。
        uow: 请求级工作单元。
        config: 系统参数取数（角色码格式）。
        cache: 缓存能力域（角色 / 分配变更后权限版本递增）。
        client: 服务间调用客户端（组织域分支执行 / 内部写通道）。
        manager: 事务管理器（`provider=null` 时为 Null 实现）。
        participant: 事务参与方（platform 自身分支进程内执行）。
        checker: 权限校验器（`role` 段命令式复校 `role:update`）。
        idem_key: 幂等键请求头（透传给组织域内部写通道）。

    Returns:
        ApiResponse: 统一响应，data 为角色详情、生效后用户清单与本次参与分段名。

    Raises:
        PermissionError: 缺少 `role:update`（30001）。
        ParamError: 未提供任何分段（10001）。
        TransactionUnavailableError: 分支未达 `PREPARED`（10013）。
        ServiceUnavailableError: 跨服务调用失败（10007）。
    """
    if req.role is not None:
        checker.require("role:update")
    session = cast("DbSession", uow.session)
    service = RoleAssignmentsService(
        writer=RoleAssignmentWriter(
            session,
            uow,
            RoleRepository(session),
            UserRoleRepository(session),
            UserRepository(session),
            config,
        ),
        roles=RoleRepository(session),
        users=UserRepository(session),
        user_roles=UserRoleRepository(session),
        cache=cache,
        manager=manager,
        participant=participant,
        client=client,
        tenant_id=current_tenant_id_str(),
    )
    role, users, applied = await service.apply(role_id=role_id, req=req, idempotency_key=idem_key)
    counts = await _role_service(uow, config).subject_counts(ConcurrentStableList((role_id,)))
    detail = _role_detail(role, builtin=_is_builtin(role), subject_count=counts.get(role_id) or 0)
    items = ConcurrentStableList(_assigned_user(row) for row in users)
    return ApiResponse.ok(RoleAssignmentsResult(role=detail, users=RoleAssignedUsers(items=items), applied=applied))
