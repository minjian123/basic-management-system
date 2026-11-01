"""字段权限用例（`02_04`）：静态收窄求值 + 多角色从严 + 快照字段态查询。

覆盖：`sys_role_field` 收窄项解析（`field_id → field_key` 合流）、多角色**从严合并**
（任一角色不可见即不可见 / 任一不可编辑即不可编辑）、表单过滤与空角色短路、默认全开
（未收窄字段不进结果）、快照 `field_state` 与豁免层级。

单库叠加口径（04-6-2）：库用共享平台库、写入走 `rollback_session`（整体回滚不残留）；
角色主键按命名空间派生（`_role_id`），使「本角色只有一条收窄行」一类断言在用例叠加下仍成立。
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.models.base import Base
from bms_core.models.platform.menu_form import SysField
from bms_core.models.platform.role import SysRoleField
from bms_core.permission.field import (
    DEFAULT_FIELD_PERMISSION_PROVIDER_KEY,
    FieldPermission,
    current_field_permission_provider_factory,
    register_field_permission_provider_factory,
    reset_field_permission_provider_factories,
)
from bms_core.permission.snapshot import TIER_STANDARD, TIER_SYSTEM_ADMIN, PermissionSnapshot
from bms_core.testing.namespace import Namespace
from bms_core.testing.transaction import rollback_session
from bms_platform.domains.role.permission.field_provider import (
    StaticFieldPermissionProvider,
    build_static_field_provider,
)

_FORM_ID = 7001
_OTHER_FORM_ID = 7002

_TABLES: ConcurrentStableList[Table] = ConcurrentStableList(
    (cast("Table", SysField.__table__), cast("Table", SysRoleField.__table__))
)
"""本文件涉及的表（共享平台库幂等补齐）。"""


def _role_id(ns: Namespace, slot: int) -> int:
    """按命名空间派生角色主键（叠加下不与他人角色的收窄行相撞）。

    Args:
        ns: 用例命名空间。
        slot: 槽位（同一用例内区分多个角色）。

    Returns:
        int: 角色主键。
    """
    return int(ns.prefix[2:], 16) * 10 + slot


@dataclass(frozen=True)
class _Seeded:
    """播种结果（本用例专属角色主键与字段主键）。

    Attributes:
        keys: 字段键 → 字段主键。
        strict_role: 收窄为「不可见 + 不可编辑」的角色。
        loose_role: 收窄为「可见 + 不可编辑」的角色。
        ghost_role: 收窄项指向未登记字段的角色。
        empty_role: 无任何收窄行的角色。
    """

    keys: ConcurrentStableDict[str, int]
    strict_role: int
    loose_role: int
    ghost_role: int
    empty_role: int


def _build_field_provider(session: AsyncSession, platform_session: AsyncSession) -> object:
    """按当前登记的工厂构造字段权限求值器（下沉后由平台数据来源调用，语义不变）。

    Args:
        session: 租户库会话。
        platform_session: 平台库会话。

    Returns:
        object: 求值器；未登记工厂为 None。
    """
    factory = current_field_permission_provider_factory()
    if factory is None:
        return None
    return factory(session, platform_session)


@pytest_asyncio.fixture
async def session(shared_platform_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """共享平台库上的回滚会话：字段元数据（`sys_field`）+ 角色字段收窄（`sys_role_field`）。

    Args:
        shared_platform_engine: 共享平台库引擎。

    Yields:
        AsyncSession: 回滚会话（用例内直插种子数据，结束整体回滚）。
    """
    async with shared_platform_engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=list(_TABLES)))
    async with rollback_session(shared_platform_engine) as opened:
        yield opened


async def _seed(session: AsyncSession, ns: Namespace) -> _Seeded:
    """播种两个字段与两个角色的收窄项（角色主键按命名空间派生）。

    Args:
        session: 会话。
        ns: 用例命名空间。

    Returns:
        _Seeded: 播种结果（字段键 → 字段主键与角色主键）。
    """
    salary = SysField(form_id=_FORM_ID, field_key="salary", name="薪资", type="number", sort=1)
    name = SysField(form_id=_FORM_ID, field_key="name", name="姓名", type="text", sort=2)
    session.add_all([salary, name])
    await session.flush()
    strict_role = _role_id(ns, 0)
    loose_role = _role_id(ns, 1)
    session.add_all(
        [
            SysRoleField(role_id=strict_role, form_id=_FORM_ID, field_id=salary.id, visible=False, editable=False),
            SysRoleField(role_id=loose_role, form_id=_FORM_ID, field_id=salary.id, visible=True, editable=False),
        ]
    )
    await session.commit()
    keys: ConcurrentStableDict[str, int] = ConcurrentStableDict()
    keys.set("salary", salary.id)
    keys.set("name", name.id)
    return _Seeded(
        keys=keys,
        strict_role=strict_role,
        loose_role=loose_role,
        ghost_role=_role_id(ns, 2),
        empty_role=_role_id(ns, 3),
    )


@pytest.mark.kiwi_id(2269)
async def test_static_provider_merges_narrowing_strictly(session: AsyncSession, ns: Namespace) -> None:
    """多角色从严合并：任一角色不可见即不可见、任一不可编辑即不可编辑；未收窄字段不进结果。"""
    seeded = await _seed(session, ns)
    provider = StaticFieldPermissionProvider(session, session)
    role_ids: ConcurrentStableSet[int] = ConcurrentStableSet()
    role_ids.add(seeded.strict_role)
    role_ids.add(seeded.loose_role)
    perms = await provider.resolve(role_ids=role_ids, form_ids=ConcurrentStableSet[int]())
    assert seeded.keys.get("salary") is not None
    assert len(perms) == 1
    only = perms[0]
    assert (only.form_id, only.field_key) == (_FORM_ID, "salary")
    assert only.visible is False
    assert only.editable is False
    assert provider.key == DEFAULT_FIELD_PERMISSION_PROVIDER_KEY


@pytest.mark.kiwi_id(2269)
async def test_static_provider_form_filter_and_empty_roles(session: AsyncSession, ns: Namespace) -> None:
    """表单过滤与空角色短路：不匹配表单不收窄项，无角色直接返回空。"""
    seeded = await _seed(session, ns)
    provider = StaticFieldPermissionProvider(session, session)
    roles: ConcurrentStableSet[int] = ConcurrentStableSet()
    roles.add(seeded.strict_role)
    other_form: ConcurrentStableSet[int] = ConcurrentStableSet()
    other_form.add(_OTHER_FORM_ID)
    assert list(await provider.resolve(role_ids=roles, form_ids=other_form)) == []
    assert list(await provider.resolve(role_ids=ConcurrentStableSet[int](), form_ids=other_form)) == []


@pytest.mark.kiwi_id(2269)
async def test_static_provider_skips_unresolvable_field_key(session: AsyncSession, ns: Namespace) -> None:
    """字段键缺失：收窄项指向未登记字段（`sys_field` 无此主键）时跳过，不进结果。"""
    seeded = await _seed(session, ns)
    session.add(
        SysRoleField(role_id=seeded.ghost_role, form_id=_FORM_ID, field_id=999999, visible=False, editable=False)
    )
    await session.commit()

    provider = StaticFieldPermissionProvider(session, session)
    roles: ConcurrentStableSet[int] = ConcurrentStableSet()
    roles.add(seeded.ghost_role)
    assert list(await provider.resolve(role_ids=roles, form_ids=ConcurrentStableSet[int]())) == []


@pytest.mark.kiwi_id(2269)
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


@pytest.mark.kiwi_id(2269)
async def test_build_field_provider_none_without_factory(session: AsyncSession) -> None:
    """未登记字段权限工厂 ⇒ 求值器为 None（字段全开，不构造 provider）。"""
    reset_field_permission_provider_factories()
    try:
        provider = _build_field_provider(session, session)
        assert provider is None
    finally:
        reset_field_permission_provider_factories()


@pytest.mark.kiwi_id(2329)
async def test_static_provider_empty_rows_after_roles(session: AsyncSession, ns: Namespace) -> None:
    """角色有值但无字段收窄行：直接返回空列表（不查字段键）。"""
    seeded = await _seed(session, ns)
    provider = StaticFieldPermissionProvider(session, session)
    roles: ConcurrentStableSet[int] = ConcurrentStableSet()
    roles.add(seeded.empty_role)
    assert list(await provider.resolve(role_ids=roles, form_ids=ConcurrentStableSet[int]())) == []


@pytest.mark.kiwi_id(2269)
def test_snapshot_field_state_defaults_and_exempt() -> None:
    """快照字段态：未收窄返回 None（默认全开）；豁免层级不参与收窄。"""
    perms: ConcurrentStableList[FieldPermission] = ConcurrentStableList()
    perms.add(FieldPermission(form_id=_FORM_ID, field_key="salary", visible=False, editable=True))
    snapshot = PermissionSnapshot(tier=TIER_STANDARD, field_perms=perms)
    assert snapshot.field_state(_FORM_ID, "salary") == (False, True)
    assert snapshot.field_state(_FORM_ID, "name") is None
    assert snapshot.exempt is False
    assert PermissionSnapshot(tier=TIER_SYSTEM_ADMIN).exempt is True
