"""平台服务域装配：按请求级会话构造业务域服务（跨域只读面在此注入）。

**为什么单独一层**：`MenuFormService` 需要权限元数据（业务码 / 动作码 / 权限码）构建快照、
`PermissionMetadataService` 需要按钮 / 表单挂接与角色授权引用做删除前置校验——两侧若直接互相 import
会形成域间环。装配面同时依赖两侧，域实现只依赖 Protocol（依赖方向恒为「装配 → 域」）。

本模块属**装配面**（`shared_paths`），不承载业务规则。
"""

from typing import cast

from bms_core.audit.base import AuditCapturer
from bms_core.cache.base import CacheRegion
from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.metrics.base import BaseMetrics
from bms_core.outbox.base import BaseOutboxStore
from bms_core.permission.resolver import BaseRoleResolver
from bms_core.servicecall.base import BaseServiceClient
from bms_platform.domains.menu_form.repositories.menu import (
    ButtonRepository,
    FieldRepository,
    FormRepository,
    MenuFormRepository,
    MenuRepository,
)
from bms_platform.domains.menu_form.services.menu import MenuFormService
from bms_platform.domains.permission_meta.repositories.business import (
    ActionRepository,
    BusinessRepository,
    PermissionRepository,
)
from bms_platform.domains.permission_meta.services.permission_meta import PermissionMetadataService
from bms_platform.domains.role.ports import (
    RoleAssignmentPort,
    RoleGrantPort,
    RoleQueryPort,
    RoleReferencePort,
    SeparationPort,
)
from bms_platform.domains.role.repositories.reference import MetadataReferenceRepository
from bms_platform.domains.role.repositories.role import RoleRepository, UserRoleRepository
from bms_platform.domains.role.services.permission_subject import DirectRoleResolver, OrgRoleResolver
from bms_platform.domains.role.services.role_assignment import RoleAssignmentService
from bms_platform.domains.role.services.role_assignments import RoleAssignmentWriter
from bms_platform.domains.role.services.role_grant_reader import RoleGrantReader
from bms_platform.domains.role.services.role_query import RoleQueryService
from bms_platform.domains.role.services.role_reference import RoleReferenceService
from bms_platform.domains.role.services.separation import SeparationGuard
from bms_platform.domains.user.repositories.user import UserRepository

__all__ = [
    "build_menu_service",
    "build_permission_service",
    "role_assignment",
    "role_assignment_writer",
    "role_grant",
    "role_query",
    "role_reference",
    "role_resolvers",
    "separation_guard",
]


def build_permission_service(
    *,
    uow: UnitOfWork,
    outbox: BaseOutboxStore,
    cache: CacheRegion,
    tenant_session: DbSession | None = None,
) -> PermissionMetadataService:
    """构造权限元数据服务（本域仓储 + 菜单表单 / 角色域的只读探测）。

    Args:
        uow: 请求级工作单元（平台库）。
        outbox: 发件箱存储（保留参数，权限元数据写路径不发布事件）。
        cache: 缓存 Region（元数据版本失效）。
        tenant_session: 租户库会话（角色授权引用探测；None 表示不探测）。

    Returns:
        PermissionMetadataService: 权限元数据服务实例。
    """
    session = cast("DbSession", uow.session)
    return PermissionMetadataService(
        uow=uow,
        businesses=BusinessRepository(session),
        actions=ActionRepository(session),
        permissions=PermissionRepository(session),
        buttons=ButtonRepository(session),
        forms=FormRepository(session),
        cache=cache,
        references=MetadataReferenceRepository(tenant_session) if tenant_session is not None else None,
    )


