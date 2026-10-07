"""角色域服务级用例共用夹具（Kiwi 2248）：临时 SQLite 会话与服务构造。

角色 / 授权表（platform 租户库）与授权目标元数据（菜单元数据）、字典表在测试中共用同一临时库
（同构于生产「同服务跨库」口径下的校验路径）。
"""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.config.null import NullConfigSource
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.dict.models import SysDictAttr, SysDictType
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.models.role import SysRole
from bms_platform.repositories.menu import (
    ActionRepository,
    BusinessRepository,
    FieldRepository,
    FormRepository,
    MenuRepository,
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


def assign_service(target: AsyncSession, cache: MemoryCacheRegion | None = None) -> RoleAssignService:
    """构造角色分配服务。

    Args:
        target: 会话。
        cache: 缓存 Region（缺省新建内存实现）。

    Returns:
        RoleAssignService: 角色分配服务。
    """
    return RoleAssignService(
        RoleRepository(target),
        UserRoleRepository(target),
        UserRepository(target),
        DbUnitOfWork(target),
        cache or MemoryCacheRegion(),
    )


def grant_service(target: AsyncSession, cache: MemoryCacheRegion | None = None) -> RoleGrantService:
    """构造角色授权服务。

    Args:
        target: 会话。
        cache: 缓存 Region（缺省新建内存实现）。

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
    )


async def seed_metadata(target: AsyncSession) -> tuple[int, int, int, int]:
    """播种授权目标元数据（菜单 / 业务 / 表单 / 动作）。

    Args:
        target: 会话。

    Returns:
        tuple[int, int, int, int]: (菜单 ID, 业务码 ID, 表单 ID, 动作 ID)。
    """
    menu = await MenuRepository(target).create(
        parent_id=0, name="授权页", path="/t-grant", component=None, icon=None, sort=1, hidden=False, status="enabled"
    )
    business = await BusinessRepository(target).create(code="t_grant", name="授权业务", status="enabled")
    form = await FormRepository(target).create(business_id=business.id, component=None, status="enabled")
    action = await ActionRepository(target).create(
        business_id=business.id, code="create", name="新建", status="enabled"
    )
    await target.commit()
    return menu.id, business.id, form.id, action.id


async def seed_dict(target: AsyncSession) -> tuple[int, str]:
    """播种一个字典类型与一个**已启用**扩展属性（数据权限匹配字段白名单）。

    Args:
        target: 会话。

    Returns:
        tuple[int, str]: (字典类型 ID, 已启用扩展属性键)。
    """
    dict_type = SysDictType(type="area", name="区域", sort=1, status="enabled")
    target.add(dict_type)
    await target.flush()
    target.add(
        SysDictAttr(type_id=dict_type.id, attr_key="area_code", name="区域码", data_type="text", status="enabled")
    )
    target.add(
        SysDictAttr(type_id=dict_type.id, attr_key="disabled_key", name="停用属性", data_type="text", status="disabled")
    )
    await target.flush()
    await target.commit()
    return dict_type.id, "area_code"


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
