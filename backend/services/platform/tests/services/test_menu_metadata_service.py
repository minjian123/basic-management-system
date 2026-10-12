"""菜单元数据服务写路径与快照用例（补齐 `services/menu.py` 覆盖面，Kiwi 2242）。

端点用例（`tests/api/test_menu_metadata.py`）已覆盖维护链主路径；本文件补齐其未触及的分支：

- **纯函数**：多语言归一（空白剔除）、默认文案派生优先级与全空失败、出参回填、请求语言回退、入口去重；
- **快照构建**：业务 / 动作 / 权限 / 表单 / 按钮 / 字段的**停用与断裂挂接**跳过（挂接链校验零容忍）；
- **菜单**：父子嵌套树、父菜单校验、路径冲突、子节点引用禁删、缺行与「行消失」竞态；
- **表单 / 按钮 / 字段**：更新全量替换与业务 1:1 冲突、各类缺行校验、表单缺失时的发件箱降级与「行消失」竞态。

真库两阶段事务与三库方言由 CI 作业承担，本文件以内存 SQLite 承载服务层编排。
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from sqlalchemy import Connection, Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.cache.base import CacheRegion
from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import (
    ConflictError,
    MenuI18nRequiredError,
    MenuNotFoundError,
    MenuPathConflictError,
    MenuReferencedError,
)
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.dict.base import current_dict_locale
from bms_core.i18n.base import DEFAULT_LOCALE
from bms_core.models.base import Base, BaseModel
from bms_platform.models.menu import (
    SysAction,
    SysActionI18n,
    SysBusiness,
    SysBusinessI18n,
    SysButton,
    SysField,
    SysFieldI18n,
    SysForm,
    SysMenu,
    SysMenuForm,
    SysMenuI18n,
    SysPermission,
)
from bms_platform.repositories.menu import (
    ActionRepository,
    BusinessRepository,
    ButtonRepository,
    FieldRepository,
    FormRepository,
    MenuFormRepository,
    MenuRepository,
    PermissionRepository,
)
from bms_platform.schemas.menu import MenuCreateRequest, MenuUpdateRequest
from bms_platform.services.menu import (
    MenuMetadataService,
    _snapshot_form,  # pyright: ignore[reportPrivateUsage]
    clean_i18n,
    derive_default_name,
    i18n_out,
    request_locale,
    require_i18n_name,
)

_MENU_TABLES = (
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
"""菜单元数据十二表（用例内存库建表集合）。"""


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


class _VanishMenus(MenuRepository):
    """菜单仓储替身：`update` 恒无行（构造取行后行消失的竞态）。"""

    async def update(self, item_id: int, **values: object) -> SysMenu | None:
        """恒返回 None。

        Args:
            item_id: 记录主键。
            values: 更新字段。

        Returns:
            SysMenu | None: 恒 None。
        """
        return None


class _VanishForms(FormRepository):
    """表单仓储替身：`update` 恒无行。"""

    async def update(self, item_id: int, **values: object) -> SysForm | None:
        """恒返回 None。

        Args:
            item_id: 记录主键。
            values: 更新字段。

        Returns:
            SysForm | None: 恒 None。
        """
        return None


class _VanishButtons(ButtonRepository):
    """按钮仓储替身：`update` 恒无行。"""

    async def update(self, item_id: int, **values: object) -> SysButton | None:
        """恒返回 None。

        Args:
            item_id: 记录主键。
            values: 更新字段。

        Returns:
            SysButton | None: 恒 None。
        """
        return None


class _VanishFields(FieldRepository):
    """字段仓储替身：`update` 恒无行。"""

    async def update(self, item_id: int, **values: object) -> SysField | None:
        """恒返回 None。

        Args:
            item_id: 记录主键。
            values: 更新字段。

        Returns:
            SysField | None: 恒 None。
        """
        return None


class _MissingForms(FormRepository):
    """表单仓储替身：`get` 恒无行（构造表单缺失时的发件箱降级分支）。"""

    async def get(self, item_id: int) -> SysForm | None:
        """恒返回 None。

        Args:
            item_id: 记录主键。

        Returns:
            SysForm | None: 恒 None。
        """
        return None


def _names(text: str) -> ConcurrentStableDict[str, str]:
    """构造单语言（`zh-CN`）文案映射。

    Args:
        text: 文案。

    Returns:
        ConcurrentStableDict[str, str]: 文案映射。
    """
    return ConcurrentStableDict({"zh-CN": text})


def _create_menu_tables(connection: Connection) -> None:
    """建菜单元数据十二表（依赖序由元数据排序）。

    Args:
        connection: 同步连接（`run_sync` 回调）。
    """
    Base.metadata.create_all(connection, tables=cast("list[Table]", list(_MENU_TABLES)))


async def _engine() -> tuple[AsyncSession, AsyncEngine]:
    """建临时内存 SQLite 会话（仅菜单元数据十二表）。

    Returns:
        tuple[AsyncSession, AsyncEngine]: (会话, 引擎)。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(_create_menu_tables)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory(), engine