def build_menu_service(
    *,
    uow: UnitOfWork,
    outbox: BaseOutboxStore,
    cache: CacheRegion,
    tenant_session: DbSession | None = None,
) -> MenuFormService:
    """构造菜单表单服务（本域仓储 + 权限元数据读取器 + 角色授权引用探测）。

    Args:
        uow: 请求级工作单元（平台库）。
        outbox: 发件箱存储（事件发布）。
        cache: 缓存 Region（元数据快照与版本）。
        tenant_session: 租户库会话（角色授权引用探测；None 表示不探测）。

    Returns:
        MenuFormService: 菜单表单服务实例。
    """
    session = cast("DbSession", uow.session)
    return MenuFormService(
        uow=uow,
        businesses=BusinessRepository(session),
        actions=ActionRepository(session),
        permissions=PermissionRepository(session),
        menus=MenuRepository(session),
        forms=FormRepository(session),
        menu_forms=MenuFormRepository(session),
        buttons=ButtonRepository(session),
        fields=FieldRepository(session),
        outbox=outbox,
        cache=cache,
        references=MetadataReferenceRepository(tenant_session) if tenant_session is not None else None,
    )


def role_query(session: DbSession) -> RoleQueryPort:
    """构造角色读面（单条 / 批量 / 按码）。

    Args:
        session: 租户库会话。

    Returns:
        RoleQueryPort: 角色读面。
    """
    return RoleQueryService(session)


def role_assignment(session: DbSession, *, guard: SeparationPort | None = None) -> RoleAssignmentPort:
    """构造用户 × 角色分配服务（写回角色域执行）。

    Args:
        session: 租户库会话。
        guard: 三权分立校验器（None 时不做互斥校验）。

    Returns:
        RoleAssignmentPort: 角色分配服务。
    """
    return RoleAssignmentService(session, guard=guard)


def role_assignment_writer(
    *,
    session: DbSession,
    uow: UnitOfWork,
    users: UserRepository,
    config: BaseConfigSource,
    guard: SeparationGuard | None = None,
) -> RoleAssignmentWriter:
    """构造角色保存写入器（角色本体 + 角色 × 用户全量覆盖）。

    Args:
        session: 会话（分支同步会话或请求会话）。
        uow: 工作单元。
        users: 用户仓储（同域内使用；分配主体有效性校验）。
        config: 系统参数取数（角色码格式）。
        guard: 三权分立校验器（None 时不做互斥校验）。

    Returns:
        RoleAssignmentWriter: 角色保存写入器。
    """
    return RoleAssignmentWriter(
        session,
        uow,
        RoleRepository(session),
        UserRoleRepository(session),
        users,
        config,
        guard,
    )


def role_grant(session: DbSession) -> RoleGrantPort:
    """构造角色授权读面（授权条目 / 数据范围 / 角色类型映射）。

    Args:
        session: 租户库会话。

    Returns:
        RoleGrantPort: 授权读面。
    """
    return RoleGrantReader(session)


def role_reference(session: DbSession) -> RoleReferencePort:
    """构造角色引用面（字典数据源用）。

    Args:
        session: 租户库会话。

    Returns:
        RoleReferencePort: 角色引用面。
    """
    return RoleReferenceService(session)


def separation_guard(session: DbSession, *, audit: AuditCapturer | None = None) -> SeparationGuard:
    """构造三权分立校验器。

    Args:
        session: 租户库会话。
        audit: 审计捕获器（None 时不产生审计事件）。

    Returns:
        SeparationGuard: 三权分立校验器（结构上满足 `SeparationPort`，跨域消费方按协议使用）。
    """
    return SeparationGuard(roles=RoleRepository(session), user_roles=UserRoleRepository(session), audit=audit)


def role_resolvers(
    session: DbSession,
    *,
    service_client: BaseServiceClient,
    require_org: bool = False,
    metrics: BaseMetrics | None = None,
) -> ConcurrentStableList[BaseRoleResolver]:
    """构造角色解析器组（直接角色 + 组织链角色）。

    Args:
        session: 租户库会话。
        service_client: 服务间客户端（组织链角色按能力名取用）。
        require_org: 组织链不可达时是否严格拒绝。
        metrics: 指标记录器（可选）。

    Returns:
        ConcurrentStableList[BaseRoleResolver]: 按执行次序排列的解析器。
    """
    return ConcurrentStableList(
        [
            DirectRoleResolver(UserRoleRepository(session)),
            OrgRoleResolver(service_client, require_roles=require_org, metrics=metrics),
        ]
    )
