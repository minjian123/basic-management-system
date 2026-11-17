"""帮助覆盖率只读快照（08_04；Kiwi 2523）。

被测对象：`bms_core/repositories/help_coverage.py`。锁死：启用 / 未软删过滤、权限码与表单 / 菜单关联、
模块映射、表单 / 字段参考行、动作码兜底与锚点复用。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import partial
from typing import cast

import pytest
from sqlalchemy import Connection, Table, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.models.platform.catalog import SysModule
from bms_core.models.platform.menu_form import SysButton, SysField, SysForm, SysMenu, SysMenuForm
from bms_core.models.platform.permission_meta import SysAction, SysBusiness, SysPermission
from bms_core.repositories.help_coverage import load_help_coverage_snapshot
from bms_core.testing.transaction import rollback_session

_MODELS = (SysBusiness, SysAction, SysPermission, SysForm, SysMenu, SysMenuForm, SysButton, SysField, SysModule)


def _create_table(table: Table, connection: Connection) -> None:
    """幂等建表（共享库上只补本文件需要的表）。

    Args:
        table: 表定义。
        connection: 同步连接。
    """
    table.create(connection, checkfirst=True)


@pytest.fixture
async def engine(shared_platform_engine: AsyncEngine) -> AsyncEngine:
    """共享平台库引擎（幂等建相关表）。

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


async def _seed_metadata(session: AsyncSession, prefix: str) -> tuple[SysForm, SysMenu, SysButton, SysButton]:
    """构造一套帮助覆盖率元数据。

    Args:
        session: 会话。
        prefix: 键前缀（隔离同名用例）。

    Returns:
        tuple: （表单，菜单，已声明按钮，未声明按钮）。
    """
    business = SysBusiness(code=f"{prefix}_biz", name="覆盖率业务", status="enabled")
    action = SysAction(code=f"{prefix}_act", name="覆盖率动作", status="enabled")
    fallback = SysAction(
        code=f"{prefix}_fallback", name="兜底动作", status="enabled", help_key=f"platform::::{prefix}_fb"
    )
    session.add_all([business, action, fallback])
    await session.flush()
    permission = SysPermission(business_id=business.id, action_id=action.id, status="enabled")
    session.add(permission)
    await session.flush()
    menu = SysMenu(name="覆盖率菜单", path=f"/probe/{prefix}", component="probe/view", status="enabled")
    session.add(menu)
    await session.flush()
    form = SysForm(business_id=business.id, component="probe/view", status="enabled")
    session.add(form)
    await session.flush()
    session.add(SysMenuForm(menu_id=menu.id, form_id=form.id))
    covered = SysButton(
        form_id=form.id,
        permission_id=permission.id,
        name="已声明按钮",
        status="enabled",
        help_key=f"platform:{prefix}:{prefix}_biz::{prefix}_act",
    )
    gap = SysButton(form_id=form.id, permission_id=permission.id + 1000, name="无效权限按钮", status="enabled")
    session.add_all([covered, gap])
    session.add(SysField(form_id=form.id, field_key="name", name="名称", type="input", status="enabled"))
    session.add(
        SysField(
            form_id=form.id,
            field_key="code",
            name="编码",
            type="input",
            status="enabled",
            help_key=f"platform:{prefix}:{prefix}_biz:code:",
        )
    )
    session.add(
        SysModule(
            module_key=prefix,
            name="覆盖率模块",
            table_prefix=f"{prefix}_",
            business_code=business.code,
            event_domain=prefix,
            product_key="biz",
            status="enabled",
        )
    )
    await session.flush()
    return form, menu, covered, gap


@pytest.mark.kiwi_id(2523)
async def test_snapshot_reads_enabled_rows_and_joins(session: AsyncSession) -> None:
    """启用行参与、关联与顺序正确；锚点复用 list_help_anchors。"""
    _form, menu, covered, _gap = await _seed_metadata(session, "probe_cov")
    snapshot = await load_help_coverage_snapshot(session)
    action = next(row for row in snapshot.actions if row.model_id == int(covered.id))
    assert action.business_code == "probe_cov_biz"
    assert action.action_code == "probe_cov_act"
    assert list(action.menu_paths) == ["/probe/probe_cov"]
    assert action.help_key is not None
    menu_row = next(row for row in snapshot.menus if row.model_id == int(menu.id))
    assert list(menu_row.business_codes) == ["probe_cov_biz"]
    assert any(row.business_code == "probe_cov_biz" and row.kind == "form" for row in snapshot.reference_rows)
    assert any(
        row.business_code == "probe_cov_biz" and row.kind == "field" and row.help_key for row in snapshot.reference_rows
    )
    module = next(row for row in snapshot.modules if row.business_code == "probe_cov_biz")
    assert (module.product_key, module.module_key) == ("biz", "probe_cov")
    assert any(anchor.model_id == int(covered.id) for anchor in snapshot.anchors)
    assert any(row.action_code == "probe_cov_fallback" and row.help_key for row in snapshot.action_fallbacks)
    assert "probe_cov_biz" in snapshot.business_codes_with_permission


