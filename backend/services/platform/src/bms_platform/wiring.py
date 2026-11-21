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
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.context import get_current_tenant, get_current_user_id
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.help.content import BaseHelpContentResolver
from bms_core.lock.base import BaseDistributedLock
from bms_core.metrics.base import BaseMetrics
from bms_core.models.platform.menu_form import SysField, SysForm
from bms_core.models.platform.permission_meta import SysBusiness
from bms_core.optionset.base import BaseOptionSetRegistry
from bms_core.outbox.base import BaseOutboxStore
from bms_core.permission.field import current_field_permission_provider_factory
from bms_core.permission.resolver import BaseRoleResolver
from bms_core.preference.base import BasePreferenceStore
from bms_core.registry.forms import FormRegistry
from bms_core.servicecall.base import BaseServiceClient
from bms_core.transfer.base import ColumnSpec
from bms_platform.domains.dashboard.repositories.adapters import (
    NotificationBadgeAdapter,
    NullDatasetProbe,
    NullTodoCountProvider,
)
from bms_platform.domains.dashboard.repositories.adapters import (
    RoleQueryAdapter as DashboardRoleQueryAdapter,
)
from bms_platform.domains.dashboard.repositories.card import (
    DashboardCardI18nRepository,
    DashboardCardRepository,
)
from bms_platform.domains.dashboard.repositories.template import DashboardTemplateRepository
from bms_platform.domains.dashboard.services.dashboard import DashboardService
from bms_platform.domains.form_design.repositories.adapters import (
    FieldPermissionAdapter,
    OptionSetAdapter,
    PlatformMetadataAdapter,
    RoleQueryAdapter,
)
from bms_platform.domains.form_design.repositories.field_ext_i18n import FieldExtI18nRepository
from bms_platform.domains.form_design.repositories.layout import (
    FieldAttrRepository,
    FieldExtRepository,
    FormLayoutRepository,
)
from bms_platform.domains.form_design.repositories.metadata import MetadataRepository
from bms_platform.domains.form_design.services.layout import FormDesignService
from bms_platform.domains.form_design.services.validator import LocalFormValidator
from bms_platform.domains.help.services.maintenance import HelpMaintenanceService
from bms_platform.domains.help.services.package_admin import HelpPackageAdminService
from bms_platform.domains.help.services.reader import HelpReaderService
from bms_platform.domains.help.services.statistics import HelpStatisticsService
from bms_platform.domains.menu_form.repositories.menu import (
    ButtonRepository,
    FieldRepository,
    FormRepository,
    MenuFormRepository,
    MenuRepository,
)
from bms_platform.domains.menu_form.services.help_context import HelpContextService
from bms_platform.domains.menu_form.services.help_coverage import HelpCoverageService
from bms_platform.domains.menu_form.services.menu import MenuFormService
from bms_platform.domains.permission_meta.repositories.business import (
    ActionRepository,
    BusinessRepository,
    PermissionRepository,
)
from bms_platform.domains.permission_meta.services.permission_meta import PermissionMetadataService
from bms_platform.domains.role.dto import RoleSummary
from bms_platform.domains.role.ports import (
    RoleAssignmentPort,
    RoleGrantPort,
    RoleQueryPort,
    RoleReferencePort,
    SeparationPort,
)
from bms_platform.domains.role.repositories.reference import MetadataReferenceRepository
from bms_platform.domains.role.repositories.role import RoleRepository, UserRoleRepository
from bms_platform.domains.role.services.permission_subject import DeptPostRoleResolver, DirectRoleResolver
from bms_platform.domains.role.services.role_assignment import RoleAssignmentService
from bms_platform.domains.role.services.role_assignments import RoleAssignmentWriter
from bms_platform.domains.role.services.role_grant_reader import RoleGrantReader
from bms_platform.domains.role.services.role_query import RoleQueryService
from bms_platform.domains.role.services.role_reference import RoleReferenceService
from bms_platform.domains.role.services.separation import SeparationGuard
from bms_platform.domains.user.repositories.user import UserRepository

__all__ = [
    "build_dashboard_role_port",
    "build_dashboard_service",
    "build_form_design_service",
    "build_help_context_service",
    "build_help_coverage_service",
    "build_local_form_validator",
    "build_menu_service",
    "build_permission_service",
    "current_form_role_types",
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
    audit: AuditCapturer | None = None,
) -> PermissionMetadataService:
    """构造权限元数据服务（本域仓储 + 菜单表单 / 角色域的只读探测）。

    Args:
        uow: 请求级工作单元（平台库）。
        outbox: 发件箱存储（保留参数，权限元数据写路径不发布事件）。
        cache: 缓存 Region（元数据版本失效）。
        tenant_session: 租户库会话（角色授权引用探测；None 表示不探测）。
        audit: 字段级审计捕获器（锚点变更显式留痕；None 不留痕）。

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
        audit=audit,
    )


def build_menu_service(
    *,
    uow: UnitOfWork,
    outbox: BaseOutboxStore,
    cache: CacheRegion,
    tenant_session: DbSession | None = None,
    audit: AuditCapturer | None = None,
) -> MenuFormService:
    """构造菜单表单服务（本域仓储 + 权限元数据读取器 + 角色授权引用探测）。

    Args:
        uow: 请求级工作单元（平台库）。
        outbox: 发件箱存储（事件发布）。
        cache: 缓存 Region（元数据快照与版本）。
        tenant_session: 租户库会话（角色授权引用探测；None 表示不探测）。
        audit: 字段级审计捕获器（锚点变更显式留痕；None 不留痕）。

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
        audit=audit,
    )


