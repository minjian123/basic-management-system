"""平台服务域装配：按请求级会话构造业务域服务（跨域只读面在此注入）。

**为什么单独一层**：`MenuFormService` 需要权限元数据（业务码 / 动作码 / 权限码）构建快照、
`PermissionMetadataService` 需要按钮 / 表单挂接与角色授权引用做删除前置校验——两侧若直接互相 import
会形成域间环。装配面同时依赖两侧，域实现只依赖 Protocol（依赖方向恒为「装配 → 域」）。

本模块属**装配面**（`shared_paths`），不承载业务规则。
"""

from typing import cast

from bms_core.cache.base import CacheRegion
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.outbox.base import BaseOutboxStore
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
from bms_platform.domains.role.repositories.reference import MetadataReferenceRepository

__all__ = ["build_menu_service", "build_permission_service"]


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
