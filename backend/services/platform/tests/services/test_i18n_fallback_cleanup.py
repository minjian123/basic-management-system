"""i18n 附表回退与删除连带清理（Kiwi 2405）：服务层口径。

锁死三件事：

1. **两级回退**：请求语言缺文案时回退**系统默认语言**（取自语言清单上下文，不是常量），两级皆缺才回主表列；
2. **大小写不敏感**：存量 `ZH-cn` 行可被 `zh-CN` 请求命中；
3. **同生命周期**：删菜单 / 字段 / 业务码 / 动作码时，附表行在同一事务内被软删（无孤儿行）。
"""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bms_core.cache.base import CacheRegion
from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.gate import LazyGatedSession, db_access_gate
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.i18n.base import current_default_locale
from bms_core.models.platform.menu_form import (
    SysField,
    SysFieldI18n,
    SysForm,
    SysMenu,
    SysMenuI18n,
)
from bms_core.models.platform.permission_meta import (
    SysAction,
    SysActionI18n,
    SysBusiness,
    SysBusinessI18n,
)
from bms_core.outbox.base import BaseOutboxStore
from bms_core.testing.gates import PLATFORM_GATE
from bms_core.testing.namespace import Namespace
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
from tests_support.shared_access import shared_engine, shared_platform_url

pytestmark = pytest.mark.kiwi_id(2405)


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


