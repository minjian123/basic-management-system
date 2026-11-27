"""角色域服务级用例共用夹具（Kiwi 2248）：临时 SQLite 会话与服务构造。

角色 / 授权表（platform 租户库）与授权目标元数据（菜单元数据）、字典表在测试中共用同一临时库
（同构于生产「同服务跨库」口径下的校验路径）。
"""

from typing import cast
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.audit.base import AuditCapturer
from bms_core.cache.memory import MemoryCacheRegion
from bms_core.config.null import NullConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.db.gate import LazyGatedSession, db_access_gate
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.schemas.pagination import BasePageQuery
from bms_core.testing.transaction import _sqlite_autocommit, gate_for_engine  # pyright: ignore[reportPrivateUsage]
from bms_platform.domains.menu_form.repositories.menu import FieldRepository, FormRepository, MenuRepository
from bms_platform.domains.permission_meta.repositories.business import (
    ActionRepository,
    BusinessRepository,
    PermissionRepository,
)
from bms_platform.domains.role.repositories.role import (
    DataScopeRepository,
    RoleFieldRepository,
    RolePermissionRepository,
    RoleRepository,
    UserRoleRepository,
)
from bms_platform.domains.role.services.role import RoleService
from bms_platform.domains.role.services.role_assign import RoleAssignService
from bms_platform.domains.role.services.role_grant import MenuMetadataChecker, RoleGrantService
from bms_platform.domains.role.services.separation import RoleBusinessPermissions, SeparationGuard
from bms_platform.domains.user.repositories.user import UserRepository
from tests_support.seed_names import seed_name
from tests_support.shared_access import shared_engine, shared_platform_url, shared_tenant_url

_SCOPE: ConcurrentStableList[str] = ConcurrentStableList()
"""当前用例的唯一前缀（每次 `session()` 刷新；`uniq()` / `token()` 读它）。"""

_META: ConcurrentStableDict[str, object] = ConcurrentStableDict()
"""平台库会话与引擎（`session()` 顺带创建，`close_all()` 释放）。

角色域天然跨两库：角色 / 授权表在租户库，授权目标元数据（菜单 / 表单 / 权限码 / 字段）在平台库。
`grant_service` 的元数据校验器要用平台库会话（与生产注入一致），故在 `session()` 里一并建好。
"""


def _gated(engine: AsyncEngine) -> AsyncSession:
    """把引擎包成操作级写门会话（每次写操作取写门、写完即放）。

    Args:
        engine: 目标库引擎。

    Returns:
        AsyncSession: 门代理会话。
    """
    gate_name = gate_for_engine(engine)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(_sqlite_autocommit(engine), expire_on_commit=False)
    raw = factory()
    if gate_name is None:  # pragma: no cover - 共享库必然命中门名
        return raw
    return cast("AsyncSession", LazyGatedSession(lambda: db_access_gate(gate_name, read_only=False), raw, bind=engine))


async def session() -> tuple[AsyncSession, AsyncEngine]:
    """在共享租户库（角色 / 授权）与共享平台库（元数据）上各开门代理会话。

    引擎是本次调用自建的独立实例（`NullPool`），用例结束 `engine.dispose()` 只关自己的连接池；
    平台库那一份由 `close_all()` 释放（`role/conftest.py` 的用例收尾统一调用）。

    Returns:
        tuple[AsyncSession, AsyncEngine]: (租户库会话, 租户库引擎)。
    """
    _SCOPE.clear()
    _SCOPE.add(uuid4().hex[:8])
    engine = shared_engine(shared_tenant_url())
    _META.clear()
    _META["engine"] = shared_engine(shared_platform_url())
    _META["session"] = _gated(cast("AsyncEngine", _META["engine"]))
    return _gated(engine), engine


async def close_all() -> None:
    """释放 `session()` 顺带建的平台库引擎（用例收尾统一调用）。"""
    engine = _META.get("engine")
    _META.clear()
    if engine is not None:
        await cast("AsyncEngine", engine).dispose()


async def platform_session() -> tuple[AsyncSession, AsyncEngine]:
    """在共享平台库上开门代理会话（菜单 / 业务码 / 表单 / 字段等元数据）。

    与 `session()`（租户库：角色 / 授权）成对使用；引擎由调用方 `dispose`。

    Returns:
        tuple[AsyncSession, AsyncEngine]: (会话, 引擎)。
    """
    engine = shared_engine(shared_platform_url())
    return _gated(engine), engine