def _service(
    session: AsyncSession,
    *,
    outbox: Any,
    cache: CacheRegion,
    menus: MenuRepository | None = None,
    forms: FormRepository | None = None,
    buttons: ButtonRepository | None = None,
    fields: FieldRepository | None = None,
) -> MenuMetadataService:
    """构造元数据服务（真实仓储 + 可替换的单仓储替身）。

    Args:
        session: 会话。
        outbox: 发件箱存储（替身）。
        cache: 缓存 Region。
        menus: 菜单仓储覆写（缺省真实仓储）。
        forms: 表单仓储覆写。
        buttons: 按钮仓储覆写。
        fields: 字段仓储覆写。

    Returns:
        MenuMetadataService: 元数据服务。
    """
    db = cast("DbSession", session)
    return MenuMetadataService(
        uow=DbUnitOfWork(db),
        businesses=BusinessRepository(db),
        actions=ActionRepository(db),
        permissions=PermissionRepository(db),
        menus=menus if menus is not None else MenuRepository(db),
        forms=forms if forms is not None else FormRepository(db),
        menu_forms=MenuFormRepository(db),
        buttons=buttons if buttons is not None else ButtonRepository(db),
        fields=fields if fields is not None else FieldRepository(db),
        outbox=outbox,
        cache=cache,
    )


async def _seed[ModelT: BaseModel](session: AsyncSession, row: ModelT) -> ModelT:
    """插入并提交一条记录。

    Args:
        session: 会话。
        row: 待插入的 ORM 行。

    Returns:
        ModelT: 持久化后的同一行（主键已生成）。
    """
    session.add(row)
    await session.commit()
    return row


def test_clean_i18n_drops_blank_values() -> None:
    """多语言归一：剔除纯空白文案，保留有值语言（不改动语言集合）。"""
    cleaned = clean_i18n(ConcurrentStableDict({"zh-CN": "  菜单  ", "en-US": "   "}))
    assert cleaned.get("zh-CN") == "菜单"
    assert "en-US" not in cleaned


def test_derive_default_name_priority_and_empty_failure() -> None:
    """默认文案派生：系统默认语言 → 必填语言 → 首个有值语言；全空即拒（40208）。"""
    assert (
        derive_default_name(ConcurrentStableDict({"zh-CN": "中文", "en-US": "EN"}), required_locale="en-US") == "中文"
    )
    assert derive_default_name(ConcurrentStableDict({"fr-FR": "", "de-DE": "德语"}), required_locale="zh-CN") == "德语"
    with pytest.raises(MenuI18nRequiredError):
        derive_default_name(ConcurrentStableDict(), required_locale="zh-CN")


def test_require_i18n_name_rejects_missing_required_locale() -> None:
    """必填语言校验：有值放行，缺必填语言文案拒绝（40208）。"""
    require_i18n_name(ConcurrentStableDict({"zh-CN": "中文"}), locale="zh-CN")
    with pytest.raises(MenuI18nRequiredError):
        require_i18n_name(ConcurrentStableDict({"zh-CN": "中文"}), locale="en-US")


def test_i18n_out_handles_none_and_fills_required_locale() -> None:
    """出参多语言映射：可空入参 → 仅必填语言回填主表默认文案。"""
    assert i18n_out(None, name="缺省文案", locale="en-US").get("en-US") == "缺省文案"
    filled = i18n_out(ConcurrentStableDict({"zh-CN": "中文"}), name="默认文案", locale="en-US")
    assert filled.get("zh-CN") == "中文"
    assert filled.get("en-US") == "默认文案"


def test_request_locale_falls_back_when_unsupported() -> None:
    """请求语言：不在支持清单时回退系统默认语言。"""
    token = current_dict_locale.set("fr-FR")
    try:
        assert request_locale() == DEFAULT_LOCALE
    finally:
        current_dict_locale.reset(token)


