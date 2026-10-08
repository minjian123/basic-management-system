"""字段权限用例（`02_04`）：静态收窄求值 + 多角色从严 + 快照字段态查询。

覆盖：`sys_role_field` 收窄项解析（`field_id → field_key` 合流）、多角色**从严合并**
（任一角色不可见即不可见 / 任一不可编辑即不可编辑）、表单过滤与空角色短路、默认全开
（未收窄字段不进结果）、快照 `field_state` 与豁免层级。
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.models.base import Base
from bms_core.permission.field import (
    DEFAULT_FIELD_PERMISSION_PROVIDER_KEY,
    FieldPermission,
    current_field_permission_provider_factory,
    register_field_permission_provider_factory,
    reset_field_permission_provider_factories,
)
from bms_core.permission.snapshot import TIER_STANDARD, TIER_SYSTEM_ADMIN, PermissionSnapshot
from bms_platform.models.menu import SysField
from bms_platform.models.role import SysRoleField
from bms_platform.permission.field_provider import StaticFieldPermissionProvider, build_static_field_provider

_FORM_ID = 7001
_OTHER_FORM_ID = 7002


@pytest_asyncio.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    """最小库会话：字段元数据（`sys_field`）+ 角色字段收窄（`sys_role_field`）。

    Args:
        tmp_path: pytest 临时目录。

    Yields:
        AsyncSession: 会话（用例内直插种子数据）。
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'field.db'}")
    tables = [SysField.__table__, SysRoleField.__table__]
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as opened:
        yield opened
    await engine.dispose()


async def _seed(session: AsyncSession) -> ConcurrentStableDict[str, int]:
    """播种两个字段与两个角色的收窄项。

    Args:
        session: 会话。

    Returns:
        ConcurrentStableDict[str, int]: 字段键 → 字段主键（测试断言用）。
    """
    salary = SysField(form_id=_FORM_ID, field_key="salary", name="薪资", type="number", sort=1)
    name = SysField(form_id=_FORM_ID, field_key="name", name="姓名", type="text", sort=2)
    session.add_all([salary, name])
    await session.flush()
    session.add_all(
        [
            SysRoleField(role_id=10, form_id=_FORM_ID, field_id=salary.id, visible=False, editable=False),
            SysRoleField(role_id=11, form_id=_FORM_ID, field_id=salary.id, visible=True, editable=False),
        ]
    )
    await session.commit()
    keys: ConcurrentStableDict[str, int] = ConcurrentStableDict()
    keys.set("salary", salary.id)
    keys.set("name", name.id)
    return keys


async def test_static_provider_merges_narrowing_strictly(session: AsyncSession) -> None:
    """多角色从严合并：任一角色不可见即不可见、任一不可编辑即不可编辑；未收窄字段不进结果。"""
    keys = await _seed(session)
    provider = StaticFieldPermissionProvider(session, session)
    role_ids: ConcurrentStableSet[int] = ConcurrentStableSet()
    role_ids.add(10)
    role_ids.add(11)
    perms = await provider.resolve(role_ids=role_ids, form_ids=ConcurrentStableSet[int]())
    assert keys.get("salary") is not None
    assert len(perms) == 1
    only = perms[0]
    assert (only.form_id, only.field_key) == (_FORM_ID, "salary")
    assert only.visible is False
    assert only.editable is False
    assert provider.key == DEFAULT_FIELD_PERMISSION_PROVIDER_KEY


async def test_static_provider_form_filter_and_empty_roles(session: AsyncSession) -> None:
    """表单过滤与空角色短路：不匹配表单不收窄项，无角色直接返回空。"""
    await _seed(session)
    provider = StaticFieldPermissionProvider(session, session)
    roles: ConcurrentStableSet[int] = ConcurrentStableSet()
    roles.add(10)
    other_form: ConcurrentStableSet[int] = ConcurrentStableSet()
    other_form.add(_OTHER_FORM_ID)
    assert list(await provider.resolve(role_ids=roles, form_ids=other_form)) == []
    assert list(await provider.resolve(role_ids=ConcurrentStableSet[int](), form_ids=other_form)) == []


async def test_field_provider_factory_registry_supports_override(session: AsyncSession) -> None:
    """工厂注册表：登记后可按会话构造，末位登记生效（后代档位覆盖口径）。"""
    reset_field_permission_provider_factories()
    register_field_permission_provider_factory(DEFAULT_FIELD_PERMISSION_PROVIDER_KEY, build_static_field_provider)
    factory = current_field_permission_provider_factory()
    assert factory is not None
    provider = factory(session, session)
    assert isinstance(provider, StaticFieldPermissionProvider)
    reset_field_permission_provider_factories()
    assert current_field_permission_provider_factory() is None


def test_snapshot_field_state_defaults_and_exempt() -> None:
    """快照字段态：未收窄返回 None（默认全开）；豁免层级不参与收窄。"""
    perms: ConcurrentStableList[FieldPermission] = ConcurrentStableList()
    perms.add(FieldPermission(form_id=_FORM_ID, field_key="salary", visible=False, editable=True))
    snapshot = PermissionSnapshot(tier=TIER_STANDARD, field_perms=perms)
    assert snapshot.field_state(_FORM_ID, "salary") == (False, True)
    assert snapshot.field_state(_FORM_ID, "name") is None
    assert snapshot.exempt is False
    assert PermissionSnapshot(tier=TIER_SYSTEM_ADMIN).exempt is True
