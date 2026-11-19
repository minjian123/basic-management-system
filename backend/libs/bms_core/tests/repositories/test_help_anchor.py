"""帮助锚点跨表唯一性读助手（08_01；Kiwi 2520）。

被测对象：`bms_core/repositories/help_anchor.py`。锁死三条口径：五表一起探测、软删行不参与、
更新自身时可排除（同表多行时按主键排除）。
"""

from collections.abc import AsyncIterator
from functools import partial
from typing import cast

import pytest
from sqlalchemy import Connection, Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.help.anchors import HelpAnchorKind
from bms_core.models.platform.menu_form import SysButton, SysField, SysForm, SysMenu
from bms_core.models.platform.permission_meta import SysAction, SysBusiness, SysPermission
from bms_core.repositories.help_anchor import (
    HelpAnchorEntry,
    find_help_key_conflict,
    list_help_anchors,
    load_help_anchor_index,
    load_help_anchor_kinds,
)
from bms_core.testing.transaction import write_session

_MODELS = (SysMenu, SysForm, SysField, SysButton, SysAction, SysBusiness, SysPermission)


def _create_table(table: Table, connection: Connection) -> None:
    """幂等建表（共享库上只补本文件需要的五表）。

    Args:
        table: 表定义。
        connection: 同步连接。
    """
    table.create(connection, checkfirst=True)


@pytest.fixture
async def engine(shared_platform_engine: AsyncEngine) -> AsyncEngine:
    """共享平台库引擎（幂等建五张元数据表）。

    Args:
        shared_platform_engine: 共享库引擎。

    Returns:
        AsyncEngine: 已建表的引擎。
    """
    async with shared_platform_engine.begin() as connection:
        for model in _MODELS:
            await connection.run_sync(partial(_create_table, cast("Table", model.__table__)))
    return shared_platform_engine


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """回滚会话。

    Args:
        engine: 共享库引擎。

    Yields:
        AsyncSession: 写会话（不提交，退出即回滚）。
    """
    async with write_session(engine) as db_session:
        yield db_session


@pytest.mark.kiwi_id(2520)
async def test_conflict_found_across_tables_and_self_excluded(session: AsyncSession) -> None:
    """同一 help_key 跨表命中；更新自身时排除自身行后仍能命中他人。"""
    menu = SysMenu(name="菜单", path="/probe/menu", status="enabled", help_key="platform:platform:::")
    form = SysForm(business_id=1, status="enabled", help_key="platform:platform:::")
    session.add_all([menu, form])
    await session.flush()

    conflict = await find_help_key_conflict(session, "platform:platform:::")
    assert conflict is not None
    assert conflict.table == "sys_menu"
    assert conflict.model_id == int(menu.id)

    excluded = await find_help_key_conflict(
        session, "platform:platform:::", exclude_kind=conflict.kind, exclude_id=int(menu.id)
    )
    assert excluded is not None
    assert excluded.table == "sys_form"
    assert excluded.model_id == int(form.id)


@pytest.mark.kiwi_id(2520)
async def test_soft_deleted_rows_do_not_block(session: AsyncSession) -> None:
    """软删除行不参与唯一性判定（删除后释放锚点）。"""
    menu = SysMenu(name="菜单", path="/probe/deleted", status="enabled", help_key="platform:deleted:::")
    session.add(menu)
    await session.flush()
    menu.soft_delete()
    await session.flush()
    assert await find_help_key_conflict(session, "platform:deleted:::") is None


@pytest.mark.kiwi_id(2520)
async def test_list_help_anchors_skips_null_and_deleted(session: AsyncSession) -> None:
    """全量列示只取非空、未软删行（跨五表）。"""
    session.add_all(
        [
            SysMenu(name="有锚点", path="/probe/one", status="enabled", help_key="platform:one:::"),
            SysMenu(name="无锚点", path="/probe/two", status="enabled"),
            SysAction(code="probe_action", name="动作", status="enabled", help_key="platform::::probe_action"),
        ]
    )
    await session.flush()
    entries = await list_help_anchors(session)
    assert sorted(entry.table for entry in entries) == ["sys_action", "sys_menu"]
    assert {entry.help_key for entry in entries} == {"platform:one:::", "platform::::probe_action"}


