"""引擎端到端用例（`04_01` 下沉后）：**非豁免主体**经真库角色域 → 基座引擎 → 判定与写拒绝。

与 `libs/bms_core/tests/permission/test_engine.py`（替身驱动判定口径）互补：本文件用**真实仓储**
（`sys_role` / `sys_user_role` / `sys_role_permission` / `sys_role_field` / `sys_data_scope`）跑通
「自定义角色 → 授权 → 聚合 → 快照」全链，断言**非豁免**主体的码级判定、字段收窄与数据范围规则，
并验证写时字段校验接缝 `assert_fields_writable`（豁免 / 未预加载放行，收窄字段即拒）。

数据来源以**本文件内的会话来源**实现（接缝可替换的直接演示）：取数与映射走真实仓储，算法走基座引擎
`bms_core.permission.engine`——与生产装配（`bms_platform.permission.source`）同一套口径。
"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.exceptions import PermissionError
from bms_core.models.base import Base
from bms_core.models.platform.menu import SysField
from bms_core.models.platform.role import (
    NO_SOURCE_MENU_ID,
    PERM_TYPE_FORM,
    PERM_TYPE_MENU,
    PERM_TYPE_PERMISSION,
    POLICY_TYPE_SELECT,
    ROLE_TYPE_CUSTOM,
    SysDataScope,
    SysRole,
    SysRoleField,
    SysRolePermission,
    SysUserRole,
)
from bms_core.permission.engine import PermissionEngine
from bms_core.permission.field import BaseFieldPermissionProvider
from bms_core.permission.snapshot import (
    TIER_STANDARD,
    TIER_SYSTEM_ADMIN,
    PermissionSnapshot,
    assert_fields_writable,
    set_current_permission_snapshot,
)
from bms_core.permission.sources import (
    BasePermissionDataSource,
    DataScopeRule,
    PermissionGrant,
    PermissionMetadata,
    PermissionSubjectData,
)
from bms_core.permission.subject import PermissionSubjectService
from bms_platform.permission.field_provider import StaticFieldPermissionProvider
from bms_platform.repositories.role import (
    DataScopeRepository,
    RolePermissionRepository,
    RoleRepository,
    UserRoleRepository,
)
from bms_platform.services.permission_subject import DirectRoleResolver

_USER_ID = 1001
_MENU_ID = 900
_FORM_ID = 901
_ACTION_ID = 902
_ROLE_CODE = "reviewer"
_FORM_BUSINESS = "employee"
_FORM_GRANT_ID = 999
_MENU_UNGRANTED_ID = 899


def _metadata() -> PermissionMetadata:
    """构造元数据索引（菜单 900 → 表单 901 + 按钮动作 902；未授予的菜单 899 → 表单 999）。

    Returns:
        PermissionMetadata: 元数据。
    """
    metadata = PermissionMetadata(version=3)
    form_ids: ConcurrentStableList[int] = ConcurrentStableList()
    form_ids.add(_FORM_ID)
    metadata.menu_forms.set(_MENU_ID, form_ids)
    ungranted: ConcurrentStableList[int] = ConcurrentStableList()
    ungranted.add(_FORM_GRANT_ID)
    metadata.menu_forms.set(_MENU_UNGRANTED_ID, ungranted)
    metadata.permission_codes.set(_ACTION_ID, "employee:query")
    return metadata


class _SessionSource(BasePermissionDataSource):
    """会话型数据来源（真实仓储 + 替身元数据）：演示接缝可替换。"""

    key: str = "session_permission_source"

    def __init__(self, session: AsyncSession) -> None:
        """初始化。

        Args:
            session: 租户库会话（用例内已播种）。
        """
        self._session = session

    async def load_subject(self, *, user_id: int) -> PermissionSubjectData:
        """按用户取聚合输入（真实仓储）。

        Args:
            user_id: 用户主键。

        Returns:
            PermissionSubjectData: 聚合输入。
        """
        role_ids = await PermissionSubjectService(
            ConcurrentStableList((DirectRoleResolver(UserRoleRepository(self._session)),))
        ).resolve_role_ids(user_id)
        data = PermissionSubjectData(role_ids=role_ids)
        if not role_ids:
            return data
        for role in await RoleRepository(self._session).list_by_ids(role_ids):
            data.role_types.set(role.id, role.role_type)
        for row in await RolePermissionRepository(self._session).list_by_roles(role_ids):
            data.grants.add(PermissionGrant(perm_type=row.perm_type, target_id=row.target_id))
        for scope_row in await DataScopeRepository(self._session).list_by_roles(role_ids):
            config: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
            for item in cast("list[dict[str, object]]", list(scope_row.config)):
                stable: ConcurrentStableDict[str, object] = ConcurrentStableDict()
                for key, value in item.items():
                    stable.set(key, value)
                config.add(stable)
            data.data_scope_rules.add(
                DataScopeRule(
                    data_source_key=scope_row.data_source_key,
                    policy_type=scope_row.policy_type,
                    config=config,
                )
            )
        provider = self._field_provider()
        data.field_perms = await provider.resolve(role_ids=role_ids, form_ids=ConcurrentStableSet[int]())
        return data

    async def load_metadata(self, *, locale: str = "zh-CN") -> PermissionMetadata:
        """返回替身元数据。

        Args:
            locale: 语言标识（忽略）。

        Returns:
            PermissionMetadata: 元数据。
        """
        del locale
        return _metadata()

    def _field_provider(self) -> BaseFieldPermissionProvider:
        """构造字段权限求值器（真实两库合流：本用例两库同会话）。

        Returns:
            BaseFieldPermissionProvider: 求值器。
        """
        return StaticFieldPermissionProvider(self._session, self._session)


@pytest.fixture(autouse=True)
def clean_context() -> Iterator[None]:
    """每例前后清空快照（请求态隔离）。

    Yields:
        None: 用例运行期。
    """
    set_current_permission_snapshot(None)
    yield
    set_current_permission_snapshot(None)


@pytest_asyncio.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    """建最小租户库（角色域五表 + `sys_field`）并播种非豁免主体的授权数据。

    Args:
        tmp_path: pytest 临时目录。

    Yields:
        AsyncSession: 会话。
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'engine.db'}")
    tables = [
        cast("Table", SysRole.__table__),
        cast("Table", SysUserRole.__table__),
        cast("Table", SysRolePermission.__table__),
        cast("Table", SysRoleField.__table__),
        cast("Table", SysDataScope.__table__),
        cast("Table", SysField.__table__),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as opened:
        await _seed(opened)
        yield opened
    await engine.dispose()


async def _seed(session: AsyncSession) -> None:
    """播种：自定义角色 + 用户分配 + 菜单/动作授权 + 字段收窄 + 数据范围规则。

    Args:
        session: 会话。
    """
    role = SysRole(code=_ROLE_CODE, name="复核员", status="enabled", role_type=ROLE_TYPE_CUSTOM)
    session.add(role)
    await session.flush()
    session.add(SysUserRole(role_id=role.id, user_id=_USER_ID))
    session.add_all(
        [
            SysRolePermission(role_id=role.id, perm_type=PERM_TYPE_MENU, target_id=_MENU_ID),
            SysRolePermission(role_id=role.id, perm_type=PERM_TYPE_FORM, target_id=_FORM_GRANT_ID),
            SysRolePermission(role_id=role.id, perm_type=PERM_TYPE_PERMISSION, target_id=_ACTION_ID),
        ]
    )
    field = SysField(form_id=_FORM_ID, field_key="salary", name="薪资", type="number", sort=1)
    session.add(field)
    await session.flush()
    session.add(
        SysRoleField(
            role_id=role.id,
            form_id=_FORM_ID,
            field_id=field.id,
            visible=False,
            editable=False,
            source_menu_id=NO_SOURCE_MENU_ID,
        )
    )
    config: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    row: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    row.set("field", "area_code")
    row.set("values", ["13"])
    config.add(row)
    session.add(
        SysDataScope(role_id=role.id, data_source_key="role", policy_type=POLICY_TYPE_SELECT, config=list(config))
    )
    await session.commit()


def _engine(session: AsyncSession, *, cache: MemoryCacheRegion | None = None) -> PermissionEngine:
    """构造基座引擎（会话型数据来源 + 真实字段权限 provider）。

    Args:
        session: 会话。
        cache: 缓存域（缺省新建内存实现）。

    Returns:
        PermissionEngine: 引擎实例。
    """
    return PermissionEngine(
        source=_SessionSource(session),
        cache=cache if cache is not None else MemoryCacheRegion(),
        profile="smb",
        exempt_role_types=ConcurrentStableList(("system",)),
    )


@pytest.mark.kiwi_id(2320)
async def test_non_exempt_subject_snapshot_and_write_guard(session: AsyncSession) -> None:
    """非豁免主体全链：菜单/表单 → 业务码、动作 → 动作码、字段收窄、数据范围规则与写拒绝。"""
    snapshot = await _engine(session).snapshot_for(user_id=_USER_ID, tenant_id="1001")
    assert snapshot.tier == TIER_STANDARD
    assert snapshot.exempt is False
    assert 900 in snapshot.granted_menu_ids  # 菜单授权计入入口集合
    assert {901, 999} <= snapshot.granted_form_ids  # 菜单连带表单 + 表单级直接授予
    assert snapshot.holds("employee:query") is True
    assert snapshot.holds("employee:export") is False
    assert snapshot.field_state(_FORM_ID, "salary") == (False, False)
    assert snapshot.field_state(_FORM_ID, "name") is None
    assert len(snapshot.data_scopes) == 1
    first = snapshot.data_scopes[0]
    assert first.get("policy_type") == POLICY_TYPE_SELECT
    set_current_permission_snapshot(snapshot)
    assert _write(form_id=_FORM_ID, name="张三") is None
    with pytest.raises(PermissionError):
        _write(form_id=_FORM_ID, salary=100)


@pytest.mark.kiwi_id(2320)
async def test_exempt_and_absent_snapshot_pass_write_guard(session: AsyncSession) -> None:
    """写拒绝接缝的放行分支：豁免层级与未预加载（占位实现 / 服务身份）不拦字段。"""
    engine = _engine(session)
    snapshot = await engine.snapshot_for(user_id=_USER_ID, tenant_id="1001")
    assert snapshot.field_state(_FORM_ID, "salary") == (False, False)
    set_current_permission_snapshot(PermissionSnapshot(tier=TIER_SYSTEM_ADMIN, field_perms=snapshot.field_perms))
    assert _write(form_id=_FORM_ID, salary=100) is None
    set_current_permission_snapshot(None)
    assert _write(form_id=_FORM_ID, salary=100) is None


@pytest.mark.kiwi_id(2320)
async def test_snapshot_cache_reuses_version_and_reflects_grant_removal(session: AsyncSession) -> None:
    """快照缓存：同版本二次取用复用；授权移除 + 版本失效后重算出结果。"""
    engine = _engine(session)
    first = await engine.snapshot_for(user_id=_USER_ID, tenant_id="1001")
    second = await engine.snapshot_for(user_id=_USER_ID, tenant_id="1001")
    assert first.holds("employee:query") == second.holds("employee:query") is True
    rows = (
        (await session.execute(select(SysRolePermission).where(SysRolePermission.perm_type == PERM_TYPE_PERMISSION)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    for row in rows:
        await session.delete(row)
    await session.commit()
    version = await engine.invalidate(tenant_id="1001")
    assert version == 1
    refreshed = await engine.snapshot_for(user_id=_USER_ID, tenant_id="1001")
    assert refreshed.holds("employee:query") is False


def _write(*, form_id: int, values: ConcurrentStableDict[str, object] | None = None, **kwargs: object) -> None:
    """调用字段写校验接缝。

    Args:
        form_id: 表单 id。
        values: 待写字段值（缺省由 kwargs 组装）。
        kwargs: 字段键值对。

    Returns:
        None: 无返回（违规时抛错）。
    """
    payload: ConcurrentStableDict[str, object] = values if values is not None else ConcurrentStableDict()
    for key, value in kwargs.items():
        payload.set(key, value)
    assert_fields_writable(form_id=form_id, values=payload)