def test_dedupe_removes_repeated_ids() -> None:
    """入口去重：保持首次出现序。"""
    assert list(MenuMetadataService._dedupe(ConcurrentStableList([1, 2, 1, 2, 3]))) == [1, 2, 3]  # pyright: ignore[reportPrivateUsage]


def test_snapshot_form_skips_buttons_with_broken_links() -> None:
    """快照表单：按钮权限码缺失 / 动作码缺失时跳过（挂接链断裂不产出按钮）。"""
    form = SysForm(id=1, business_id=1, component=None, status="enabled")
    business = SysBusiness(id=1, code="biz", name="业务", status="enabled")
    permission = SysPermission(id=2, business_id=1, action_id=2, status="enabled")
    orphan = SysButton(id=1, form_id=1, permission_id=9, name="孤儿", type="toolbar", sort=1, status="enabled")
    no_action = SysButton(id=2, form_id=1, permission_id=2, name="缺动作", type="toolbar", sort=2, status="enabled")

    result = _snapshot_form(  # pyright: ignore[reportPrivateUsage]
        form,
        business,
        action_by_id=ConcurrentStableDict(),
        permission_by_id=ConcurrentStableDict({2: permission}),
        business_by_id=ConcurrentStableDict({1: business}),
        buttons_by_form=ConcurrentStableDict({1: ConcurrentStableList([orphan, no_action])}),
        fields_by_form=ConcurrentStableDict(),
        field_i18n=ConcurrentStableDict(),
    )
    assert list(result.buttons) == []


async def test_load_snapshot_skips_disabled_and_broken_rows() -> None:
    """快照构建：停用业务 / 权限 / 表单 / 按钮 / 字段与断裂挂接一律跳过；多入口 / 多按钮 / 多字段归集。"""
    session, engine = await _engine()
    try:
        service = _service(session, outbox=_OutboxSpy(), cache=MemoryCacheRegion())
        first_business = await _seed(session, SysBusiness(code="biz1", name="业务一", status="enabled"))
        first_business_id = first_business.id
        disabled_business = await _seed(session, SysBusiness(code="biz2", name="业务二", status="disabled"))
        third_business = await _seed(session, SysBusiness(code="biz3", name="业务三", status="enabled"))
        first_action = await _seed(session, SysAction(code="act1", name="动作一", status="enabled"))
        first_action_id = first_action.id
        second_action = await _seed(session, SysAction(code="act2", name="动作二", status="enabled"))
        second_action_id = second_action.id
        third_action = await _seed(session, SysAction(code="act3", name="动作三", status="enabled"))
        third_action_id = third_action.id
        first_permission = await _seed(
            session, SysPermission(business_id=first_business_id, action_id=first_action_id, status="enabled")
        )
        first_permission_id = first_permission.id
        second_permission = await _seed(
            session, SysPermission(business_id=first_business_id, action_id=second_action_id, status="enabled")
        )
        second_permission_id = second_permission.id
        third_permission = await _seed(
            session, SysPermission(business_id=first_business_id, action_id=third_action_id, status="enabled")
        )
        third_permission_id = third_permission.id
        await _seed(session, SysPermission(business_id=third_business.id, action_id=first_action_id, status="disabled"))
        await _seed(session, SysPermission(business_id=987654321, action_id=first_action_id, status="enabled"))
        await _seed(session, SysPermission(business_id=first_business_id, action_id=987654321, status="enabled"))
        menu = await _seed(session, SysMenu(parent_id=0, name="菜单", path="/snap", status="enabled"))
        menu_id = menu.id
        first_form = await _seed(session, SysForm(business_id=first_business_id, component=None, status="enabled"))
        first_form_id = first_form.id
        second_form = await _seed(session, SysForm(business_id=third_business.id, component=None, status="enabled"))
        disabled_form = await _seed(
            session, SysForm(business_id=disabled_business.id, component=None, status="disabled")
        )
        await _seed(session, SysMenuForm(menu_id=menu_id, form_id=first_form_id))
        await _seed(session, SysMenuForm(menu_id=menu_id, form_id=second_form.id))
        await _seed(session, SysMenuForm(menu_id=menu_id, form_id=disabled_form.id))
        await _seed(
            session,
            SysButton(
                form_id=first_form_id,
                permission_id=first_permission_id,
                name="停用按钮",
                type="toolbar",
                sort=1,
                status="disabled",
            ),
        )
        await _seed(
            session,
            SysButton(
                form_id=first_form_id,
                permission_id=second_permission_id,
                name="按钮一",
                type="toolbar",
                sort=2,
                status="enabled",
            ),
        )
        await _seed(
            session,
            SysButton(
                form_id=first_form_id,
                permission_id=third_permission_id,
                name="按钮二",
                type="toolbar",
                sort=3,
                status="enabled",
            ),
        )
        await _seed(
            session,
            SysField(form_id=first_form_id, field_key="kd", name="停用字段", type="input", sort=1, status="disabled"),
        )
        await _seed(
            session,
            SysField(form_id=first_form_id, field_key="ka", name="字段一", type="input", sort=2, status="enabled"),
        )
        await _seed(
            session,
            SysField(form_id=first_form_id, field_key="kb", name="字段二", type="input", sort=3, status="enabled"),
        )

        snapshot = await service.load_snapshot(locale=DEFAULT_LOCALE, tenant_id=None, ttl=300)

        assert snapshot.version == 0
        assert list(snapshot.permission_codes) == ["biz1:act1", "biz1:act2", "biz1:act3"]
        menus = list(snapshot.menus)
        assert len(menus) == 1
        forms = list(menus[0].forms)
        assert len(forms) == 2
        assert forms[0].business_code == "biz1"
        assert [button.name for button in forms[0].buttons] == ["按钮一", "按钮二"]
        assert [field.field_key for field in forms[0].fields] == ["ka", "kb"]

        permissions = await service.list_permissions(None)
        assert [item.code for item in permissions.items] == ["biz1:act1", "biz1:act2", "biz1:act3", "biz3:act1"]
    finally:
        await engine.dispose()