def build_help_context_service(
    *,
    uow: UnitOfWork,
    cache: CacheRegion,
    resolver: BaseHelpContentResolver,
) -> HelpContextService:
    """构造帮助解析服务（锚点索引回源 + 缓存 + 内容侧端口）。

    Args:
        uow: 请求级工作单元（平台库：五张元数据表）。
        cache: 缓存 Region（锚点索引与元数据版本）。
        resolver: 内容侧解析实现（`[help_content].provider` 装配）。

    Returns:
        HelpContextService: 页面内帮助解析服务实例。
    """
    return HelpContextService(session=cast("DbSession", uow.session), cache=cache, resolver=resolver)


def build_help_coverage_service(*, uow: UnitOfWork, exemption_paths: ConcurrentStableList[str]) -> HelpCoverageService:
    """构造帮助覆盖率台账服务（平台库只读快照 + 豁免文件）。

    Args:
        uow: 请求级工作单元（平台库：元数据五表 + 模块登记 + 锚点）。
        exemption_paths: 豁免文件路径（部署配置）。

    Returns:
        HelpCoverageService: 覆盖率台账服务。
    """
    return HelpCoverageService(session=cast("DbSession", uow.session), exemption_paths=exemption_paths)


def build_help_reader_service(
    *,
    tenant_uow: UnitOfWork,
    cache: CacheRegion,
    locale: str,
    default_locale: str,
) -> HelpReaderService:
    """构造帮助读者面服务。

    Args:
        tenant_uow: 请求级工作单元（租户库：内容表）。
        cache: 缓存 Region（阅读计数去重窗口）。
        locale: 请求语言。
        default_locale: 系统默认语言（请求语言缺行时回退）。

    Returns:
        HelpReaderService: 读者面服务实例。
    """
    return HelpReaderService(
        session=cast("DbSession", tenant_uow.session),
        uow=tenant_uow,
        cache=cache,
        locale=locale,
        default_locale=default_locale,
    )


def build_help_maintenance_service(
    *,
    tenant_uow: UnitOfWork,
    platform_uow: UnitOfWork,
    outbox: BaseOutboxStore,
    cache: CacheRegion,
) -> HelpMaintenanceService:
    """构造帮助内容维护服务。

    Args:
        tenant_uow: 请求级工作单元（租户库：内容表）。
        platform_uow: 请求级工作单元（平台库：锚点清单）。
        outbox: 发件箱存储（事件发布）。
        cache: 缓存 Region（内容版本键）。

    Returns:
        HelpMaintenanceService: 维护服务实例。
    """
    return HelpMaintenanceService(
        session=cast("DbSession", tenant_uow.session),
        platform_session=cast("DbSession", platform_uow.session),
        uow=tenant_uow,
        outbox=outbox,
        cache=cache,
    )


def build_help_statistics_service(*, tenant_uow: UnitOfWork) -> HelpStatisticsService:
    """构造帮助统计视图服务。

    Args:
        tenant_uow: 请求级工作单元（租户库：内容表）。

    Returns:
        HelpStatisticsService: 统计服务实例。
    """
    return HelpStatisticsService(session=cast("DbSession", tenant_uow.session))


def build_help_package_admin_service(
    *,
    tenant_uow: UnitOfWork,
    platform_uow: UnitOfWork,
    cache: CacheRegion,
    root: str,
) -> HelpPackageAdminService:
    """构造帮助包管理服务。

    Args:
        tenant_uow: 请求级工作单元（租户库：内容表）。
        platform_uow: 请求级工作单元（平台库：锚点清单）。
        cache: 缓存 Region（内容版本键）。
        root: 允许装载的根目录（`[help_package].root`）。

    Returns:
        HelpPackageAdminService: 包管理服务实例。
    """
    return HelpPackageAdminService(
        session=cast("DbSession", tenant_uow.session),
        platform_session=cast("DbSession", platform_uow.session),
        uow=tenant_uow,
        cache=cache,
        root=root,
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
    require_dept_post: bool = False,
    metrics: BaseMetrics | None = None,
) -> ConcurrentStableList[BaseRoleResolver]:
    """构造角色解析器组（直接角色 + 岗位/部门链角色）。

    Args:
        session: 租户库会话。
        service_client: 服务间客户端（岗位/部门链角色按能力名取用）。
        require_dept_post: 岗位 / 部门链不可达时是否严格拒绝。
        metrics: 指标记录器（可选）。

    Returns:
        ConcurrentStableList[BaseRoleResolver]: 按执行次序排列的解析器。
    """
    return ConcurrentStableList(
        [
            DirectRoleResolver(UserRoleRepository(session)),
            DeptPostRoleResolver(service_client, require_roles=require_dept_post, metrics=metrics),
        ]
    )