@pytest.mark.kiwi_id(2521)
async def test_load_help_anchor_index_collects_enabled_rows(session: AsyncSession) -> None:
    """索引归集：只取启用且未软删行；非法 / 失联 / 停用行不进索引。"""
    business = SysBusiness(code="probe_biz", name="业务", status="enabled")
    disabled_business = SysBusiness(code="probe_off", name="停用业务", status="disabled")
    action = SysAction(code="probe_create", name="新建", status="enabled", help_key="platform::::probe_create")
    menu = SysMenu(name="模块", path="/probe/module", status="enabled", help_key="platform:probe_mod:::")
    disabled_menu = SysMenu(name="停用模块", path="/probe/off", status="disabled", help_key="platform:probe_off:::")
    broken_menu = SysMenu(name="坏锚点", path="/probe/broken", status="enabled", help_key="probe-broken")
    orphan_form_business = SysBusiness(code="probe_orphan", name="孤儿业务", status="enabled")
    session.add_all([business, disabled_business, action, menu, disabled_menu, broken_menu, orphan_form_business])
    await session.flush()

    form = SysForm(business_id=business.id, status="enabled", help_key="platform:probe_mod:probe_biz::")
    orphan_form = SysForm(
        business_id=orphan_form_business.id, status="enabled", help_key="platform:probe_mod:probe_orphan::"
    )
    disabled_form = SysForm(
        business_id=disabled_business.id, status="disabled", help_key="platform:probe_mod:probe_off::"
    )
    missing_business_form = SysForm(business_id=999999, status="enabled", help_key="platform:probe_mod:missing::")
    session.add_all([form, orphan_form, disabled_form, missing_business_form])
    await session.flush()

    permission = SysPermission(business_id=business.id, action_id=action.id, status="enabled")
    missing_business_permission = SysPermission(business_id=999999, action_id=action.id, status="enabled")
    missing_action_permission = SysPermission(business_id=business.id, action_id=999999, status="enabled")
    session.add_all([permission, missing_business_permission, missing_action_permission])
    await session.flush()

    button = SysButton(
        form_id=form.id,
        permission_id=permission.id,
        name="新建",
        status="enabled",
        help_key="platform:probe_mod:probe_biz::probe_create",
    )
    orphan_button = SysButton(
        form_id=form.id,
        permission_id=999999,
        name="失联",
        status="enabled",
        help_key="platform:probe_mod:probe_biz::lost",
    )
    field = SysField(
        form_id=form.id,
        field_key="probe_field",
        name="字段",
        type="input",
        status="enabled",
        help_key="platform:probe_mod:probe_biz:probe_field:",
    )
    deleted_field = SysField(
        form_id=form.id,
        field_key="probe_deleted",
        name="已删字段",
        type="input",
        status="enabled",
        help_key="platform:probe_mod:probe_biz:probe_deleted:",
    )
    session.add_all([button, orphan_button, field, deleted_field])
    await session.flush()
    deleted_field.soft_delete()
    await session.flush()

    index = await load_help_anchor_index(session)
    assert [(anchor.product, anchor.module_key) for anchor in index.menus] == [("platform", "probe_mod")]
    assert index.menus[0].model_id == int(menu.id)
    assert dict(index.forms) == {
        "probe_biz": "platform:probe_mod:probe_biz::",
        "probe_orphan": "platform:probe_mod:probe_orphan::",
    }
    assert dict(index.fields) == {("probe_biz", "probe_field"): "platform:probe_mod:probe_biz:probe_field:"}
    assert dict(index.buttons) == {("probe_biz", "probe_create"): "platform:probe_mod:probe_biz::probe_create"}
    assert dict(index.actions) == {"probe_create": "platform::::probe_create"}


async def test_load_anchor_kinds_keeps_first_on_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """锚点 → 类型映射：重复值按先出现者为准（跨表唯一由写接口保证，此处只做容错）。"""
    entries = ConcurrentStableList(
        (
            HelpAnchorEntry(
                kind=HelpAnchorKind.MENU,
                table="sys_menu",
                model_id=1,
                help_key="platform:dup:::",
            ),
            HelpAnchorEntry(
                kind=HelpAnchorKind.FORM,
                table="sys_form",
                model_id=2,
                help_key="platform:dup:::",
            ),
        )
    )

    async def _fake_list(session: AsyncSession) -> ConcurrentStableList[HelpAnchorEntry]:
        """返回重复锚点清单。"""
        del session
        return entries

    monkeypatch.setattr("bms_core.repositories.help_anchor.list_help_anchors", _fake_list)
    kinds = await load_help_anchor_kinds(cast("AsyncSession", object()))
    assert dict(kinds) == {"platform:dup:::": HelpAnchorKind.MENU}
