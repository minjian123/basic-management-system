"""平台种子去产品化用例（07B `03_03`；Kiwi 2254 改造）：平台种子不含产品条目、动作码字典不变。"""

from collections.abc import AsyncIterator
from functools import partial

import pytest
from sqlalchemy import Connection, Table, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.models.platform.menu_form import SysButton, SysField, SysForm, SysMenu
from bms_core.models.platform.permission_meta import SysAction, SysBusiness
from bms_core.tenant.seed import menu as seed_menu
from bms_core.testing.transaction import rollback_session

# 07B `03_03` 改造前的清单规模（凭据：设计 §2.1 实测 44 / 110 / 31）。
# 2026-10-31 起基线记「含平台后续新增条目」：08-02_02 补 `config:manage`（110 → 111）、
# 08-03_01 补 `file:manage`（111 → 112）、03_06 补 `job` 业务码与 query / manage 权限码（44 → 45、112 → 114）；
# 2026-11-16/17 通知与公告三条任务补 notification / notice 权限码（114 → 123）与动作码（31 → 32）；
# 08_04 补 `help:manage`（123 → 124，当时未同步本基线，2026-11-18 一并校正）、
# 10_02 补 `formdesign:manage`（124 → 125）、11_01 补 `dashboard:manage`（125 → 126）、
# 12_01 补 `help:package`（126 → 127；动作码字典新增 `package` → 32 → 33）。
_BUSINESS_BEFORE = 45
_PERMISSIONS_BEFORE = 127
_ACTIONS_BEFORE = 33


@pytest.mark.kiwi_id(2254)
def test_platform_seed_has_no_product_entries() -> None:
    """平台种子只播平台自身数据：业务码与权限码清单不含产品条目。"""
    business_codes = {code for code, _zh, _en in seed_menu.BUSINESS_SEEDS}
    assert "mdm" not in business_codes
    permissions = {(business, action) for business, action, _zh, _en in seed_menu.PERMISSION_SEEDS}
    assert not {business for business, _action in permissions} - business_codes
    assert all(not business.startswith("mdm") for business, _action in permissions)


@pytest.mark.kiwi_id(2254)
def test_platform_seed_counts_drop_by_product_entries() -> None:
    """只移除产品条目：业务码 −1、权限码 −4，平台条目一条不少。"""
    assert len(seed_menu.BUSINESS_SEEDS) == _BUSINESS_BEFORE - 1
    assert len(seed_menu.PERMISSION_SEEDS) == _PERMISSIONS_BEFORE - 4


@pytest.mark.kiwi_id(2254)
def test_action_dictionary_unchanged() -> None:
    """动作码字典由平台权限码派生：移除产品权限码后动词集合不减少。"""
    actions = {code for code, _zh, _en in seed_menu.ACTION_SEEDS}
    assert len(actions) == _ACTIONS_BEFORE
    assert {"query", "create", "update", "delete"} <= actions


@pytest.mark.kiwi_id(2254)
def test_seed_lists_have_unique_keys() -> None:
    """业务码、动作码与「业务码 + 动作码」种子不重复（幂等键唯一，重跑不产生重复行）。"""
    business_codes = [code for code, _zh, _en in seed_menu.BUSINESS_SEEDS]
    assert len(business_codes) == len(set(business_codes))
    actions = [code for code, _zh, _en in seed_menu.ACTION_SEEDS]
    assert len(actions) == len(set(actions))
    permissions = [(business, action) for business, action, _zh, _en in seed_menu.PERMISSION_SEEDS]
    assert len(permissions) == len(set(permissions))


def _create_table(table: Table, connection: Connection) -> None:
    """幂等建表（共享平台库上只补菜单元数据表）。

    Args:
        table: 表定义。
        connection: 同步连接。
    """
    table.create(connection, checkfirst=True)


@pytest.fixture
async def seed_session(shared_platform_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """菜单元数据表已建的回滚会话。

    Args:
        shared_platform_engine: 共享平台库引擎。

    Yields:
        AsyncSession: 会话（用例结束整体回滚）。
    """
    async with shared_platform_engine.begin() as connection:
        for table in seed_menu._MENU_TABLES:  # pyright: ignore[reportPrivateUsage]
            await connection.run_sync(partial(_create_table, table))
    async with rollback_session(shared_platform_engine) as session:
        yield session


@pytest.mark.kiwi_id(2520)
async def test_platform_seed_applies_help_key_declarations(
    seed_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """平台种子装载可选锚点声明（五类全覆盖，装载后元数据可查）。"""
    monkeypatch.setattr(
        seed_menu,
        "MENU_HELP_KEYS",
        ConcurrentStableDict({"/sys/users": "platform:seed_users:::"}),
    )
    monkeypatch.setattr(
        seed_menu,
        "FORM_HELP_KEYS",
        ConcurrentStableDict({"user": "platform:seed_users:user::"}),
    )
    monkeypatch.setattr(
        seed_menu,
        "FIELD_HELP_KEYS",
        ConcurrentStableDict({("user", "username"): "platform:seed_users:user:username:"}),
    )
    monkeypatch.setattr(
        seed_menu,
        "BUTTON_HELP_KEYS",
        ConcurrentStableDict({("user", "create"): "platform:seed_users:user::create"}),
    )
    monkeypatch.setattr(
        seed_menu,
        "ACTION_HELP_KEYS",
        ConcurrentStableDict({"create": "platform::::create"}),
    )
    await seed_menu._seed_menu_in_session(seed_session)  # pyright: ignore[reportPrivateUsage]

    menu = (await seed_session.execute(select(SysMenu).where(SysMenu.path == "/sys/users"))).scalars().first()
    assert menu is not None
    assert menu.help_key == "platform:seed_users:::"
    business = (await seed_session.execute(select(SysBusiness).where(SysBusiness.code == "user"))).scalars().first()
    assert business is not None
    business_form = (
        (await seed_session.execute(select(SysForm).where(SysForm.business_id == business.id))).scalars().first()
    )
    assert business_form is not None
    assert business_form.help_key == "platform:seed_users:user::"
    field = (
        (
            await seed_session.execute(
                select(SysField).where(SysField.form_id == business_form.id, SysField.field_key == "username")
            )
        )
        .scalars()
        .first()
    )
    assert field is not None
    assert field.help_key == "platform:seed_users:user:username:"
    button = (
        (await seed_session.execute(select(SysButton).where(SysButton.help_key == "platform:seed_users:user::create")))
        .scalars()
        .first()
    )
    assert button is not None
    action = (await seed_session.execute(select(SysAction).where(SysAction.code == "create"))).scalars().first()
    assert action is not None
    assert action.help_key == "platform::::create"