async def test_menu_write_paths() -> None:
    """菜单写路径：父子嵌套树、父校验、路径冲突、缺行、子节点引用禁删、行消失竞态。"""
    session, engine = await _engine()
    try:
        service = _service(session, outbox=_OutboxSpy(), cache=MemoryCacheRegion())
        parent, _ = await service.create_menu(MenuCreateRequest(path="/p", i18n=_names("父")))
        parent_id = parent.id
        child, _ = await service.create_menu(MenuCreateRequest(parent_id=parent_id, path="/p/c", i18n=_names("子")))
        child_id = child.id
        with pytest.raises(MenuNotFoundError):
            await service.create_menu(MenuCreateRequest(parent_id=987654321, path="/p/x", i18n=_names("无")))

        tree = await service.list_menu_tree()
        root = next(node for node in tree.items if node.id == parent_id)
        assert [node.id for node in root.children] == [child_id]
        await session.rollback()  # 读查询会 autobegin，写路径前先结束隐式事务

        with pytest.raises(MenuPathConflictError):
            await service.update_menu(child_id, MenuUpdateRequest(parent_id=0, path="/p", i18n=_names("子")))
        with pytest.raises(MenuNotFoundError):
            await service.update_menu(987654321, MenuUpdateRequest(parent_id=0, path="/zz", i18n=_names("无")))

        vanishing = _service(
            session, outbox=_OutboxSpy(), cache=MemoryCacheRegion(), menus=_VanishMenus(cast("DbSession", session))
        )
        with pytest.raises(MenuNotFoundError):
            await vanishing.update_menu(parent_id, MenuUpdateRequest(parent_id=0, path="/p2", i18n=_names("父")))

        with pytest.raises(MenuReferencedError):
            await service.delete_menu(parent_id)
        await service.delete_menu(child_id)
        await service.delete_menu(parent_id)
        with pytest.raises(MenuNotFoundError):
            await service.delete_menu(parent_id)
    finally:
        await engine.dispose()


