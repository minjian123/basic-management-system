"""帮助锚点种子声明与 upsert（08_01；Kiwi 2520）。

被测对象：`bms_core/tenant/seed/help_anchor.py`。锁死四条口径：整批校验（任一违规零写入）、
按自然键定位、仅差异更新、装载不清空。
"""

from collections.abc import AsyncIterator
from functools import partial
from typing import cast

import pytest
from sqlalchemy import Connection, Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import MenuHelpKeyInvalidError
from bms_core.help.anchors import HelpAnchorKind
from bms_core.models.platform.menu_form import SysButton, SysField, SysForm, SysMenu
from bms_core.models.platform.permission_meta import SysAction, SysBusiness, SysPermission
from bms_core.tenant.seed.help_anchor import HelpAnchorDeclaration, apply_help_anchor_declarations
from bms_core.testing.transaction import rollback_session

_MODELS = (SysMenu, SysForm, SysField, SysButton, SysAction, SysBusiness, SysPermission)


def _create_table(table: Table, connection: Connection) -> None:
    """幂等建表。

    Args:
        table: 表定义。
        connection: 同步连接。
    """
    table.create(connection, checkfirst=True)


@pytest.fixture
async def engine(shared_platform_engine: AsyncEngine) -> AsyncEngine:
    """共享平台库引擎（幂等建本文件需要的表）。

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


class _Graph:
    """一棵最小元数据图（菜单 / 业务 / 表单 / 字段 / 动作 / 权限码 / 按钮）。"""

    def __init__(self, session: AsyncSession) -> None:
        """初始化。

        Args:
            session: 会话。
        """
        self.session = session
        self.menu = SysMenu(name="用户管理", path="/probe/users", status="enabled")
        self.business = SysBusiness(code="probe_user", name="用户", status="enabled")
        self.form = SysForm(business_id=0, status="enabled")
        self.field = SysField(form_id=0, field_key="username", name="用户名", type="input", status="enabled")
        self.action = SysAction(code="probe_create", name="新建", status="enabled")
        self.permission = SysPermission(business_id=0, action_id=0, status="enabled")
        self.button = SysButton(form_id=0, permission_id=0, name="新建", type="toolbar", status="enabled")

    async def setup(self) -> _Graph:
        """落库并回填逻辑外键。

        Returns:
            _Graph: 自身（链式调用）。
        """
        self.session.add_all([self.menu, self.business, self.action])
        await self.session.flush()
        self.form.business_id = int(self.business.id)
        self.session.add(self.form)
        await self.session.flush()
        self.field.form_id = int(self.form.id)
        self.permission.business_id = int(self.business.id)
        self.permission.action_id = int(self.action.id)
        self.session.add_all([self.field, self.permission])
        await self.session.flush()
        self.button.form_id = int(self.form.id)
        self.button.permission_id = int(self.permission.id)
        self.session.add(self.button)
        await self.session.flush()
        return self


def _declarations(
    graph: _Graph, *, menu_key: str = "platform:platform:::"
) -> ConcurrentStableList[HelpAnchorDeclaration]:
    """构造五类声明（菜单 / 表单 / 字段 / 按钮 / 动作码）。

    Args:
        graph: 元数据图。
        menu_key: 菜单锚点值（用于验证差异更新）。

    Returns:
        ConcurrentStableList[HelpAnchorDeclaration]: 声明清单。
    """
    return ConcurrentStableList(
        (
            HelpAnchorDeclaration(
                kind=HelpAnchorKind.MENU,
                help_key=menu_key,
                declaring_product="platform",
                menu_path=graph.menu.path,
            ),
            HelpAnchorDeclaration(
                kind=HelpAnchorKind.FORM,
                help_key="platform:platform:probe_user::",
                declaring_product="platform",
                business_code=graph.business.code,
            ),
            HelpAnchorDeclaration(
                kind=HelpAnchorKind.FIELD,
                help_key="platform:platform:probe_user:username:",
                declaring_product="platform",
                business_code=graph.business.code,
                field_key="username",
            ),
            HelpAnchorDeclaration(
                kind=HelpAnchorKind.BUTTON,
                help_key="platform:platform:probe_user::probe_create",
                declaring_product="platform",
                business_code=graph.business.code,
                action_code=graph.action.code,
            ),
            HelpAnchorDeclaration(
                kind=HelpAnchorKind.ACTION,
                help_key="platform::::probe_create",
                declaring_product="platform",
                action_code=graph.action.code,
            ),
        )
    )


@pytest.mark.kiwi_id(2520)
async def test_upsert_lifecycle_create_unchanged_update(session: AsyncSession) -> None:
    """首次装载全新增、重复装载全跳过、差异声明只更新该条。"""
    graph = await _Graph(session).setup()

    first = await apply_help_anchor_declarations(session, _declarations(graph))
    assert (first.created, first.updated, first.unchanged) == (5, 0, 0)
    assert graph.menu.help_key == "platform:platform:::"
    assert graph.form.help_key == "platform:platform:probe_user::"
    assert graph.field.help_key == "platform:platform:probe_user:username:"
    assert graph.button.help_key == "platform:platform:probe_user::probe_create"
    assert graph.action.help_key == "platform::::probe_create"

    second = await apply_help_anchor_declarations(session, _declarations(graph))
    assert (second.created, second.updated, second.unchanged) == (0, 0, 5)

    third = await apply_help_anchor_declarations(session, _declarations(graph, menu_key="platform:renamed:::"))
    assert (third.created, third.updated, third.unchanged) == (0, 1, 4)
    assert graph.menu.help_key == "platform:renamed:::"


@pytest.mark.kiwi_id(2520)
async def test_invalid_declaration_rejects_whole_batch(session: AsyncSession) -> None:
    """任一条格式违规 → 整批不写（合法条目也保持未登记）。"""
    graph = await _Graph(session).setup()
    bad = ConcurrentStableList(
        (
            _declarations(graph)[0],
            HelpAnchorDeclaration(
                kind=HelpAnchorKind.FORM,
                help_key="platform:platform",
                declaring_product="platform",
                business_code=graph.business.code,
            ),
        )
    )
    with pytest.raises(MenuHelpKeyInvalidError) as exc:
        await apply_help_anchor_declarations(session, bad)
    assert "段数" in str(exc.value)
    assert graph.menu.help_key is None
    assert graph.form.help_key is None


@pytest.mark.kiwi_id(2520)
async def test_empty_declaration_value_is_rejected(session: AsyncSession) -> None:
    """装载声明必须显式给出锚点（空值不等于未登记、也不是清空）。"""
    graph = await _Graph(session).setup()
    with pytest.raises(MenuHelpKeyInvalidError) as exc:
        await apply_help_anchor_declarations(
            session,
            ConcurrentStableList(
                (
                    HelpAnchorDeclaration(
                        kind=HelpAnchorKind.MENU,
                        help_key="   ",
                        declaring_product="platform",
                        menu_path=graph.menu.path,
                    ),
                )
            ),
        )
    assert "必须给出 help_key" in str(exc.value)


@pytest.mark.kiwi_id(2520)
async def test_duplicate_keys_in_batch_are_rejected(session: AsyncSession) -> None:
    """批内同一 help_key 重复声明 → 整批拒。"""
    graph = await _Graph(session).setup()
    other_menu = SysMenu(name="另一菜单", path="/probe/other", status="enabled")
    session.add(other_menu)
    await session.flush()
    duplicate = ConcurrentStableList(
        (
            HelpAnchorDeclaration(
                kind=HelpAnchorKind.MENU,
                help_key="platform:platform:::",
                declaring_product="platform",
                menu_path=graph.menu.path,
            ),
            HelpAnchorDeclaration(
                kind=HelpAnchorKind.MENU,
                help_key="platform:platform:::",
                declaring_product="platform",
                menu_path=other_menu.path,
            ),
        )
    )
    with pytest.raises(MenuHelpKeyInvalidError) as exc:
        await apply_help_anchor_declarations(session, duplicate)
    assert "批内 help_key 重复" in str(exc.value)


@pytest.mark.kiwi_id(2520)
async def test_conflict_with_other_row_is_rejected(session: AsyncSession) -> None:
    """声明的键已被其它元数据行占用 → 整批拒（不静默覆盖）。"""
    graph = await _Graph(session).setup()
    graph.form.help_key = "platform:platform:::"
    await session.flush()
    with pytest.raises(MenuHelpKeyInvalidError) as exc:
        await apply_help_anchor_declarations(session, _declarations(graph))
    assert "已被 sys_form" in str(exc.value)


@pytest.mark.kiwi_id(2520)
async def test_declaring_product_mismatch_is_rejected(session: AsyncSession) -> None:
    """声明方产品与首段不一致 → 整批拒。"""
    graph = await _Graph(session).setup()
    with pytest.raises(MenuHelpKeyInvalidError) as exc:
        await apply_help_anchor_declarations(
            session,
            ConcurrentStableList(
                (
                    HelpAnchorDeclaration(
                        kind=HelpAnchorKind.MENU,
                        help_key="biz:biz:::",
                        declaring_product="platform",
                        menu_path=graph.menu.path,
                    ),
                )
            ),
        )
    assert "与声明方不一致" in str(exc.value)


@pytest.mark.kiwi_id(2520)
async def test_missing_targets_and_natural_keys_are_rejected(session: AsyncSession) -> None:
    """自然键缺失 / 目标不存在 → 整批拒（错误信息带声明摘要）。"""
    graph = await _Graph(session).setup()
    cases = ConcurrentStableList(
        (
            HelpAnchorDeclaration(kind=HelpAnchorKind.MENU, help_key="platform:a:::", declaring_product="platform"),
            HelpAnchorDeclaration(kind=HelpAnchorKind.ACTION, help_key="platform::::a", declaring_product="platform"),
            HelpAnchorDeclaration(kind=HelpAnchorKind.FORM, help_key="platform:a:b::", declaring_product="platform"),
            HelpAnchorDeclaration(
                kind=HelpAnchorKind.MENU,
                help_key="platform:b:::",
                declaring_product="platform",
                menu_path="/probe/absent",
            ),
            HelpAnchorDeclaration(
                kind=HelpAnchorKind.FORM,
                help_key="platform:a:absent::",
                declaring_product="platform",
                business_code="absent_business",
            ),
            HelpAnchorDeclaration(
                kind=HelpAnchorKind.FIELD,
                help_key="platform:a:b:c:",
                declaring_product="platform",
                business_code=graph.business.code,
            ),
            HelpAnchorDeclaration(
                kind=HelpAnchorKind.FIELD,
                help_key="platform:a:b:absent:",
                declaring_product="platform",
                business_code=graph.business.code,
                field_key="absent_field",
            ),
            HelpAnchorDeclaration(
                kind=HelpAnchorKind.BUTTON,
                help_key="platform:a:b::absent",
                declaring_product="platform",
                business_code=graph.business.code,
            ),
            HelpAnchorDeclaration(
                kind=HelpAnchorKind.BUTTON,
                help_key="platform:a:b::absent",
                declaring_product="platform",
                business_code=graph.business.code,
                action_code="absent_action",
            ),
        )
    )
    for declaration in cases:
        with pytest.raises(MenuHelpKeyInvalidError) as exc:
            await apply_help_anchor_declarations(session, ConcurrentStableList((declaration,)))
        assert "目标元数据不存在" in str(exc.value)


@pytest.mark.kiwi_id(2520)
async def test_missing_permission_and_button_are_rejected(session: AsyncSession) -> None:
    """动作存在但权限码 / 按钮未建 → 目标不存在（逐个探测分支）。"""
    graph = await _Graph(session).setup()
    query_action = SysAction(code="probe_query", name="查询", status="enabled")
    session.add(query_action)
    await session.flush()
    # 动作存在、权限码未建
    with pytest.raises(MenuHelpKeyInvalidError) as no_permission:
        await apply_help_anchor_declarations(
            session,
            ConcurrentStableList(
                (
                    HelpAnchorDeclaration(
                        kind=HelpAnchorKind.BUTTON,
                        help_key="platform:a:b::probe_query",
                        declaring_product="platform",
                        business_code=graph.business.code,
                        action_code=query_action.code,
                    ),
                )
            ),
        )
    assert "目标元数据不存在" in str(no_permission.value)

    # 权限码补建、按钮未建
    permission = SysPermission(business_id=int(graph.business.id), action_id=int(query_action.id), status="enabled")
    session.add(permission)
    await session.flush()
    with pytest.raises(MenuHelpKeyInvalidError) as no_button:
        await apply_help_anchor_declarations(
            session,
            ConcurrentStableList(
                (
                    HelpAnchorDeclaration(
                        kind=HelpAnchorKind.BUTTON,
                        help_key="platform:a:b::probe_query",
                        declaring_product="platform",
                        business_code=graph.business.code,
                        action_code=query_action.code,
                    ),
                )
            ),
        )
    assert "目标元数据不存在" in str(no_button.value)


@pytest.mark.kiwi_id(2520)
async def test_missing_form_is_rejected(session: AsyncSession) -> None:
    """业务存在但表单未建 → 目标不存在。"""
    business = SysBusiness(code="probe_orphan", name="孤儿", status="enabled")
    session.add(business)
    await session.flush()
    with pytest.raises(MenuHelpKeyInvalidError) as exc:
        await apply_help_anchor_declarations(
            session,
            ConcurrentStableList(
                (
                    HelpAnchorDeclaration(
                        kind=HelpAnchorKind.FORM,
                        help_key="platform:a:b::",
                        declaring_product="platform",
                        business_code=business.code,
                    ),
                )
            ),
        )
    assert "目标元数据不存在" in str(exc.value)
