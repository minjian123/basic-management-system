"""帮助锚点跨表唯一性读助手（08_01；Kiwi 2520）。

被测对象：`bms_core/repositories/help_anchor.py`。锁死三条口径：五表一起探测、软删行不参与、
更新自身时可排除（同表多行时按主键排除）。

运行口径（2026-11-27 重写）：`write_session` 是 autocommit（写入立即落库），共享库又跨轮次叠加，
故本文件的业务键（菜单路径 / 业务与动作编码 / 五段锚点）一律按用例命名空间派生，用例之间靠
前缀互不相交；**不做任何清场**，也不与他人数据抢同一张表的固定哨兵。
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
from bms_core.testing.namespace import Namespace
from bms_core.testing.transaction import write_session

_MODELS = (SysMenu, SysForm, SysField, SysButton, SysAction, SysBusiness, SysPermission)


def _code(ns: Namespace, leaf: str) -> str:
    """本用例命名空间下的业务码 / 动作码（编码只允许 `[a-z0-9_]`）。

    Args:
        ns: 命名空间。
        leaf: 叶子段。

    Returns:
        str: `{prefix}_{leaf}`。
    """
    return f"{ns.prefix}_{leaf}"


def _module_key(ns: Namespace) -> str:
    """本用例的模块键（五段锚点的第二段）。

    Args:
        ns: 命名空间。

    Returns:
        str: `{prefix}mod`。
    """
    return f"{ns.prefix}mod"


def _path(ns: Namespace, leaf: str) -> str:
    """本用例命名空间下的菜单路径。

    Args:
        ns: 命名空间。
        leaf: 叶子段。

    Returns:
        str: `/{prefix}/{leaf}`。
    """
    return f"/{ns.prefix}/{leaf}"


def _create_table(table: Table, connection: Connection) -> None:
    """幂等建表（共享库上只补本文件需要的表）。

    Args:
        table: 表定义。
        connection: 同步连接。
    """
    table.create(connection, checkfirst=True)


@pytest.fixture
async def engine(shared_platform_engine: AsyncEngine) -> AsyncEngine:
    """共享平台库引擎（幂等建本文件用到的七张元数据表）。

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
    """操作级写会话（autocommit；本文件数据按命名空间隔离，不清理）。

    Args:
        engine: 共享库引擎。

    Yields:
        AsyncSession: 写会话。
    """
    async with write_session(engine) as db_session:
        yield db_session


@pytest.mark.kiwi_id(2520)
async def test_conflict_found_across_tables_and_self_excluded(session: AsyncSession, ns: Namespace) -> None:
    """同一 help_key 跨表命中；更新自身时排除自身行后仍能命中他人。"""
    anchor = f"platform:{_module_key(ns)}:{_code(ns, 'biz')}::"
    menu = SysMenu(name="菜单", path=_path(ns, "conflict"), status="enabled", help_key=anchor)
    form = SysForm(business_id=1, status="enabled", help_key=anchor)
    session.add_all([menu, form])
    await session.flush()

    conflict = await find_help_key_conflict(session, anchor)
    assert conflict is not None
    assert conflict.table == "sys_menu"
    assert conflict.model_id == int(menu.id)

    excluded = await find_help_key_conflict(session, anchor, exclude_kind=conflict.kind, exclude_id=int(menu.id))
    assert excluded is not None
    assert excluded.table == "sys_form"
    assert excluded.model_id == int(form.id)


@pytest.mark.kiwi_id(2520)
async def test_soft_deleted_rows_do_not_block(session: AsyncSession, ns: Namespace) -> None:
    """软删除行不参与唯一性判定（删除后释放锚点）。"""
    anchor = f"platform:{_module_key(ns)}:deleted::"
    menu = SysMenu(name="菜单", path=_path(ns, "deleted"), status="enabled", help_key=anchor)
    session.add(menu)
    await session.flush()
    menu.soft_delete()
    await session.flush()
    assert await find_help_key_conflict(session, anchor) is None


@pytest.mark.kiwi_id(2520)
async def test_list_help_anchors_skips_null_and_deleted(session: AsyncSession, ns: Namespace) -> None:
    """全量列示只取非空、未软删行（跨表）；本用例只认自己造的两条锚点。"""
    menu_anchor = f"platform:{_module_key(ns)}:one:::"
    action_anchor = f"platform::::{_code(ns, 'act')}"
    session.add_all(
        [
            SysMenu(name="有锚点", path=_path(ns, "one"), status="enabled", help_key=menu_anchor),
            SysMenu(name="无锚点", path=_path(ns, "two"), status="enabled"),
            SysAction(code=_code(ns, "act"), name="动作", status="enabled", help_key=action_anchor),
        ]
    )
    await session.flush()
    entries = await list_help_anchors(session)
    mine = [entry for entry in entries if entry.help_key in {menu_anchor, action_anchor}]
    assert sorted(entry.table for entry in mine) == ["sys_action", "sys_menu"]
    assert {entry.help_key for entry in mine} == {menu_anchor, action_anchor}