@pytest.mark.kiwi_id(2523)
async def test_snapshot_excludes_disabled_and_soft_deleted(session: AsyncSession) -> None:
    """停用 / 软删 / 缺权限码的行不参与动作与菜单基准。"""
    form, menu, covered, gap = await _seed_metadata(session, "probe_cov_off")
    covered.status = "disabled"
    menu.soft_delete()
    session.add(SysButton(form_id=form.id, permission_id=0, name="缺权限", status="enabled"))
    await session.flush()
    snapshot = await load_help_coverage_snapshot(session)
    assert all(row.model_id != int(covered.id) for row in snapshot.actions)
    assert all(row.model_id != int(menu.id) for row in snapshot.menus)
    assert all(row.model_id != int(gap.id) for row in snapshot.actions)
    assert all(anchor.model_id != int(menu.id) for anchor in snapshot.anchors)


@pytest.mark.kiwi_id(2523)
async def test_snapshot_handles_missing_module_and_orphans(session: AsyncSession) -> None:
    """无模块登记时不伪造映射；基准外锚点保留给引擎对账。"""
    _form, menu, covered, _gap = await _seed_metadata(session, "probe_cov_orphan")
    module = (
        (await session.execute(select(SysModule).where(SysModule.business_code == "probe_cov_orphan_biz")))
        .scalars()
        .first()
    )
    assert module is not None
    module.soft_delete()
    await session.flush()
    snapshot = await load_help_coverage_snapshot(session)
    assert all(row.business_code != "probe_cov_orphan_biz" for row in snapshot.modules)
    assert any(anchor.model_id == int(covered.id) for anchor in snapshot.anchors)
    assert any(row.model_id == int(menu.id) for row in snapshot.menus)


@pytest.mark.kiwi_id(2523)
async def test_snapshot_deduplicates_shared_links(session: AsyncSession) -> None:
    """同一表单挂多菜单 / 同一菜单挂多表单 / 同业务多权限码时聚合去重。"""
    business = SysBusiness(code="probe_cov_shared_biz", name="共享业务", status="enabled")
    action_one = SysAction(code="probe_cov_shared_one", name="动作一", status="enabled")
    action_two = SysAction(code="probe_cov_shared_two", name="动作二", status="enabled")
    session.add_all([business, action_one, action_two])
    await session.flush()
    session.add_all(
        [
            SysPermission(business_id=business.id, action_id=action_one.id, status="enabled"),
            SysPermission(business_id=business.id, action_id=action_two.id, status="enabled"),
        ]
    )
    menu_one = SysMenu(name="共享菜单一", path="/probe/cov-shared-1", component="probe/view", status="enabled")
    menu_two = SysMenu(name="共享菜单二", path="/probe/cov-shared-2", component="probe/view", status="enabled")
    form_one = SysForm(business_id=business.id, component="probe/view", status="enabled")
    form_two = SysForm(business_id=business.id, component="probe/view", status="enabled")
    session.add_all([menu_one, menu_two, form_one, form_two])
    await session.flush()
    session.add_all(
        [
            SysMenuForm(menu_id=menu_one.id, form_id=form_one.id),
            SysMenuForm(menu_id=menu_two.id, form_id=form_one.id),
            SysMenuForm(menu_id=menu_one.id, form_id=form_two.id),
        ]
    )
    await session.flush()
    snapshot = await load_help_coverage_snapshot(session)
    menu_one_row = next(row for row in snapshot.menus if row.model_id == int(menu_one.id))
    assert list(menu_one_row.business_codes) == ["probe_cov_shared_biz"]
    form_actions = [row for row in snapshot.actions if row.business_code == "probe_cov_shared_biz"]
    assert len(form_actions) == 0
    assert snapshot.business_codes_with_permission.count("probe_cov_shared_biz") == 1


@pytest.mark.kiwi_id(2523)
async def test_snapshot_skips_rows_with_missing_links(session: AsyncSession) -> None:
    """权限码缺业务 / 缺动作、按钮 / 表单 / 字段缺业务时跳过，不造半套数据。"""
    business = SysBusiness(code="probe_cov_link_biz", name="链路业务", status="enabled")
    action = SysAction(code="probe_cov_link_act", name="链路动作", status="enabled")
    session.add_all([business, action])
    await session.flush()
    permission = SysPermission(business_id=business.id, action_id=action.id, status="enabled")
    session.add_all(
        [
            permission,
            SysPermission(business_id=business.id, action_id=999_000, status="enabled"),
            SysPermission(business_id=999_000, action_id=action.id, status="enabled"),
        ]
    )
    await session.flush()
    orphan_form = SysForm(business_id=999_000, component="probe/orphan", status="enabled")
    orphan_menu = SysMenu(name="孤儿菜单", path="/probe/cov-orphan", component="probe/orphan", status="enabled")
    session.add_all([orphan_form, orphan_menu])
    await session.flush()
    session.add(SysMenuForm(menu_id=orphan_menu.id, form_id=orphan_form.id))
    session.add(
        SysButton(
            form_id=orphan_form.id,
            permission_id=permission.id,
            name="孤儿按钮",
            status="enabled",
        )
    )
    session.add(SysField(form_id=orphan_form.id, field_key="name", name="名称", type="input", status="enabled"))
    await session.flush()
    snapshot = await load_help_coverage_snapshot(session)
    assert all(row.business_code != "probe_cov_link_biz" for row in snapshot.actions)
    assert all(row.business_code != "probe_cov_link_biz" for row in snapshot.reference_rows)
    assert all(row.business_code != "probe_cov_link_biz" for row in snapshot.modules)
