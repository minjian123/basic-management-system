"""平台服务权限子包：菜单元数据服务构造（权限聚合的元数据来源）。

权限聚合需要「菜单 → 表单 → 业务码 / 动作码」的元数据（**平台服务库**表，非租户库），
故按平台库会话构造 `MenuMetadataService`——只读路径不产生发件箱副作用（`NullOutboxStore`），
元数据快照自身的缓存与版本失效由该服务承担（与 `/api/v1/menus/my` 同源同缓存）。
"""

from __future__ import annotations

from bms_core.cache.base import CacheRegion
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.outbox.null import NullOutboxStore
from bms_platform.repositories.menu import (
    ActionRepository,
    BusinessRepository,
    ButtonRepository,
    FieldRepository,
    FormRepository,
    MenuFormRepository,
    MenuRepository,
)
from bms_platform.services.menu import MenuMetadataService


def build_menu_metadata_service(session: DbSession, cache: CacheRegion) -> MenuMetadataService:
    """按平台库会话构造菜单元数据服务（只读口径）。

    Args:
        session: 平台库会话（`session_scope(db_key="platform")`）。
        cache: 缓存能力域（元数据快照缓存）。

    Returns:
        MenuMetadataService: 元数据服务实例。
    """
    return MenuMetadataService(
        uow=DbUnitOfWork(session),
        businesses=BusinessRepository(session),
        actions=ActionRepository(session),
        menus=MenuRepository(session),
        forms=FormRepository(session),
        menu_forms=MenuFormRepository(session),
        buttons=ButtonRepository(session),
        fields=FieldRepository(session),
        outbox=NullOutboxStore(),
        cache=cache,
    )
