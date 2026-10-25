"""权限聚合的元数据服务构造（`permission_meta` 业务域）。

权限聚合需要「菜单 → 表单 → 业务码 / 动作码」的元数据（**平台服务库**表，非租户库），
故按平台库会话经装配面构造 `MenuFormService`——只读路径不产生发件箱副作用（`NullOutboxStore`），
元数据快照自身的缓存与版本失效由该服务承担（与 `/api/v1/menus/my` 同源同缓存）。

跨域读取只经 `bms_platform.wiring`（装配面）与 `menu_form.public`（公共出口），本域不 import 他域实现。
"""

from __future__ import annotations

from bms_core.cache.base import CacheRegion
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.outbox.null import NullOutboxStore
from bms_platform.domains.menu_form.public import MenuFormService
from bms_platform.wiring import build_menu_service


def build_menu_metadata_service(session: DbSession, cache: CacheRegion) -> MenuFormService:
    """按平台库会话构造菜单元数据服务（只读口径）。

    Args:
        session: 平台库会话（`session_scope(db_key="platform")`）。
        cache: 缓存能力域（元数据快照缓存）。

    Returns:
        MenuFormService: 菜单表单服务实例（只读使用）。
    """
    return build_menu_service(uow=DbUnitOfWork(session), outbox=NullOutboxStore(), cache=cache)