@pytest_asyncio.fixture
async def session(ns: Namespace) -> AsyncIterator[AsyncSession]:
    """共享平台库会话（表由数据初始化建好；经 `LazyGatedSession` 逐操作走写门）。

    Yields:
        AsyncSession: 共享平台库写会话（门代理）。
    """
    engine = shared_engine(shared_platform_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    proxy = LazyGatedSession(lambda: db_access_gate(PLATFORM_GATE, read_only=False), factory(), bind=engine)
    try:
        yield cast("AsyncSession", proxy)
    finally:
        await proxy.close()
        _purge_ns(ns)


def _purge_ns(ns: Namespace) -> None:
    """teardown 清理：按用例命名空间删除本文件造的 业务 / 菜单及其附表。

    走同步连接（清理是收尾动作，不参与被测事务；ORM 删除在门代理会话上会被下一例的前置事务冲掉）。

    Args:
        ns: 用例命名空间（清理范围）。
    """
    path = shared_platform_url().split("///")[-1]
    connection = sqlite3.connect(path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            "DELETE FROM sys_business_i18n WHERE business_id IN (SELECT id FROM sys_business WHERE code LIKE ?)",
            (ns.like(),),
        )
        cursor.execute("DELETE FROM sys_business WHERE code LIKE ?", (ns.like(),))
        cursor.execute(
            "DELETE FROM sys_menu_i18n WHERE menu_id IN (SELECT id FROM sys_menu WHERE path LIKE ?)",
            (f"/{ns.like()}",),
        )
        cursor.execute("DELETE FROM sys_menu WHERE path LIKE ?", (f"/{ns.like()}",))
        connection.commit()
    finally:
        connection.close()


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


async def test_menu_i18n_falls_back_to_default_locale(session: AsyncSession, ns: Namespace) -> None:
    """请求语言缺文案时回退系统默认语言（而非主表列）。"""
    menu = await _seed(
        session,
        SysMenu(path=f"/{ns.code('m')}", name="主表名", status="enabled", icon=None, sort=0),
    )
    await _seed(session, SysMenuI18n(menu_id=menu.id, locale="zh-CN", name="中文名"))
    repository = MenuRepository(cast("DbSession", session))
    texts = await repository.list_i18n(ConcurrentStableList([int(menu.id)]), "en-US")
    assert texts.get(int(menu.id)) == "中文名"


async def test_menu_i18n_default_locale_follows_registry_context(session: AsyncSession, ns: Namespace) -> None:
    """回退目标随语言清单默认语言变化（不是写死 zh-CN）。"""
    menu = await _seed(
        session,
        SysMenu(path=f"/{ns.code('m')}", name="主表名", status="enabled", icon=None, sort=0),
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


async def test_menu_i18n_locale_case_insensitive(session: AsyncSession, ns: Namespace) -> None:
    """存量大小写混杂的 locale 行可被标准形态请求命中。"""
    menu = await _seed(
        session,
        SysMenu(path=f"/{ns.code('m')}", name="主表名", status="enabled", icon=None, sort=0),
    )
    await _seed(session, SysMenuI18n(menu_id=menu.id, locale="ZH-cn", name="大小写存量"))
    texts = await MenuRepository(cast("DbSession", session)).list_i18n(ConcurrentStableList([int(menu.id)]), "zh-CN")
    assert texts.get(int(menu.id)) == "大小写存量"


async def test_business_i18n_falls_back_to_default_locale(session: AsyncSession, ns: Namespace) -> None:
    """业务码附表同样两级回退（同一助手口径）。"""
    business = await _seed(session, SysBusiness(code=ns.code("biz"), name="业务名", status="enabled"))
    await _seed(session, SysBusinessI18n(business_id=business.id, locale="zh-CN", name="业务中文"))
    texts = await BusinessRepository(cast("DbSession", session)).list_i18n(
        ConcurrentStableList([int(business.id)]), "en-US"
    )
    assert texts.get(int(business.id)) == "业务中文"


async def test_delete_menu_cleans_i18n(session: AsyncSession, ns: Namespace) -> None:
    """删除菜单时附表同行软删（无孤儿行）。"""
    cache = MemoryCacheRegion()
    menu = await _seed(
        session,
        SysMenu(path=f"/{ns.code('m')}", name="主表名", status="enabled", icon=None, sort=0),
    )
    await _seed(session, SysMenuI18n(menu_id=menu.id, locale="zh-CN", name="中文名"))
    await _menu_service(session, cache).delete_menu(int(menu.id))
    assert await _live_i18n_count(session, SysMenuI18n, "menu_id", int(menu.id)) == 0


async def test_delete_field_cleans_i18n(session: AsyncSession, ns: Namespace) -> None:
    """删除字段时附表同行软删。"""
    business = await _seed(session, SysBusiness(code=ns.code("biz"), name="业务名", status="enabled"))
    form = await _seed(session, SysForm(business_id=business.id, component=None, status="enabled"))
    field = await _seed(
        session,
        SysField(form_id=form.id, field_key="f1", name="字段", type="text", sort=0, status="enabled"),
    )
    await _seed(session, SysFieldI18n(field_id=field.id, locale="zh-CN", name="字段中文"))
    await _menu_service(session, MemoryCacheRegion()).delete_field(int(field.id))
    assert await _live_i18n_count(session, SysFieldI18n, "field_id", int(field.id)) == 0


async def test_delete_business_cleans_i18n(session: AsyncSession, ns: Namespace) -> None:
    """删除业务码时附表同行软删。"""
    business = await _seed(session, SysBusiness(code=ns.code("biz"), name="业务名", status="enabled"))
    await _seed(session, SysBusinessI18n(business_id=business.id, locale="zh-CN", name="业务中文"))
    await _permission_service(session, MemoryCacheRegion()).delete_business(int(business.id))
    assert await _live_i18n_count(session, SysBusinessI18n, "business_id", int(business.id)) == 0


async def test_delete_action_cleans_i18n(session: AsyncSession, ns: Namespace) -> None:
    """删除动作码时附表同行软删。"""
    action = await _seed(session, SysAction(code=ns.code("act"), name="动作名", status="enabled"))
    await _seed(session, SysActionI18n(action_id=action.id, locale="zh-CN", name="动作中文"))
    await _permission_service(session, MemoryCacheRegion()).delete_action(int(action.id))
    assert await _live_i18n_count(session, SysActionI18n, "action_id", int(action.id)) == 0


async def test_i18n_text_helpers_follow_default_context(session: AsyncSession) -> None:
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
