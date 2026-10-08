"""引擎端到端用例（`02_04`，Kiwi 2269）：**非豁免主体**经真库角色域 → 引擎计算 → 判定与写拒绝。

与 `test_engine.py`（替身驱动判定口径）互补：本文件用**真实仓储**（`sys_role` / `sys_user_role` /
`sys_role_permission` / `sys_role_data_scope` / `sys_role_field`）跑通「自定义角色 → 授权 → 聚合 →
快照」全链，断言**非豁免**主体的码级判定、字段收窄与数据范围规则，并验证写时字段校验接缝
`assert_fields_writable`（豁免 / 未预加载放行，收窄字段即拒）。菜单元数据以替身快照给入
（其存储正确性由菜单用例覆盖）。
"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import PermissionError
from bms_core.models.base import Base
from bms_core.permission.snapshot import (
    TIER_STANDARD,
    TIER_SYSTEM_ADMIN,
    PermissionSnapshot,
    assert_fields_writable,
    set_current_permission_snapshot,
)
from bms_platform.models.menu import SysField
from bms_platform.models.role import (
    NO_SOURCE_MENU_ID,
    PERM_TYPE_ACTION,
    PERM_TYPE_FORM,
    PERM_TYPE_MENU,
    POLICY_TYPE_SELECT,
    ROLE_TYPE_CUSTOM,
    SysDataScope,
    SysRole,
    SysRoleField,
    SysRolePermission,
    SysUserRole,
)
from bms_platform.permission.field_provider import StaticFieldPermissionProvider
from bms_platform.repositories.role import (
    DataScopeRepository,
    RolePermissionRepository,
    RoleRepository,
    UserRoleRepository,
)
from bms_platform.services.menu import MenuMetadataService
from bms_platform.services.permission import PermissionService
from bms_platform.services.permission_subject import DirectRoleResolver, PermissionSubjectService

_USER_ID = 1001
_MENU_ID = 900
_FORM_ID = 901
_ACTION_ID = 902
_ROLE_CODE = "reviewer"
_FORM_BUSINESS = "employee"
_FORM_GRANT_ID = 999
_MENU_UNGRANTED_ID = 899


class _Button:
    """按钮快照替身。"""

    def __init__(self, action_id: int, action_code: str) -> None:
        """初始化。

        Args:
            action_id: 动作 id。
            action_code: 动作码。
        """
        self.action_id = action_id
        self.action_code = action_code


class _Form:
    """表单快照替身。"""

    def __init__(self, form_id: int, business_code: str, buttons: ConcurrentStableList[object]) -> None:
        """初始化。

        Args:
            form_id: 表单 id。
            business_code: 业务码。
            buttons: 按钮列表。
        """
        self.id = form_id
        self.business_code = business_code
        self.buttons = buttons


class _Menu:
    """菜单快照替身。"""

    def __init__(self, menu_id: int, forms: ConcurrentStableList[object]) -> None:
        """初始化。

        Args:
            menu_id: 菜单 id。
            forms: 表单列表。
        """
        self.id = menu_id
        self.forms = forms


class _Snapshot:
    """菜单元数据快照替身（聚合所需最小面）。"""

    def __init__(self) -> None:
        """初始化（菜单 900 → 表单 901 + 按钮动作 902；未授予的菜单 899 → 表单 999）。"""
        buttons: ConcurrentStableList[object] = ConcurrentStableList()
        buttons.add(_Button(_ACTION_ID, "employee:query"))
        forms: ConcurrentStableList[object] = ConcurrentStableList()
        forms.add(_Form(_FORM_ID, _FORM_BUSINESS, buttons))
        standalone: ConcurrentStableList[object] = ConcurrentStableList()
        standalone.add(_Form(_FORM_GRANT_ID, "payroll", ConcurrentStableList[object]()))
        self.menus: ConcurrentStableList[object] = ConcurrentStableList()
        self.menus.add(_Menu(_MENU_ID, forms))
        self.menus.add(_Menu(_MENU_UNGRANTED_ID, standalone))


class _Metadata:
    """菜单元数据服务替身。"""

    async def load_snapshot(self, **kwargs: object) -> object:
        """返回替身快照。

        Args:
            kwargs: 调用参数（忽略）。

        Returns:
            object: 快照替身。
        """
        del kwargs
        return _Snapshot()


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
            SysRolePermission(role_id=role.id, perm_type=PERM_TYPE_ACTION, target_id=_ACTION_ID),
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
    session.add(SysDataScope(role_id=role.id, dict_type_id=1, policy_type=POLICY_TYPE_SELECT, config=list(config)))
    await session.commit()


def _service(session: AsyncSession) -> PermissionService:
    """构造真实仓储驱动的引擎（菜单元数据替身）。

    Args:
        session: 会话。

    Returns:
        PermissionService: 引擎实例。
    """
    return PermissionService(
        roles=RoleRepository(session),
        permissions=RolePermissionRepository(session),
        data_scopes=DataScopeRepository(session),
        metadata=cast("MenuMetadataService", _Metadata()),
        subject=PermissionSubjectService((DirectRoleResolver(UserRoleRepository(session)),)),
        cache=MemoryCacheRegion(),
        field_provider=StaticFieldPermissionProvider(session, session),
        profile="smb",
    )


@pytest.mark.kiwi_id(2269)
async def test_non_exempt_subject_snapshot_and_write_guard(session: AsyncSession) -> None:
    """非豁免主体全链：菜单/表单 → 业务码、动作 → 动作码、字段收窄、数据范围规则与写拒绝。"""
    snapshot = await _service(session).snapshot_for(user_id=_USER_ID, tenant_id="1001")
    assert snapshot.tier == TIER_STANDARD
    assert snapshot.exempt is False
    assert snapshot.holds("employee") is True  # 菜单授权连带其表单业务码
    assert snapshot.holds("payroll") is True  # 表单授权取业务码
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


@pytest.mark.kiwi_id(2269)
async def test_exempt_and_absent_snapshot_pass_write_guard(session: AsyncSession) -> None:
    """写拒绝接缝的放行分支：豁免层级与未预加载（占位实现 / 服务身份）不拦字段。"""
    service = _service(session)
    snapshot = await service.snapshot_for(user_id=_USER_ID, tenant_id="1001")
    assert snapshot.field_state(_FORM_ID, "salary") == (False, False)
    set_current_permission_snapshot(PermissionSnapshot(tier=TIER_SYSTEM_ADMIN, field_perms=snapshot.field_perms))
    assert _write(form_id=_FORM_ID, salary=100) is None
    set_current_permission_snapshot(None)
    assert _write(form_id=_FORM_ID, salary=100) is None


@pytest.mark.kiwi_id(2269)
async def test_snapshot_cache_reuses_version_and_reflects_grant_removal(session: AsyncSession) -> None:
    """快照缓存：同版本二次取用复用；授权移除 + 版本失效后重算出结果。"""
    service = _service(session)
    first = await service.snapshot_for(user_id=_USER_ID, tenant_id="1001")
    second = await service.snapshot_for(user_id=_USER_ID, tenant_id="1001")
    assert first.holds("employee:query") == second.holds("employee:query") is True
    rows = (
        (await session.execute(select(SysRolePermission).where(SysRolePermission.perm_type == PERM_TYPE_ACTION)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    for row in rows:
        await session.delete(row)
    await session.commit()
    version = await service.invalidate(tenant_id="1001")
    assert version == 1
    refreshed = await service.snapshot_for(user_id=_USER_ID, tenant_id="1001")
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
