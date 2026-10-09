"""平台服务管理端点：`/api/v1/users`（用户列表 / CRUD / 启停 / 重置密码 / 角色查看）。

- **鉴权**：模块级 `require_auth`（登录态）；各端点挂 `require_permission("user:*")`
  （`02_04` 起为真实 RBAC 校验器；内置系统管理员的 `user:*` 授权见 `ops/seed_rbac.py`）；
- **同库**：`sys_user` / `sys_user_role` / `sys_role` / `sys_account_lock` 全在 **platform 服务租户库**；
- **跨服务**：会话失效经 identity 内部端点（`services/user_sessions.py`，提交后调用、失败不阻断）；
- **不含**：组织字段（部门 / 岗位，归 mdm，需求 `07-11`）、`locale` / `timezone`（个人中心）、
  SSO 身份绑定查看（identity 服务既有端点 `GET /api/v1/users/{id}/identities`，权限码 `sso:bind`）；
- **留痕**：写操作接 `AuditCapturer` 占位（真实落库随审计阶段）+ 事务性发件箱发射 `sys.user.*`；
- **契约**：计入 platform 公开契约（`deploy/contracts/platform.json`）。
"""

from typing import Annotated, cast

from fastapi import Depends, Header, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import (
    get_audit_capturer,
    get_cache_region,
    get_idempotency_store,
    get_outbox_store,
    get_password_hasher,
    get_password_policy,
    get_service_client,
    get_uow,
)
from bms_core.audit.base import AuditCapturer
from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.context import current_user_id
from bms_core.core.exceptions import ConflictError, ParamError
from bms_core.db.session import DbSession
from bms_core.db.tenant import current_tenant_id_str
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.idempotency.base import IDEMPOTENCY_HEADER, IdempotencyStore, build_idempotency_key
from bms_core.outbox.base import BaseOutboxStore
from bms_core.password.base import BasePasswordPolicy
from bms_core.permission.base import BasePermissionChecker, get_permission_checker, require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery, BasePageResponse
from bms_core.security.base import BasePasswordHasher
from bms_core.servicecall.base import BaseServiceClient
from bms_core.transaction.base import (
    BaseTransactionManager,
    BaseTransactionParticipant,
    get_transaction_manager,
    get_transaction_participant,
)
from bms_platform.models.role import SysRole
from bms_platform.models.user import SysUser
from bms_platform.repositories.account_lock import AccountLockRepository
from bms_platform.repositories.role import RoleRepository, UserRoleRepository
from bms_platform.repositories.user import UserRepository
from bms_platform.schemas.users import (
    UserAdminCreateRequest,
    UserAdminCreateResult,
    UserAssignmentsRequest,
    UserAssignmentsResult,
    UserDeleteResult,
    UserDetail,
    UserItem,
    UserPasswordResetRequest,
    UserPasswordResetResult,
    UserRoleItem,
    UserRoleList,
    UserStatus,
    UserStatusResult,
    UserStatusUpdateRequest,
    UserUpdateRequest,
)
from bms_platform.services.user_assignments import UserAssignmentsService, UserAssignmentWriter
from bms_platform.services.user_sessions import UserSessionClient
from bms_platform.services.users import USER_STATUSES, UserQueryService
from bms_platform.services.users_admin import UserAdminService

router = BaseRouter(
    key="platform_users",
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_auth)],
)

