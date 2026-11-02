"""导入定义预检分支：空值 / 非字符串 / 库内已存在 / 状态非法。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.core.concurrent import (
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenSet,
    ConcurrentStableList,
)
from bms_core.models.platform.role import SysRole, SysUserRole
from bms_core.models.platform.user import SysUser
from bms_core.password.default import DefaultPasswordPolicy
from bms_core.security.pbkdf2 import Pbkdf2PasswordHasher
from bms_core.testing.schema import ensure_tables
from bms_core.transfer.importer import ParsedRow
from bms_platform.domains.role.imports import RoleImportDefinition, _RolePreload  # pyright: ignore[reportPrivateUsage]
from bms_platform.domains.role.services.role import RoleService
from bms_platform.domains.user.imports import UserImportDefinition, _UserPreload  # pyright: ignore[reportPrivateUsage]
from bms_platform.domains.user.services.users_admin import UserAdminService

pytestmark = [pytest.mark.kiwi_id(2401), pytest.mark.usefixtures("serial_db_write")]


def _unused(*_args: object, **_kwargs: object) -> UserAdminService:
    """未使用的写服务工厂。"""
    raise AssertionError("不应调用写路径")


def _unused_role(*_args: object, **_kwargs: object) -> RoleService:
    """未使用的角色写服务工厂。"""
    raise AssertionError("不应调用写路径")


def _policy() -> DefaultPasswordPolicy:
    """密码策略。"""
    return DefaultPasswordPolicy(config=None, hasher=Pbkdf2PasswordHasher(iterations=100000))  # type: ignore[arg-type]


@pytest_asyncio.fixture
async def factory(shared_tenant_engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """共享租户库会话工厂（建导入涉及表）。"""
    tables: list[Table] = cast(  # bare-collections:allow（SQLAlchemy 表清单）
        "list[Table]",
        [
            SysUser.__table__,
            SysRole.__table__,
            SysUserRole.__table__,
        ],
    )
    await ensure_tables(shared_tenant_engine, tables)
    yield async_sessionmaker(shared_tenant_engine, expire_on_commit=False)


async def test_user_preload_skips_invalid_and_blank(factory: async_sessionmaker[AsyncSession]) -> None:
    """非字符串 / 空白账号不进入已存在查询（空集早返回）。"""
    definition = UserImportDefinition(service_factory=_unused, policy=_policy())
    rows = ConcurrentStableList(
        (
            ParsedRow(row_no=2, values={"username": 123}),  # type: ignore[arg-type]
            ParsedRow(row_no=3, values={"username": "   "}),  # type: ignore[arg-type]
        )
    )
    async with factory() as session:
        state = await definition.preload(session, rows)
    assert not state.existing
    assert not state.duplicates


async def test_user_validate_existing() -> None:
    """库内已存在账号 → 行错误。"""
    definition = UserImportDefinition(service_factory=_unused, policy=_policy())
    state = _UserPreload(  # pyright: ignore[reportPrivateUsage]
        existing=ConcurrentStableFrozenSet({"taken"}),
        duplicates=ConcurrentStableFrozenSet(),
    )
    row = ParsedRow(
        row_no=2,
        values=ConcurrentStableFrozenDict[str, object]({"username": "taken", "name": "甲", "status": "启用"}),
    )
    errors = await definition.validate_row(row, state, config=None)
    assert [(error.field, error.message) for error in errors] == [("username", "登录账号已存在")]


async def test_role_preload_skips_invalid_and_blank(factory: async_sessionmaker[AsyncSession]) -> None:
    """非字符串 / 空白角色码不进入已存在查询（空集早返回）。"""
    definition = RoleImportDefinition(service_factory=_unused_role)
    rows = ConcurrentStableList(
        (
            ParsedRow(row_no=2, values={"code": 123}),  # type: ignore[arg-type]
            ParsedRow(row_no=3, values={"code": "   "}),  # type: ignore[arg-type]
        )
    )
    async with factory() as session:
        state = await definition.preload(session, rows)
    assert not state.existing
    assert not state.duplicates


async def test_role_validate_existing_and_status() -> None:
    """库内已存在角色码 / 状态非法 → 行错误。"""
    definition = RoleImportDefinition(service_factory=_unused_role)
    state = _RolePreload(  # pyright: ignore[reportPrivateUsage]
        existing=ConcurrentStableFrozenSet({"taken_role"}),
        duplicates=ConcurrentStableFrozenSet(),
    )
    row = ParsedRow(  # type: ignore[arg-type]
        row_no=2,
        values=ConcurrentStableFrozenDict[str, object]({"code": "taken_role", "name": "甲", "status": "未知"}),
    )
    errors = await definition.validate_row(row, state, config=None)
    assert {(error.field, error.message) for error in errors} == {
        ("code", "角色码已存在"),
        ("status", "状态取值非法"),
    }