@pytest.mark.kiwi_id(2521)
async def test_load_help_anchor_index_collects_enabled_rows(session: AsyncSession, ns: Namespace) -> None:
    """索引归集：只取启用且未软删行；非法 / 失联 / 停用行不进索引。"""
    module = _module_key(ns)
    business_code = _code(ns, "biz")
    create_code = _code(ns, "create")
    field_key = _code(ns, "field")

    business = SysBusiness(code=business_code, name="业务", status="enabled")
    disabled_business = SysBusiness(code=_code(ns, "off"), name="停用业务", status="disabled")
    action = SysAction(code=create_code, name="新建", status="enabled", help_key=f"platform::::{create_code}")
    menu = SysMenu(name="模块", path=_path(ns, "module"), status="enabled", help_key=f"platform:{module}:::")
    disabled_menu = SysMenu(
        name="停用模块", path=_path(ns, "off"), status="disabled", help_key=f"platform:{module}_off:::"
    )
    broken_menu = SysMenu(name="坏锚点", path=_path(ns, "broken"), status="enabled", help_key=f"{module}-broken")
    orphan_form_business = SysBusiness(code=_code(ns, "orphan"), name="孤儿业务", status="enabled")
    session.add_all([business, disabled_business, action, menu, disabled_menu, broken_menu, orphan_form_business])
    await session.flush()

    form = SysForm(business_id=business.id, status="enabled", help_key=f"platform:{module}:{business_code}::")
    orphan_form = SysForm(
        business_id=orphan_form_business.id,
        status="enabled",
        help_key=f"platform:{module}:{_code(ns, 'orphan')}::",
    )
    disabled_form = SysForm(
        business_id=disabled_business.id, status="disabled", help_key=f"platform:{module}:{_code(ns, 'off')}::"
    )
    missing_business_form = SysForm(
        business_id=999_999, status="enabled", help_key=f"platform:{module}:{_code(ns, 'missing')}::"
    )
    session.add_all([form, orphan_form, disabled_form, missing_business_form])
    await session.flush()

    permission = SysPermission(business_id=business.id, action_id=action.id, status="enabled")
    missing_business_permission = SysPermission(business_id=999_999, action_id=action.id, status="enabled")
    missing_action_permission = SysPermission(business_id=business.id, action_id=999_999, status="enabled")
    session.add_all([permission, missing_business_permission, missing_action_permission])
    await session.flush()

    button = SysButton(
        form_id=form.id,
        permission_id=permission.id,
        name="新建",
        status="enabled",
        help_key=f"platform:{module}:{business_code}::{create_code}",
    )
    orphan_button = SysButton(
        form_id=form.id,
        permission_id=999_999,
        name="失联",
        status="enabled",
        help_key=f"platform:{module}:{business_code}::{_code(ns, 'lost')}",
    )
    field = SysField(
        form_id=form.id,
        field_key=field_key,
        name="字段",
        type="input",
        status="enabled",
        help_key=f"platform:{module}:{business_code}:{field_key}:",
    )
    deleted_field = SysField(
        form_id=form.id,
        field_key=_code(ns, "deleted"),
        name="已删字段",
        type="input",
        status="enabled",
        help_key=f"platform:{module}:{business_code}:{_code(ns, 'deleted')}:",
    )
    session.add_all([button, orphan_button, field, deleted_field])
    await session.flush()
    deleted_field.soft_delete()
    await session.flush()

    index = await load_help_anchor_index(session)
    assert [(anchor.product, anchor.module_key) for anchor in index.menus if anchor.module_key == module] == [
        ("platform", module)
    ]
    assert next(anchor for anchor in index.menus if anchor.module_key == module).model_id == int(menu.id)
    assert {key: value for key, value in index.forms.items() if key.startswith(ns.prefix)} == {
        business_code: f"platform:{module}:{business_code}::",
        _code(ns, "orphan"): f"platform:{module}:{_code(ns, 'orphan')}::",
    }
    assert {key: value for key, value in index.fields.items() if key[0].startswith(ns.prefix)} == {
        (business_code, field_key): f"platform:{module}:{business_code}:{field_key}:"
    }
    assert {key: value for key, value in index.buttons.items() if key[0].startswith(ns.prefix)} == {
        (business_code, create_code): f"platform:{module}:{business_code}::{create_code}"
    }
    assert {key: value for key, value in index.actions.items() if key.startswith(ns.prefix)} == {
        create_code: f"platform::::{create_code}"
    }


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