UowDep = Annotated[UnitOfWork, Depends(get_uow)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
HasherDep = Annotated[BasePasswordHasher, Depends(get_password_hasher)]
PolicyDep = Annotated[BasePasswordPolicy, Depends(get_password_policy)]
OutboxDep = Annotated[BaseOutboxStore, Depends(get_outbox_store)]
ServiceClientDep = Annotated[BaseServiceClient, Depends(get_service_client)]
IdempotencyDep = Annotated[IdempotencyStore, Depends(get_idempotency_store)]
AuditDep = Annotated[AuditCapturer, Depends(get_audit_capturer)]
CacheDep = Annotated[CacheRegion, Depends(get_cache_region)]
ManagerDep = Annotated[BaseTransactionManager, Depends(get_transaction_manager)]
ParticipantDep = Annotated[BaseTransactionParticipant, Depends(get_transaction_participant)]
CheckerDep = Annotated[BasePermissionChecker, Depends(get_permission_checker)]
IdempotencyKeyHeader = Annotated[str | None, Header(alias=IDEMPOTENCY_HEADER)]
KeywordQuery = Annotated[str | None, Query(description="关键字（用户名/姓名/邮箱/手机号，大小写不敏感）")]
StatusQuery = Annotated[str | None, Query(description="账号状态（enabled/disabled）")]

_TABLE = "sys_user"

_REQUIRE_QUERY = Depends(require_permission("user:query"))
_REQUIRE_CREATE = Depends(require_permission("user:create"))
_REQUIRE_UPDATE = Depends(require_permission("user:update"))
_REQUIRE_DELETE = Depends(require_permission("user:delete"))
_REQUIRE_RESET_PWD = Depends(require_permission("user:reset_pwd"))
_REQUIRE_ASSIGN_ROLE = Depends(require_permission("user:assign_role"))


def _build_service(
    uow: UowDep,
    hasher: HasherDep,
    policy: PolicyDep,
    outbox: OutboxDep,
    client: ServiceClientDep,
) -> UserAdminService:
    """构造用户完整域服务（请求级会话与依赖）。

    Args:
        uow: 请求级工作单元。
        hasher: 口令哈希器。
        policy: 密码策略。
        outbox: 事务性发件箱存储。
        client: 服务间调用客户端（会话失效）。

    Returns:
        UserAdminService: 用户完整域服务实例。
    """
    session = cast("DbSession", uow.session)
    return UserAdminService(
        session,
        uow,
        UserRepository(session),
        UserRoleRepository(session),
        RoleRepository(session),
        AccountLockRepository(session),
        hasher,
        policy,
        outbox,
        UserSessionClient(client),
    )


def _require_status(status: str | None) -> None:
    """校验状态筛选值。

    Args:
        status: 状态（可空）。

    Raises:
        ParamError: 取值非法（10001）。
    """
    if status is not None and status not in USER_STATUSES:
        raise ParamError(f"账号状态非法：{status}")


def _to_item(row: SysUser) -> UserItem:
    """用户记录 → 列表行。

    Args:
        row: 用户记录。

    Returns:
        UserItem: 列表行。
    """
    return UserItem(
        id=row.id,
        username=row.username,
        name=row.name,
        status=cast("UserStatus", row.status),
        last_login_at=row.last_login_at,
    )


def _to_detail(row: SysUser) -> UserDetail:
    """用户记录 → 详情。

    Args:
        row: 用户记录。

    Returns:
        UserDetail: 用户详情（联系方式按脱敏标记掩码）。
    """
    return UserDetail(
        id=row.id,
        username=row.username,
        name=row.name,
        status=cast("UserStatus", row.status),
        email=row.email,
        phone=row.phone,
        last_login_at=row.last_login_at,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_role_item(role: SysRole) -> UserRoleItem:
    """角色记录 → 用户直接角色行。

    Args:
        role: 角色记录。

    Returns:
        UserRoleItem: 角色行。
    """
    return UserRoleItem(role_id=role.id, role_code=role.code, role_name=role.name, role_type=role.role_type)


def _read_cached_user_id(payload: object) -> int | None:
    """读取幂等首次结果中的 `user_id`。

    Args:
        payload: 幂等存储载荷。

    Returns:
        int | None: 首次建号的用户主键；无法解析为 None。
    """
    if not isinstance(payload, dict):
        return None
    raw = cast("dict[str, object]", payload).get("user_id")
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    return None


@router.get("", dependencies=[_REQUIRE_QUERY])
async def list_users(
    query: PageDep,
    uow: UowDep,
    kw: KeywordQuery = None,
    status: StatusQuery = None,
) -> ApiResponse[BasePageResponse[UserItem]]:
    """用户列表（关键字「用户名 / 姓名 / 邮箱 / 手机号」+ 状态筛选 + 分页）。

    Args:
        query: 分页与排序参数。
        uow: 请求级工作单元。
        kw: 关键字（四字段模糊，大小写不敏感）。
        status: 账号状态（enabled/disabled）。

    Returns:
        ApiResponse: 统一响应，data 为分页用户列表。
    """
    _require_status(status)
    service = UserQueryService(UserRepository(cast("DbSession", uow.session)))
    rows, total = await service.list_users(query, keyword=kw, status=status)
    items = ConcurrentStableList(_to_item(row) for row in rows)
    return ApiResponse.ok(BasePageResponse[UserItem](list=items, total=total, page=query.page, size=query.size))


@router.post("", dependencies=[_REQUIRE_CREATE])
async def create_user(
    req: UserAdminCreateRequest,
    uow: UowDep,
    hasher: HasherDep,
    policy: PolicyDep,
    outbox: OutboxDep,
    client: ServiceClientDep,
    idempotency: IdempotencyDep,
    audit: AuditDep,
    idem_key: IdempotencyKeyHeader = None,
) -> ApiResponse[UserAdminCreateResult]:
    """新建用户（初始密码可选；支持 `Idempotency-Key` 幂等）。

    Args:
        req: 新建用户请求。
        uow: 请求级工作单元。
        hasher: 口令哈希器。
        policy: 密码策略。
        outbox: 事务性发件箱存储。
        client: 服务间调用客户端。
        idempotency: 幂等存储。
        audit: 审计捕获（占位）。
        idem_key: 幂等键请求头。

    Returns:
        ApiResponse: 统一响应，data 为新建用户详情与（后端生成的）初始密码。

    Raises:
        ConflictError: 同一幂等键的首个请求仍在处理中（10003）。
        UsernameExistsError: 用户名已存在（30003）。
    """
    key = build_idempotency_key(key=idem_key, tenant=current_tenant_id_str()) if idem_key else None
    service = _build_service(uow, hasher, policy, outbox, client)
    if key is not None and not await idempotency.begin(key):
        cached_id = _read_cached_user_id(await idempotency.load(key))
        if cached_id is None:
            raise ConflictError("同一幂等键的请求正在处理中，请稍后重试")
        return ApiResponse.ok(UserAdminCreateResult(user=_to_detail(await service.get_user(cached_id))))
    user, initial_password = await service.create_user(
        username=req.username,
        name=req.name,
        password=req.password,
        pwd_reset_required=req.pwd_reset_required,
        email=req.email,
        phone=req.phone,
        status=req.status,
    )
    if key is not None:
        await idempotency.save(key, {"user_id": user.id})
    audit.capture(table=_TABLE, model_id=user.id, changes=ConcurrentStableList(), actor=current_user_id.get())
    return ApiResponse.ok(UserAdminCreateResult(user=_to_detail(user), initial_password=initial_password))


@router.get("/{user_id}", dependencies=[_REQUIRE_QUERY])
async def get_user_detail(
    user_id: int,
    uow: UowDep,
    hasher: HasherDep,
    policy: PolicyDep,
    outbox: OutboxDep,
    client: ServiceClientDep,
) -> ApiResponse[UserDetail]:
    """用户详情（含联系方式与乐观锁版本）。

    Args:
        user_id: 用户主键。
        uow: 请求级工作单元。
        hasher: 口令哈希器（服务构造用）。
        policy: 密码策略（服务构造用）。
        outbox: 发件箱（服务构造用）。
        client: 服务间调用客户端（服务构造用）。

    Returns:
        ApiResponse: 统一响应，data 为用户详情。
    """
    user = await _build_service(uow, hasher, policy, outbox, client).get_user(user_id)
    return ApiResponse.ok(_to_detail(user))


@router.put("/{user_id}", dependencies=[_REQUIRE_UPDATE])
async def update_user(
    user_id: int,
    req: UserUpdateRequest,
    uow: UowDep,
    hasher: HasherDep,
    policy: PolicyDep,
    outbox: OutboxDep,
    client: ServiceClientDep,
    audit: AuditDep,
) -> ApiResponse[UserDetail]:
    """修改用户基本资料（昵称 / 邮箱 / 手机；乐观锁）。

    Args:
        user_id: 用户主键。
        req: 修改请求。
        uow: 请求级工作单元。
        hasher: 口令哈希器（服务构造用）。
        policy: 密码策略（服务构造用）。
        outbox: 发件箱（服务构造用）。
        client: 服务间调用客户端（服务构造用）。
        audit: 审计捕获（占位）。

    Returns:
        ApiResponse: 统一响应，data 为更新后的用户详情。
    """
    user = await _build_service(uow, hasher, policy, outbox, client).update_user(
        user_id,
        name=req.name,
        email=req.email,
        phone=req.phone,
        version=req.version,
    )
    audit.capture(table=_TABLE, model_id=user.id, changes=ConcurrentStableList(), actor=current_user_id.get())
    return ApiResponse.ok(_to_detail(user))


@router.put("/{user_id}/status", dependencies=[_REQUIRE_UPDATE])
async def update_user_status(
    user_id: int,
    req: UserStatusUpdateRequest,
    uow: UowDep,
    hasher: HasherDep,
    policy: PolicyDep,
    outbox: OutboxDep,
    client: ServiceClientDep,
    audit: AuditDep,
) -> ApiResponse[UserStatusResult]:
    """启用 / 停用账号（停用即时失效该用户全部会话）。

    Args:
        user_id: 用户主键。
        req: 状态请求。
        uow: 请求级工作单元。
        hasher: 口令哈希器（服务构造用）。
        policy: 密码策略（服务构造用）。
        outbox: 发件箱（服务构造用）。
        client: 服务间调用客户端（会话失效）。
        audit: 审计捕获（占位）。

    Returns:
        ApiResponse: 统一响应，data 为更新后的用户详情与会话撤销结果。
    """
    user, revoked = await _build_service(uow, hasher, policy, outbox, client).update_status(user_id, status=req.status)
    audit.capture(table=_TABLE, model_id=user.id, changes=ConcurrentStableList(), actor=current_user_id.get())
    return ApiResponse.ok(UserStatusResult(user=_to_detail(user), session_revoked=revoked))


@router.delete("/{user_id}", dependencies=[_REQUIRE_DELETE])
async def delete_user(
    user_id: int,
    uow: UowDep,
    hasher: HasherDep,
    policy: PolicyDep,
    outbox: OutboxDep,
    client: ServiceClientDep,
    audit: AuditDep,
) -> ApiResponse[UserDeleteResult]:
    """软删除用户（引用校验 + 关闭未解锁锁定记录 + 失效全部会话）。

    Args:
        user_id: 用户主键。
        uow: 请求级工作单元。
        hasher: 口令哈希器（服务构造用）。
        policy: 密码策略（服务构造用）。
        outbox: 发件箱（服务构造用）。
        client: 服务间调用客户端（会话失效）。
        audit: 审计捕获（占位）。

    Returns:
        ApiResponse: 统一响应，data 为删除与会话撤销结果。
    """
    revoked = await _build_service(uow, hasher, policy, outbox, client).delete_user(user_id)
    audit.capture(table=_TABLE, model_id=user_id, changes=ConcurrentStableList(), actor=current_user_id.get())
    return ApiResponse.ok(UserDeleteResult(deleted=True, session_revoked=revoked))


@router.put("/{user_id}/password", dependencies=[_REQUIRE_RESET_PWD])
async def reset_user_password(
    user_id: int,
    req: UserPasswordResetRequest,
    uow: UowDep,
    hasher: HasherDep,
    policy: PolicyDep,
    outbox: OutboxDep,
    client: ServiceClientDep,
    audit: AuditDep,
) -> ApiResponse[UserPasswordResetResult]:
    """重置密码（策略校验 + 强制首登改密 + 失效全部会话）。

    Args:
        user_id: 用户主键。
        req: 重置密码请求。
        uow: 请求级工作单元。
        hasher: 口令哈希器。
        policy: 密码策略。
        outbox: 发件箱（服务构造用）。
        client: 服务间调用客户端（会话失效）。
        audit: 审计捕获（占位）。

    Returns:
        ApiResponse: 统一响应，data 为重置与会话撤销结果。
    """
    revoked = await _build_service(uow, hasher, policy, outbox, client).reset_password(
        user_id, new_password=req.new_password, force_change=req.force_change
    )
    audit.capture(table=_TABLE, model_id=user_id, changes=ConcurrentStableList(), actor=current_user_id.get())
    return ApiResponse.ok(UserPasswordResetResult(reset=True, session_revoked=revoked))


@router.get("/{user_id}/roles", dependencies=[_REQUIRE_QUERY])
async def list_user_roles(
    user_id: int,
    uow: UowDep,
    hasher: HasherDep,
    policy: PolicyDep,
    outbox: OutboxDep,
    client: ServiceClientDep,
) -> ApiResponse[UserRoleList]:
    """查看该用户直接绑定的角色（只读；维护归角色管理）。

    Args:
        user_id: 用户主键。
        uow: 请求级工作单元。
        hasher: 口令哈希器（服务构造用）。
        policy: 密码策略（服务构造用）。
        outbox: 发件箱（服务构造用）。
        client: 服务间调用客户端（服务构造用）。

    Returns:
        ApiResponse: 统一响应，data 为直接角色清单。
    """
    roles = await _build_service(uow, hasher, policy, outbox, client).list_user_roles(user_id)
    items = ConcurrentStableList(_to_role_item(role) for role in roles)
    return ApiResponse.ok(UserRoleList(items=items))


@router.put("/{user_id}/assignments", dependencies=[_REQUIRE_ASSIGN_ROLE])
async def apply_user_assignments(
    user_id: int,
    req: UserAssignmentsRequest,
    uow: UowDep,
    hasher: HasherDep,
    policy: PolicyDep,
    outbox: OutboxDep,
    client: ServiceClientDep,
    cache: CacheDep,
    manager: ManagerDep,
    participant: ParticipantDep,
    checker: CheckerDep,
    audit: AuditDep,
    idem_key: IdempotencyKeyHeader = None,
) -> ApiResponse[UserAssignmentsResult]:
    """用户保存编排（分段全量覆盖；跨服务原子）。

    `provider = "xa"` 时经 TM 全局事务（platform 分支进程内 + 组织域分支经参与端点）；
    `provider = null`（dev / test）时顺序提交（platform 本地事务 → 组织域内部写通道）。
    权限码**分段校验**：`profile` 段另需 `user:update`。

    Args:
        user_id: 用户主键。
        req: 分段全量覆盖请求。
        uow: 请求级工作单元。
        hasher: 口令哈希器（占位：保持构造口径一致）。
        policy: 密码策略（占位）。
        outbox: 事务性发件箱存储。
        client: 服务间调用客户端（组织域分支执行 / 内部写通道；提交后会话失效）。
        cache: 缓存能力域（角色分配变更后权限版本递增）。
        manager: 事务管理器（`provider=null` 时为 Null 实现）。
        participant: 事务参与方（platform 自身分支进程内执行）。
        checker: 权限校验器（`profile` 段命令式复校）。
        audit: 审计捕获（占位）。
        idem_key: 幂等键请求头（透传给组织域内部写通道）。

    Returns:
        ApiResponse: 统一响应，data 为用户详情、生效后角色清单与本次参与分段名。

    Raises:
        PermissionError: 缺少 `user:update`（30001）。
        ParamError: 未提供任何分段 / 主要项不在集合内（10001）。
        TransactionUnavailableError: 分支未达 `PREPARED`（10013）。
        ServiceUnavailableError: 跨服务调用失败（10007）。
    """
    if req.profile is not None:
        checker.require("user:update")
    session = cast("DbSession", uow.session)
    service = UserAssignmentsService(
        writer=UserAssignmentWriter(
            session, uow, UserRepository(session), UserRoleRepository(session), RoleRepository(session), outbox
        ),
        user_roles=UserRoleRepository(session),
        roles=RoleRepository(session),
        users=UserRepository(session),
        sessions=UserSessionClient(client),
        cache=cache,
        manager=manager,
        participant=participant,
        client=client,
        tenant_id=current_tenant_id_str(),
    )
    user, roles, applied = await service.apply(user_id=user_id, req=req, idempotency_key=idem_key)
    audit.capture(table=_TABLE, model_id=user.id, changes=ConcurrentStableList(), actor=current_user_id.get())
    items = ConcurrentStableList(_to_role_item(role) for role in roles)
    return ApiResponse.ok(
        UserAssignmentsResult(user=_to_detail(user), roles=UserRoleList(items=items), applied=applied)
    )