# --------------------------------------------------------------------------- 表单定制（10_01）


async def bind_form_design_resolvers(app: object | None = None) -> None:
    r"""登记表单定制域向外提供的能力回调（应用装配期调用一次）。

    目前一项：**导入列派生**——\`user\` 的导入定义需要「按 user 表单布局取列」，但不得 import
    \`form_design\` 域模型；实现放装配面、经基座回调登记，跨域边界保持单向。

    回调按调用方传入的会话（\`session\` 关键字）查三表，不持有长生命周期会话。
    """
    from bms_core.formdesign.import_columns import layout_columns_of, register_layout_column_resolver
    from bms_core.models.platform.form_design import SysFieldExt, SysFormFieldAttr, SysFormLayout

    async def _resolve(
        *, form_code: str, session: DbSession
    ) -> tuple[ConcurrentStableFrozenList[str], ConcurrentStableDict[str, ColumnSpec]]:
        """按表单取布局字段序与自建字段列规格（回调实现）。

        Args:
            form_code: 表单标识（业务码）。
            session: 调用方会话（租户库）。

        Returns:
            tuple: （字段键序, 自建字段列规格）。
        """
        return await layout_columns_of(
            session,
            form_code=form_code,
            layout_model=SysFormLayout,
            attr_model=SysFormFieldAttr,
            ext_model=SysFieldExt,
        )

    register_layout_column_resolver(_resolve)


class _PlatformMetadataModels(BaseFrameworkObject):
    """平台库表单元数据三表模型集合（装配面注入给 MetadataRepository）。

    装配面是唯一允许跨域的组合点：menu_form（表单 / 字段）与 permission_meta（业务码）的模型
    在此汇聚，域实现只经 models.business/form/field 取用，不 import 他域。
    """

    business = SysBusiness
    """业务码模型（sys_business）。"""
    form = SysForm
    """表单模型（sys_form）。"""
    field = SysField
    """字段模型（sys_field）。"""


def build_form_design_service(
    *,
    tenant_uow: UnitOfWork,
    platform_uow: UnitOfWork,
    cache: CacheRegion,
    outbox: BaseOutboxStore,
    lock: BaseDistributedLock,
    option_set_registry: BaseOptionSetRegistry,
    registry: FormRegistry | None = None,
) -> FormDesignService:
    r"""构造表单定制服务（布局 / 属性 / 自建字段 / 生效解析）。

    **为什么要两个会话**：布局与属性在租户库（\`platform:tenant\` 链），而业务码 / 表单 / 字段在
    平台库（\`platform:platform\` 链）——两者分库，装配面同时持有并把只读面注入本域。

    Args:
        tenant_uow: 请求级工作单元（租户库：布局 / 属性 / 自建字段）。
        platform_uow: 平台库工作单元（只读：业务码 / 表单 / 字段）。
        cache: 缓存 Region（布局 / 字段清单缓存与版本键）。
        outbox: 事务性发件箱（\`sys.form.updated\`）。
        lock: 分布式锁（DDL 单租户串行）。
        option_set_registry: 选项集注册表（属性校验与快照）。
        registry: 表单标识清单（**应用级视图** \`app.state.form_registry\`；None 用构建期清单）。

    Returns:
        FormDesignService: 表单定制服务实例。
    """
    tenant_session = cast("DbSession", tenant_uow.session)
    platform_session = cast("DbSession", platform_uow.session)
    factory = current_field_permission_provider_factory()
    roles = RoleQueryAdapter(RoleQueryService(tenant_session))
    service = FormDesignService(
        session=tenant_session,
        uow=tenant_uow,
        layouts=FormLayoutRepository(tenant_session),
        attrs=FieldAttrRepository(tenant_session),
        ext_fields=FieldExtRepository(tenant_session),
        ext_i18n=FieldExtI18nRepository(tenant_session),
        metadata=PlatformMetadataAdapter(
            MetadataRepository(platform_session, registry=registry, models=_PlatformMetadataModels())
        ),
        permissions=(
            FieldPermissionAdapter(factory(tenant_session, platform_session)) if factory is not None else None
        ),
        option_sets=OptionSetAdapter(option_set_registry),
        roles=roles,
        cache=cache,
        outbox=outbox,
        tenant=get_current_tenant(),
        allow_runtime_ddl=get_settings().app.allow_runtime_ddl,
    )
    return service


