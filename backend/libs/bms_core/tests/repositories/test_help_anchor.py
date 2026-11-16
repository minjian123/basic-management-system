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

from bms_core.models.platform.menu_form import SysButton, SysField, SysForm, SysMenu
from bms_core.models.platform.permission_meta import SysAction
from bms_core.repositories.help_anchor import find_help_key_conflict, list_help_anchors
from bms_core.testing.transaction import rollback_session

_MODELS = (SysMenu, SysForm, SysField, SysButton, SysAction)


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
        AsyncSession: 会话（用例结束整体回滚）。
    """
    async with rollback_session(engine) as db_session:
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
