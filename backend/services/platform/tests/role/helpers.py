"""角色域服务级用例共用夹具（Kiwi 2248）：临时 SQLite 会话与服务构造。

角色 / 授权表（platform 租户库）与授权目标元数据（菜单元数据）、字典表在测试中共用同一临时库
（同构于生产「同服务跨库」口径下的校验路径）。
"""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.audit.base import AuditCapturer
from bms_core.cache.memory import MemoryCacheRegion
from bms_core.config.null import NullConfigSource
from bms_core.core.config import Settings
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.models.platform.role import SysRole
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.repositories.menu import (
    ActionRepository,
    BusinessRepository,
    FieldRepository,
    FormRepository,
    MenuRepository,
    PermissionRepository,
)
from bms_platform.repositories.role import (
    DataScopeRepository,
    RoleFieldRepository,
    RolePermissionRepository,
    RoleRepository,
    UserRoleRepository,
)
from bms_platform.repositories.user import UserRepository
from bms_platform.services.role import RoleService
from bms_platform.services.role_assign import RoleAssignService
from bms_platform.services.role_grant import MenuMetadataChecker, RoleGrantService
from bms_platform.services.separation import RoleBusinessPermissions, SeparationGuard


async def session() -> tuple[AsyncSession, AsyncEngine]:
    """建临时 SQLite 会话并建齐用例所需表。

    Returns:
        tuple[AsyncSession, AsyncEngine]: (会话, 引擎)。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SysRole.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory(), engine


async def commit(target: AsyncSession) -> None:
    """结束当前事务（服务方法经 `uow.begin()` 自行开事务；测试侧读断言后须清事务）。

    Args:
        target: 会话。
    """
    await target.commit()


def page(*, page_num: int = 1, size: int = 20) -> BasePageQuery:
    """构造分页请求。

    Args:
        page_num: 页码（从 1 起）。
        size: 每页条数。

    Returns:
        BasePageQuery: 分页请求。
    """
    return BasePageQuery(page=page_num, size=size)


def role_service(target: AsyncSession) -> RoleService:
    """构造角色服务。

    Args:
        target: 会话。

    Returns:
        RoleService: 角色服务。
    """
    return RoleService(RoleRepository(target), UserRoleRepository(target), DbUnitOfWork(target), NullConfigSource())


def assign_service(
    target: AsyncSession, cache: MemoryCacheRegion | None = None, *, guard: SeparationGuard | None = None
) -> RoleAssignService:
    """构造角色分配服务。

    Args:
        target: 会话。
        cache: 缓存 Region（缺省新建内存实现）。
        guard: 三权分立校验器（缺省不校验，`03_02` 专项用例显式传入）。

    Returns:
        RoleAssignService: 角色分配服务。
    """
    return RoleAssignService(
        RoleRepository(target),
        UserRoleRepository(target),
        UserRepository(target),
        DbUnitOfWork(target),
        cache or MemoryCacheRegion(),
        guard,
    )


def grant_service(
    target: AsyncSession,
    cache: MemoryCacheRegion | None = None,
    *,
    guard: SeparationGuard | None = None,
    settings: Settings | None = None,
) -> RoleGrantService:
    """构造角色授权服务。

    Args:
        target: 会话。
        cache: 缓存 Region（缺省新建内存实现）。
        guard: 三权分立校验器（缺省不校验，`03_02` 专项用例显式传入）。
        settings: 应用配置（数据范围阈值；缺省取进程单例）。

    Returns:
        RoleGrantService: 角色授权服务。
    """
    return RoleGrantService(
        RoleRepository(target),
        RolePermissionRepository(target),
        RoleFieldRepository(target),
        DataScopeRepository(target),
        MenuMetadataChecker(target),
        DbUnitOfWork(target),
        cache or MemoryCacheRegion(),
        guard,
        settings,
    )


def separation_guard(
    target: AsyncSession,
    *,
    audit: AuditCapturer | None = None,
    with_business: bool = False,
) -> SeparationGuard:
    """构造三权分立校验器（`03_02`；租户库角色 / 分配仓储）。

    Args:
        target: 会话。
        audit: 审计捕获器（缺省不产生事件）。
        with_business: 是否装配 `role` 业务权限码读取器（`role` 归属校验用）。

    Returns:
        SeparationGuard: 三权分立校验器。
    """
    return SeparationGuard(
        roles=RoleRepository(target),
        user_roles=UserRoleRepository(target),
        business_permissions=RoleBusinessPermissions(target) if with_business else None,
        audit=audit,
    )


async def seed_metadata(target: AsyncSession) -> tuple[int, int, int, int]:
    """播种授权目标元数据（菜单 / 业务 / 表单 / 权限码）。

    Args:
        target: 会话。

    Returns:
        tuple[int, int, int, int]: (菜单 ID, 业务码 ID, 表单 ID, 权限码 ID)。
    """
    menu = await MenuRepository(target).create(
        parent_id=0, name="授权页", path="/t-grant", component=None, icon=None, sort=1, hidden=False, status="enabled"
    )
    business = await BusinessRepository(target).create(code="t_grant", name="授权业务", status="enabled")
    form = await FormRepository(target).create(business_id=business.id, component=None, status="enabled")
    action = await ActionRepository(target).create(code="create", name="新建", status="enabled")
    permission = await PermissionRepository(target).create(
        business_id=business.id, action_id=action.id, status="enabled"
    )
    await target.commit()
    return menu.id, business.id, form.id, permission.id


async def seed_dict(target: AsyncSession) -> tuple[str, str]:
    """取一个已登记字典标识与其可匹配字段（数据权限白名单，来自字典数据源登记）。

    Args:
        target: 会话（保留参数以兼容调用面；本期校验走登记清单，不落字典表）。

    Returns:
        tuple[str, str]: (字典标识, 可匹配字段键)。
    """
    await target.commit()
    return "role", "label"


async def seed_form_field(target: AsyncSession, form_id: int) -> int:
    """为表单播种一个字段。

    Args:
        target: 会话。
        form_id: 表单 ID。

    Returns:
        int: 字段 ID。
    """
    field = await FieldRepository(target).create(
        form_id=form_id, field_key="title", name="标题", type="input", sort=1, status="enabled"
    )
    await target.commit()
    return field.id