async def test_form_write_paths() -> None:
    """表单写路径：入口全量替换、业务 1:1 冲突、缺行校验、行消失竞态与删除。"""
    session, engine = await _engine()
    try:
        service = _service(session, outbox=_OutboxSpy(), cache=MemoryCacheRegion())
        first_business = await _seed(session, SysBusiness(code="fb1", name="业务一", status="enabled"))
        first_business_id = first_business.id
        second_business = await _seed(session, SysBusiness(code="fb2", name="业务二", status="enabled"))
        second_business_id = second_business.id
        first_menu = await _seed(session, SysMenu(parent_id=0, name="甲", path="/fm1", status="enabled"))
        first_menu_id = first_menu.id
        second_menu = await _seed(session, SysMenu(parent_id=0, name="乙", path="/fm2", status="enabled"))
        second_menu_id = second_menu.id
        form = await service.create_form(
            menu_ids=ConcurrentStableList([first_menu_id]),
            business_id=first_business_id,
            component=None,
            status="enabled",
        )
        form_id = form.id
        await service.create_form(
            menu_ids=ConcurrentStableList(), business_id=second_business_id, component=None, status="enabled"
        )

        updated = await service.update_form(
            form_id,
            menu_ids=ConcurrentStableList([first_menu_id, second_menu_id, second_menu_id]),
            business_id=first_business_id,
            component="c",
            status="disabled",
        )
        assert updated.status == "disabled"
        links = await MenuFormRepository(cast("DbSession", session)).list_by_form(form_id)
        assert sorted(link.menu_id for link in links) == sorted([first_menu_id, second_menu_id])
        await session.rollback()  # 读查询会 autobegin，写路径前先结束隐式事务

        with pytest.raises(MenuNotFoundError):
            await service.update_form(
                987654321,
                menu_ids=ConcurrentStableList(),
                business_id=first_business_id,
                component=None,
                status="enabled",
            )
        with pytest.raises(MenuNotFoundError):
            await service.update_form(
                form_id, menu_ids=ConcurrentStableList(), business_id=987654321, component=None, status="enabled"
            )
        with pytest.raises(MenuNotFoundError):
            await service.update_form(
                form_id,
                menu_ids=ConcurrentStableList([987654321]),
                business_id=first_business_id,
                component=None,
                status="enabled",
            )
        with pytest.raises(ConflictError):
            await service.update_form(
                form_id,
                menu_ids=ConcurrentStableList(),
                business_id=second_business_id,
                component=None,
                status="enabled",
            )

        vanishing = _service(
            session, outbox=_OutboxSpy(), cache=MemoryCacheRegion(), forms=_VanishForms(cast("DbSession", session))
        )
        with pytest.raises(MenuNotFoundError):
            await vanishing.update_form(
                form_id,
                menu_ids=ConcurrentStableList(),
                business_id=first_business_id,
                component=None,
                status="enabled",
            )

        await service.delete_form(form_id)
        with pytest.raises(MenuNotFoundError):
            await service.delete_form(987654321)
    finally:
        await engine.dispose()