async def current_form_role_types(tenant_uow: UnitOfWork) -> ConcurrentStableList[tuple[str, int]]:
    r"""取当前用户的直接角色集（`(role_type, role_id)`；供表单动态校验与渲染同源解析）。

    **为什么放装配面**：角色读面属 `role` 域，`form_design` 域实现不得 import 他域，
    故由装配面构造适配器再取结果，域侧只拿到纯数据。

    Args:
        tenant_uow: 请求级工作单元（租户库：`sys_user_role`）。

    Returns:
        ConcurrentStableList[tuple[str, int]]: 角色类型与主键（未登录为空）。
    """
    user_id = get_current_user_id()
    if user_id is None:
        return ConcurrentStableList()
    session = cast("DbSession", tenant_uow.session)
    return await RoleQueryAdapter(RoleQueryService(session)).roles_of_user(user_id)


def build_local_form_validator(
    *,
    tenant_uow: UnitOfWork,
    platform_uow: UnitOfWork,
    option_set_registry: BaseOptionSetRegistry,
    registry: FormRegistry | None = None,
    role_types: ConcurrentStableList[tuple[str, int]] | None = None,
) -> LocalFormValidator:
    """构造表单动态校验真实实现（按生效布局 / 属性校验）。

    Args:
        tenant_uow: 请求级工作单元（租户库）。
        platform_uow: 平台库工作单元（只读元数据）。
        option_set_registry: 选项集注册表（值域判定）。
        registry: 表单标识清单（None 用构建期清单）。
        role_types: 当前用户角色集（`(role_type, role_id)`；None 表示无角色视图）。

    Returns:
        LocalFormValidator: 校验器实例。
    """
    tenant_session = cast("DbSession", tenant_uow.session)
    platform_session = cast("DbSession", platform_uow.session)
    factory = current_field_permission_provider_factory()
    return LocalFormValidator(
        session=tenant_session,
        layouts=FormLayoutRepository(tenant_session),
        attrs=FieldAttrRepository(tenant_session),
        ext_fields=FieldExtRepository(tenant_session),
        metadata=PlatformMetadataAdapter(
            MetadataRepository(platform_session, registry=registry, models=_PlatformMetadataModels())
        ),
        option_sets=OptionSetAdapter(option_set_registry),
        field_permissions=factory(tenant_session, platform_session) if factory is not None else None,
        role_types=role_types,
    )


# --------------------------------------------------------------------------- 首页工作台（11_01）


def build_dashboard_role_port(tenant_uow: UnitOfWork) -> DashboardRoleQueryAdapter[RoleSummary]:
    """构造工作台角色读面端口（角色域实现只在装配面出现）。

    **为什么单独出口**：路由的「当前用户角色集」依赖也需要角色读面，域内不得 import 他域实现，
    由装配面构造后以端口形态注入。

    Args:
        tenant_uow: 请求级工作单元（租户库）。

    Returns:
        DashboardRoleQueryAdapter[RoleSummary]: 角色读面端口实现。
    """
    return DashboardRoleQueryAdapter[RoleSummary](RoleQueryService(cast("DbSession", tenant_uow.session)))


def build_dashboard_service(
    *,
    tenant_uow: UnitOfWork,
    cache: CacheRegion,
    preferences: BasePreferenceStore,
    service_client: BaseServiceClient,
) -> DashboardService:
    """构造首页工作台服务（卡片 / 模板 / 布局 / 角标）。

    **为什么在装配面构造**：角色读面属 `role` 域、未读角标属通知服务、待办与数据集属未落地能力——
    域实现不得 import 他域实现，由装配面注入端口实现（依赖方向恒为「装配 → 域」）。

    Args:
        tenant_uow: 请求级工作单元（租户库：卡片 / 模板）。
        cache: 缓存 Region（卡片清单与解析结构）。
        preferences: 用户偏好存储（个人布局）。
        service_client: 服务间调用客户端（通知服务内部未读端点）。

    Returns:
        DashboardService: 首页工作台服务实例。
    """
    session = cast("DbSession", tenant_uow.session)
    return DashboardService(
        session=session,
        uow=tenant_uow,
        cards=DashboardCardRepository(session),
        card_i18n=DashboardCardI18nRepository(session),
        templates=DashboardTemplateRepository(session),
        preferences=preferences,
        roles=DashboardRoleQueryAdapter[RoleSummary](RoleQueryService(session)),
        todo=NullTodoCountProvider(),
        notifications=NotificationBadgeAdapter(client=service_client),
        datasets=NullDatasetProbe(),
        cache=cache,
        tenant=get_current_tenant(),
    )
