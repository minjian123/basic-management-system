"""i18n 附表回退与删除连带清理（Kiwi 2405）：服务层口径。

锁死三件事：

1. **两级回退**：请求语言缺文案时回退**系统默认语言**（取自语言清单上下文，不是常量），两级皆缺才回主表列；
2. **大小写不敏感**：存量 `ZH-cn` 行可被 `zh-CN` 请求命中；
3. **同生命周期**：删菜单 / 字段 / 业务码 / 动作码时，附表行在同一事务内被软删（无孤儿行）。
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from sqlalchemy import Connection, Table, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.cache.base import CacheRegion
from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.i18n.base import current_default_locale
from bms_core.models.base import Base
from bms_core.models.platform.menu_form import (
    SysButton,
    SysField,
    SysFieldI18n,
    SysForm,
    SysMenu,
    SysMenuForm,
    SysMenuI18n,
)
from bms_core.models.platform.permission_meta import (
    SysAction,
    SysActionI18n,
    SysBusiness,
    SysBusinessI18n,
    SysPermission,
)
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

pytestmark = pytest.mark.kiwi_id(2405)

_TABLES = (
    SysBusiness.__table__,
    SysBusinessI18n.__table__,
    SysAction.__table__,
    SysActionI18n.__table__,
    SysPermission.__table__,
    SysMenu.__table__,
    SysMenuI18n.__table__,
    SysForm.__table__,
    SysMenuForm.__table__,
    SysButton.__table__,
    SysField.__table__,
    SysFieldI18n.__table__,
)


class _OutboxSpy:
    """发件箱替身：记录事件信封（不落库）。"""

    def __init__(self) -> None:
        """初始化空记录。"""
        self.events: ConcurrentStableList[object] = ConcurrentStableList()

    async def enqueue(self, session: object, envelope: object) -> None:
        """记录一次事件入队。

        Args:
            session: 会话（未使用）。
            envelope: 事件信封。
        """
        self.events.add(envelope)


def _create_tables(connection: Connection) -> None:
    """建用例所需十二表。

    Args:
        connection: 同步连接（`run_sync` 回调）。
    """
    Base.metadata.create_all(connection, tables=cast("list[Table]", list(_TABLES)))


async def _session() -> AsyncSession:
    """建临时内存 SQLite 会话。

    Returns:
        AsyncSession: 会话。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(_create_tables)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory()


def _menu_service(session: AsyncSession, cache: CacheRegion) -> MenuFormService:
    """构造菜单表单服务（真实仓储）。

    Args:
        session: 会话。
        cache: 缓存 Region。

    Returns:
        MenuFormService: 服务实例。
    """
    db = cast("DbSession", session)
    return MenuFormService(
        uow=DbUnitOfWork(db),
        businesses=BusinessRepository(db),
        actions=ActionRepository(db),
        permissions=PermissionRepository(db),
        menus=MenuRepository(db),
        forms=FormRepository(db),
        menu_forms=MenuFormRepository(db),
        buttons=ButtonRepository(db),
        fields=FieldRepository(db),
        outbox=cast("BaseOutboxStore", _OutboxSpy()),
        cache=cache,
    )


def _permission_service(session: AsyncSession, cache: CacheRegion) -> PermissionMetadataService:
    """构造权限元数据服务（真实仓储）。

    Args:
        session: 会话。
        cache: 缓存 Region。

    Returns:
        PermissionMetadataService: 服务实例。
    """
    db = cast("DbSession", session)
    return PermissionMetadataService(
        uow=DbUnitOfWork(db),
        businesses=BusinessRepository(db),
        actions=ActionRepository(db),
        permissions=PermissionRepository(db),
        buttons=ButtonRepository(db),
        forms=FormRepository(db),
        cache=cache,
    )


async def _seed(session: AsyncSession, row: Any) -> Any:
    """插入并提交一条记录。

    Args:
        session: 会话。
        row: ORM 行。

    Returns:
        Any: 持久化后的行（含主键）。
    """
    session.add(row)
    await session.commit()
    return row


async def _live_i18n_count(session: AsyncSession, model: Any, key_column: str, owner_id: int) -> int:
    """统计某主表行的有效附表行数。

    Args:
        session: 会话。
        model: 附表模型。
        key_column: 关联列名。
        owner_id: 主表主键。

    Returns:
        int: 未软删的附表行数。
    """
    statement = select(model).where(getattr(model, key_column) == owner_id, model.deleted_at.is_(None))
    return len((await session.execute(statement)).scalars().all())


async def test_menu_i18n_falls_back_to_default_locale() -> None:
    """请求语言缺文案时回退系统默认语言（而非主表列）。"""
    session = await _session()
    menu = await _seed(
        session,
        SysMenu(path="/m", name="主表名", status="enabled", icon=None, sort=0),
    )
    await _seed(session, SysMenuI18n(menu_id=menu.id, locale="zh-CN", name="中文名"))
    repository = MenuRepository(cast("DbSession", session))
    texts = await repository.list_i18n(ConcurrentStableList([int(menu.id)]), "en-US")
    assert texts.get(int(menu.id)) == "中文名"