async def test_button_write_paths() -> None:
    """按钮写路径：表单 / 权限码缺行、业务不一致、同权限冲突、表单缺失降级与行消失竞态。"""
    session, engine = await _engine()
    try:
        service = _service(session, outbox=_OutboxSpy(), cache=MemoryCacheRegion())
        first_business = await _seed(session, SysBusiness(code="bb1", name="业务一", status="enabled"))
        first_business_id = first_business.id
        second_business = await _seed(session, SysBusiness(code="bb2", name="业务二", status="enabled"))
        second_business_id = second_business.id
        first_action = await _seed(session, SysAction(code="ba1", name="动作一", status="enabled"))
        first_action_id = first_action.id
        second_action = await _seed(session, SysAction(code="ba2", name="动作二", status="enabled"))
        second_action_id = second_action.id
        first_permission = await _seed(
            session, SysPermission(business_id=first_business_id, action_id=first_action_id, status="enabled")
        )
        first_permission_id = first_permission.id
        foreign_permission = await _seed(
            session, SysPermission(business_id=second_business_id, action_id=first_action_id, status="enabled")
        )
        foreign_permission_id = foreign_permission.id
        second_permission = await _seed(
            session, SysPermission(business_id=first_business_id, action_id=second_action_id, status="enabled")
        )
        second_permission_id = second_permission.id
        form = await service.create_form(
            menu_ids=ConcurrentStableList(), business_id=first_business_id, component=None, status="enabled"
        )
        form_id = form.id

        with pytest.raises(MenuNotFoundError):
            await service.create_button(
                form_id=987654321, permission_id=first_permission_id, name="X", type="toolbar", sort=0, status="enabled"
            )
        with pytest.raises(MenuNotFoundError):
            await service.create_button(
                form_id=form_id, permission_id=987654321, name="X", type="toolbar", sort=0, status="enabled"
            )
        with pytest.raises(ConflictError):
            await service.create_button(
                form_id=form_id,
                permission_id=foreign_permission_id,
                name="X",
                type="toolbar",
                sort=0,
                status="enabled",
            )

        first_button = await service.create_button(
            form_id=form_id, permission_id=first_permission_id, name="一", type="toolbar", sort=1, status="enabled"
        )
        first_button_id = first_button.id
        second_button = await service.create_button(
            form_id=form_id, permission_id=second_permission_id, name="二", type="interface", sort=2, status="enabled"
        )
        second_button_id = second_button.id

        with pytest.raises(MenuNotFoundError):
            await service.update_button(
                987654321, permission_id=first_permission_id, name="X", type="toolbar", sort=0, status="enabled"
            )
        with pytest.raises(MenuNotFoundError):
            await service.update_button(
                first_button_id, permission_id=987654321, name="X", type="toolbar", sort=0, status="enabled"
            )
        with pytest.raises(ConflictError):
            await service.update_button(
                first_button_id, permission_id=foreign_permission_id, name="X", type="toolbar", sort=0, status="enabled"
            )
        with pytest.raises(ConflictError):
            await service.update_button(
                first_button_id, permission_id=second_permission_id, name="X", type="toolbar", sort=0, status="enabled"
            )

        changed = await service.update_button(
            first_button_id, permission_id=first_permission_id, name="改", type="interface", sort=9, status="disabled"
        )
        assert changed.name == "改"

        missing_form = _service(
            session, outbox=_OutboxSpy(), cache=MemoryCacheRegion(), forms=_MissingForms(cast("DbSession", session))
        )
        published = await missing_form.update_button(
            second_button_id, permission_id=second_permission_id, name="三", type="toolbar", sort=3, status="enabled"
        )
        assert published.name == "三"

        vanishing = _service(
            session,
            outbox=_OutboxSpy(),
            cache=MemoryCacheRegion(),
            buttons=_VanishButtons(cast("DbSession", session)),
        )
        with pytest.raises(MenuNotFoundError):
            await vanishing.update_button(
                second_button_id,
                permission_id=second_permission_id,
                name="四",
                type="toolbar",
                sort=4,
                status="enabled",
            )

        await service.delete_button(second_button_id)
        with pytest.raises(MenuNotFoundError):
            await service.delete_button(second_button_id)
    finally:
        await engine.dispose()


async def test_field_write_paths() -> None:
    """字段写路径：表单缺行、更新重派生、表单缺失降级、行消失竞态与删除。"""
    session, engine = await _engine()
    try:
        service = _service(session, outbox=_OutboxSpy(), cache=MemoryCacheRegion())
        business = await _seed(session, SysBusiness(code="db1", name="业务", status="enabled"))
        business_id = business.id
        form = await service.create_form(
            menu_ids=ConcurrentStableList(), business_id=business_id, component=None, status="enabled"
        )
        form_id = form.id

        with pytest.raises(MenuNotFoundError):
            await service.create_field(
                form_id=987654321, field_key="k", type="input", sort=0, status="enabled", i18n=_names("字段")
            )

        field, _ = await service.create_field(
            form_id=form_id, field_key="k", type="input", sort=1, status="enabled", i18n=_names("字段")
        )
        field_id = field.id
        updated, i18n = await service.update_field(
            field_id, type="select", sort=2, status="disabled", i18n=_names("字段改")
        )
        assert updated.type == "select"
        assert i18n.get("zh-CN") == "字段改"

        with pytest.raises(MenuNotFoundError):
            await service.update_field(987654321, type="input", sort=0, status="enabled", i18n=_names("无"))

        missing_form = _service(
            session, outbox=_OutboxSpy(), cache=MemoryCacheRegion(), forms=_MissingForms(cast("DbSession", session))
        )
        renamed, _ = await missing_form.update_field(
            field_id, type="text", sort=3, status="enabled", i18n=_names("再改")
        )
        assert renamed.type == "text"

        vanishing = _service(
            session, outbox=_OutboxSpy(), cache=MemoryCacheRegion(), fields=_VanishFields(cast("DbSession", session))
        )
        with pytest.raises(MenuNotFoundError):
            await vanishing.update_field(field_id, type="text", sort=4, status="enabled", i18n=_names("又改"))

        await service.delete_field(field_id)
        with pytest.raises(MenuNotFoundError):
            await service.delete_field(field_id)
    finally:
        await engine.dispose()