def meta_session() -> AsyncSession:
    """`session()` 顺带建的**平台库**会话（造菜单 / 业务码 / 表单 / 字段时用）。

    Returns:
        AsyncSession: 平台库门代理会话。
    """
    return cast("AsyncSession", _META["session"])


async def business_id(code: str) -> int:
    """取或建业务码（`sys_business` 属平台库；`code` 非唯一键，重复跑会累积，故先查后建）。

    建行时用**种子里的中文名**而不是 `code`：种子对「已存在」的业务码只跳过主表、仍会补写
    i18n 附表，两者不一致会让播种的一致性校验直接失败（CI 全量实测
    `sys_business#…：主表 name='log' ≠ 附表 zh-CN='审计日志'`）。

    Args:
        code: 业务码（`role` / `user` / `log` 等内置码）。

    Returns:
        int: 业务码主键。
    """
    meta = meta_session()
    for row in await BusinessRepository(meta).list_all():
        if row.code == code:
            return row.id
    created = await BusinessRepository(meta).create(code=code, name=seed_name(code, kind="business"), status="enabled")
    await meta.commit()
    return created.id


def token() -> str:
    """当前用例的唯一前缀（十六进制；给有格式约束的字段用）。

    Returns:
        str: 前缀。
    """
    return _SCOPE[0] if _SCOPE else uuid4().hex[:8]


def uniq(key: str) -> str:
    """给固定业务码 / 名称加本用例唯一前缀（共享库上避免与他人行撞唯一键）。

    Args:
        key: 业务码 / 名称原文。

    Returns:
        str: 带前缀的值；前缀强制以字母开头（角色码 / 账号名要求小写字母开头）。
    """
    return f"r{_SCOPE[0]}_{key}" if _SCOPE else key


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
    meta_session: AsyncSession | None = None,
    guard: SeparationGuard | None = None,
    settings: Settings | None = None,
) -> RoleGrantService:
    """构造角色授权服务。

    **两个会话是设计口径**：角色 / 授权表在租户库（`target`），授权目标元数据（菜单 / 表单 /
    权限码 / 字段）在平台库（`meta_session`）——`MenuMetadataChecker` 的入参在生产侧同样注入
    平台库会话（`role.py` 的 `MenuMetadataChecker(platform_session)`）。

    Args:
        target: 租户库会话。
        cache: 缓存 Region（缺省新建内存实现）。
        meta_session: 平台库会话（缺省取 `session()` 顺带建的那个）。
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
        MenuMetadataChecker(meta_session or cast("AsyncSession", _META["session"])),
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
        # 业务码 / 权限码在平台库：与生产一致，业务归属读取器绑平台库会话
        business_permissions=RoleBusinessPermissions(cast("AsyncSession", _META["session"])) if with_business else None,
        audit=audit,
    )


async def seed_metadata(target: AsyncSession) -> tuple[int, int, int, int]:
    """播种授权目标元数据（菜单 / 业务 / 表单 / 权限码）—— 写**平台库**。

    元数据表属平台库、角色 / 授权表属租户库（生产上「同服务跨库」），本函数用 `session()`
    顺带建的平台库会话，`target` 仅为兼容调用面。

    Args:
        target: 租户库会话（不使用）。

    Returns:
        tuple[int, int, int, int]: (菜单 ID, 业务码 ID, 表单 ID, 权限码 ID)。
    """
    del target
    meta = cast("AsyncSession", _META["session"])
    menu = await MenuRepository(meta).create(
        parent_id=0,
        name=uniq("授权页"),
        path=f"/{uniq('t-grant')}",
        component=None,
        icon=None,
        sort=1,
        hidden=False,
        status="enabled",
    )
    business = await BusinessRepository(meta).create(code=uniq("t_grant"), name=uniq("授权业务"), status="enabled")
    form = await FormRepository(meta).create(business_id=business.id, component=None, status="enabled")
    action = await ActionRepository(meta).create(code=uniq("create"), name="新建", status="enabled")
    permission = await PermissionRepository(meta).create(business_id=business.id, action_id=action.id, status="enabled")
    await meta.commit()
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
    """为表单播种一个字段（`sys_field` 属平台库，故用平台库会话）。

    Args:
        target: 租户库会话（不使用）。
        form_id: 表单 ID。

    Returns:
        int: 字段 ID。
    """
    del target
    meta = cast("AsyncSession", _META["session"])
    field = await FieldRepository(meta).create(
        form_id=form_id, field_key=uniq("title"), name=uniq("标题"), type="input", sort=1, status="enabled"
    )
    await meta.commit()
    return field.id