async def test_menu_i18n_default_locale_follows_registry_context() -> None:
    """回退目标随语言清单默认语言变化（不是写死 zh-CN）。"""
    session = await _session()
    menu = await _seed(
        session,
        SysMenu(path="/m", name="主表名", status="enabled", icon=None, sort=0),
    )
    await _seed(session, SysMenuI18n(menu_id=menu.id, locale="en-US", name="English Name"))
    token = current_default_locale.set("en-US")
    try:
        texts = await MenuRepository(cast("DbSession", session)).list_i18n(
            ConcurrentStableList([int(menu.id)]), "zh-CN"
        )
    finally:
        current_default_locale.reset(token)
    assert texts.get(int(menu.id)) == "English Name"


async def test_menu_i18n_locale_case_insensitive() -> None:
    """存量大小写混杂的 locale 行可被标准形态请求命中。"""
    session = await _session()
    menu = await _seed(
        session,
        SysMenu(path="/m", name="主表名", status="enabled", icon=None, sort=0),
    )
    await _seed(session, SysMenuI18n(menu_id=menu.id, locale="ZH-cn", name="大小写存量"))
    texts = await MenuRepository(cast("DbSession", session)).list_i18n(ConcurrentStableList([int(menu.id)]), "zh-CN")
    assert texts.get(int(menu.id)) == "大小写存量"


async def test_business_i18n_falls_back_to_default_locale() -> None:
    """业务码附表同样两级回退（同一助手口径）。"""
    session = await _session()
    business = await _seed(session, SysBusiness(code="sys_test", name="业务名", status="enabled"))
    await _seed(session, SysBusinessI18n(business_id=business.id, locale="zh-CN", name="业务中文"))
    texts = await BusinessRepository(cast("DbSession", session)).list_i18n(
        ConcurrentStableList([int(business.id)]), "en-US"
    )
    assert texts.get(int(business.id)) == "业务中文"


async def test_delete_menu_cleans_i18n() -> None:
    """删除菜单时附表同行软删（无孤儿行）。"""
    session = await _session()
    cache = MemoryCacheRegion()
    menu = await _seed(
        session,
        SysMenu(path="/m", name="主表名", status="enabled", icon=None, sort=0),
    )
    await _seed(session, SysMenuI18n(menu_id=menu.id, locale="zh-CN", name="中文名"))
    await _menu_service(session, cache).delete_menu(int(menu.id))
    assert await _live_i18n_count(session, SysMenuI18n, "menu_id", int(menu.id)) == 0


async def test_delete_field_cleans_i18n() -> None:
    """删除字段时附表同行软删。"""
    session = await _session()
    business = await _seed(session, SysBusiness(code="sys_test", name="业务名", status="enabled"))
    form = await _seed(session, SysForm(business_id=business.id, component=None, status="enabled"))
    field = await _seed(
        session,
        SysField(form_id=form.id, field_key="f1", name="字段", type="text", sort=0, status="enabled"),
    )
    await _seed(session, SysFieldI18n(field_id=field.id, locale="zh-CN", name="字段中文"))
    await _menu_service(session, MemoryCacheRegion()).delete_field(int(field.id))
    assert await _live_i18n_count(session, SysFieldI18n, "field_id", int(field.id)) == 0


async def test_delete_business_cleans_i18n() -> None:
    """删除业务码时附表同行软删。"""
    session = await _session()
    business = await _seed(session, SysBusiness(code="sys_test", name="业务名", status="enabled"))
    await _seed(session, SysBusinessI18n(business_id=business.id, locale="zh-CN", name="业务中文"))
    await _permission_service(session, MemoryCacheRegion()).delete_business(int(business.id))
    assert await _live_i18n_count(session, SysBusinessI18n, "business_id", int(business.id)) == 0


async def test_delete_action_cleans_i18n() -> None:
    """删除动作码时附表同行软删。"""
    session = await _session()
    action = await _seed(session, SysAction(code="sys_act", name="动作名", status="enabled"))
    await _seed(session, SysActionI18n(action_id=action.id, locale="zh-CN", name="动作中文"))
    await _permission_service(session, MemoryCacheRegion()).delete_action(int(action.id))
    assert await _live_i18n_count(session, SysActionI18n, "action_id", int(action.id)) == 0


async def test_i18n_text_helpers_follow_default_context() -> None:
    """入参 / 出参助手：必填语言取请求语言，默认文案派生按清单默认语言。"""
    from bms_platform.services.i18n_text import (
        clean_i18n,
        default_locale,
        derive_default_name,
        i18n_out,
        request_locale,
        require_i18n_name,
    )

    names: ConcurrentStableDict[str, str] = ConcurrentStableDict({"en-US": "English", "zh-CN": "  "})
    cleaned = clean_i18n(names)
    assert cleaned.get("en-US") == "English"
    assert cleaned.get("zh-CN") is None
    assert default_locale() == "zh-CN"
    assert request_locale() is not None
    assert derive_default_name(ConcurrentStableDict({"en-US": "English"}), required_locale="en-US") == "English"
    with pytest.raises(Exception, match="缺少必填语言"):
        require_i18n_name(cleaned, locale="zh-CN")
    filled = i18n_out(None, name="主表名", locale="zh-CN")
    assert filled.get("zh-CN") == "主表名"
