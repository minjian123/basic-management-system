"""平台侧权限数据来源用例（`04_01`）：直查本库取数与装配。

覆盖下沉后平台侧的取数件：

- `PlatformPermissionDataSource.load_subject`：角色集合 → 类型 / 授权 / 数据范围规则 / 字段收窄；
- `load_metadata`：菜单元数据快照 → 菜单 → 表单索引、权限码 id → 权限码；
- 空角色短路（不查授权 / 范围 / 字段）；
- `build_platform_source`：按请求装配来源（含 `[permission].options` 读取）；
- `register_platform_permission`：真实校验器 + 数据来源工厂 + 字段权限工厂登记（幂等）。
"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.context import current_tenant_id, current_user_id
from bms_core.core.plugin import default_plugin_registry
from bms_core.db.registry import EngineRegistry
from bms_core.models.base import Base
from bms_core.permission.field import current_field_permission_provider_factory
from bms_core.permission.rbac import RbacPermissionChecker
from bms_core.permission.snapshot import set_current_permission_snapshot
from bms_core.servicecall.base import BaseServiceClient
from bms_platform.models.menu import SysField
from bms_platform.models.role import (
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
from bms_platform.permission.checker import (
    PLATFORM_DATA_SOURCE_KEY,
    build_platform_source,
    register_platform_permission,
)
from bms_platform.permission.field_provider import build_static_field_provider
from bms_platform.permission.source import (
    DEFAULT_METADATA_TTL,
    PlatformPermissionDataSource,
)
from bms_platform.repositories.role import UserRoleRepository
from bms_platform.services.permission_subject import DirectRoleResolver

_USER_ID = 1001
_MENU_ID = 900
_FORM_ID = 901
_ACTION_ID = 902
_ROLE_CODE = "reviewer"


class _Registry:
    """引擎注册表替身：按库键返回固定引擎（不真开库；`session_scope` 自行建会话）。"""

    def __init__(self, engine: AsyncEngine) -> None:
        """初始化。

        Args:
            engine: 用例内已建表的异步引擎（租户库与平台库同引擎，本用例数据同库）。
        """
        self._engine = engine

    def is_sync_only(self, db_key: str) -> bool:
        """非同步方言（走异步会话路径）。

        Args:
            db_key: 库键（忽略）。

        Returns:
            bool: False。
        """
        del db_key
        return False

    async def get(self, db_key: str, *, read_only: bool = False) -> object:
        """返回固定引擎。

        Args:
            db_key: 库键（忽略）。
            read_only: 只读标记（忽略）。

        Returns:
            object: 异步引擎。
        """
        del db_key, read_only
        return self._engine


class _MetadataService:
    """菜单元数据服务替身（返回固定快照）。"""

    async def load_snapshot(self, **kwargs: object) -> object:
        """返回快照替身。

        Args:
            kwargs: 调用参数（忽略）。

        Returns:
            object: 快照。
        """
        del kwargs
        return _snapshot()


class _Button:
    """按钮快照替身。"""

    def __init__(self, permission_id: int, permission_code: str) -> None:
        """初始化。

        Args:
            permission_id: 权限码 id。
            permission_code: 权限码。
        """
        self.permission_id = permission_id
        self.permission_code = permission_code


class _Form:
    """表单快照替身。"""

    def __init__(self, form_id: int, buttons: ConcurrentStableList[object]) -> None:
        """初始化。

        Args:
            form_id: 表单 id。
            buttons: 按钮列表。
        """
        self.id = form_id
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
    """菜单元数据快照替身。"""

    version: int = 7

    def __init__(self) -> None:
        """初始化（菜单 900 → 表单 901 + 按钮动作 902；菜单 899 无表单）。"""
        buttons: ConcurrentStableList[object] = ConcurrentStableList()
        buttons.add(_Button(_ACTION_ID, "employee:query"))
        forms: ConcurrentStableList[object] = ConcurrentStableList()
        forms.add(_Form(_FORM_ID, buttons))
        self.menus: ConcurrentStableList[object] = ConcurrentStableList()
        self.menus.add(_Menu(_MENU_ID, forms))
        self.menus.add(_Menu(899, ConcurrentStableList()))


def _snapshot() -> _Snapshot:
    """构造快照替身。

    Returns:
        _Snapshot: 快照。
    """
    return _Snapshot()


@pytest.fixture(autouse=True)
def clean_context() -> Iterator[None]:
    """每例前后清空快照与上下文。

    Yields:
        None: 用例运行期。
    """
    set_current_permission_snapshot(None)
    yield
    set_current_permission_snapshot(None)
    current_user_id.set(None)
    current_tenant_id.set(None)


@pytest_asyncio.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    """建最小租户库（角色域五表 + `sys_field`）并播种。

    Args:
        tmp_path: pytest 临时目录。

    Yields:
        AsyncEngine: 已建表并播种的异步引擎。
    """
    created = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'source.db'}")
    tables = [
        cast("Table", SysRole.__table__),
        cast("Table", SysUserRole.__table__),
        cast("Table", SysRolePermission.__table__),
        cast("Table", SysRoleField.__table__),
        cast("Table", SysDataScope.__table__),
        cast("Table", SysField.__table__),
    ]
    async with created.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables))
    factory = async_sessionmaker(created, expire_on_commit=False)
    async with factory() as opened:
        await _seed(opened)
    yield created
    await created.dispose()


async def _seed(session: AsyncSession) -> None:
    """播种：自定义角色 + 用户分配 + 三类授权 + 字段收窄 + 数据范围规则。

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
            SysRolePermission(role_id=role.id, perm_type=PERM_TYPE_FORM, target_id=999),
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


def _source(engine: AsyncEngine, *, with_field_provider: bool = True) -> PlatformPermissionDataSource:
    """构造平台侧数据来源（替身注册表 + 真实字段权限 provider）。

    Args:
        engine: 用例异步引擎。
        with_field_provider: 是否注入字段权限 provider 工厂。

    Returns:
        PlatformPermissionDataSource: 数据来源。
    """
    return PlatformPermissionDataSource(
        registry=cast("EngineRegistry", _Registry(engine)),
        cache=MemoryCacheRegion(),
        resolvers_factory=lambda tenant_session: (DirectRoleResolver(UserRoleRepository(tenant_session)),),
        field_provider_factory=build_static_field_provider if with_field_provider else None,
        ttl=DEFAULT_METADATA_TTL,
    )


@pytest.mark.kiwi_id(2320)
async def test_load_subject_maps_real_rows(engine: AsyncEngine) -> None:
    """取数：真实仓储行映射为基座数据契约（角色类型 / 三类授权 / 范围规则 / 字段收窄）。"""
    data = await _source(engine).load_subject(user_id=_USER_ID)
    assert len(data.role_ids) == 1
    role_id = next(iter(data.role_ids))
    assert data.role_types.get(role_id) == ROLE_TYPE_CUSTOM
    assert sorted((item.perm_type, item.target_id) for item in data.grants) == [
        ("form", 999),
        ("menu", _MENU_ID),
        ("permission", _ACTION_ID),
    ]
    assert len(data.data_scope_rules) == 1
    rule = data.data_scope_rules[0]
    assert rule.policy_type == POLICY_TYPE_SELECT
    assert list(rule.config) == [{"field": "area_code", "values": ["13"]}]
    assert len(data.field_perms) == 1
    assert data.field_perms[0].field_key == "salary"
    assert data.field_perms[0].visible is False


@pytest.mark.kiwi_id(2320)
async def test_load_subject_skips_field_provider_when_absent(engine: AsyncEngine) -> None:
    """取数：未注入字段权限工厂 → 字段收窄为空（全开）。"""
    data = await _source(engine, with_field_provider=False).load_subject(user_id=_USER_ID)
    assert len(data.role_ids) == 1
    assert list(data.field_perms) == []


@pytest.mark.kiwi_id(2320)
async def test_load_subject_short_circuits_without_roles(engine: AsyncEngine) -> None:
    """取数：无角色用户 → 空契约（不查授权 / 范围 / 字段）。"""
    data = await _source(engine).load_subject(user_id=999999)
    assert list(data.role_ids) == []
    assert list(data.grants) == []
    assert list(data.data_scope_rules) == []
    assert list(data.field_perms) == []


@pytest.mark.kiwi_id(2320)
async def test_load_subject_skips_unknown_perm_type(engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """取数：未登记授权类型的行跳过（不污染授权集合）。"""
    from bms_core.core.concurrent import ConcurrentStableList as StableList
    from bms_platform.permission import source as source_module

    monkeypatch.setattr(source_module, "_PERM_TYPES", (PERM_TYPE_MENU,))

    class _Row:
        """授权行替身（含未登记类型）。"""

        def __init__(self, perm_type: str, target_id: int) -> None:
            """初始化。

            Args:
                perm_type: 授权类型。
                target_id: 目标主键。
            """
            self.perm_type = perm_type
            self.target_id = target_id

    class _PermRepo:
        """角色授权仓储替身。"""

        def __init__(self, session: object) -> None:
            """初始化。

            Args:
                session: 会话（忽略）。
            """
            del session

        async def list_by_roles(self, role_ids: object) -> StableList[object]:
            """返回含未登记类型的行。

            Args:
                role_ids: 角色集合（忽略）。

            Returns:
                StableList[object]: 授权行。
            """
            del role_ids
            return StableList([_Row(PERM_TYPE_MENU, 900), _Row("ghost", 5)])

    monkeypatch.setattr(source_module, "RolePermissionRepository", _PermRepo)
    data = await _source(engine).load_subject(user_id=_USER_ID)
    assert [(item.perm_type, item.target_id) for item in data.grants] == [(PERM_TYPE_MENU, 900)]


@pytest.mark.kiwi_id(2320)
async def test_load_metadata_indexes_menu_forms_and_codes(engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """元数据：菜单 → 表单索引（无表单菜单不入索引）、权限码 id → 权限码、版本透传。"""
    from bms_platform.permission import source as source_module

    def _builder(session: object, cache: object) -> _MetadataService:
        """替身元数据服务构造器。

        Args:
            session: 平台库会话（忽略）。
            cache: 缓存域（忽略）。

        Returns:
            _MetadataService: 替身服务。
        """
        del session, cache
        return _MetadataService()

    monkeypatch.setattr(source_module, "build_menu_metadata_service", _builder)
    source = _source(engine)
    metadata = await source.load_metadata(locale="zh-CN")
    assert metadata.version == 7
    assert list(metadata.menu_forms.get(_MENU_ID) or []) == [_FORM_ID]
    assert metadata.menu_forms.get(899) is None
    assert metadata.permission_codes.get(_ACTION_ID) == "employee:query"


@pytest.mark.kiwi_id(2320)
async def test_build_platform_source_reads_options() -> None:
    """装配：按请求构造来源；`[permission].options` 的 TTL / 严格模式被读取。"""
    app = FastAPI()
    settings = Settings()
    options: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    options.set("snapshot_ttl_seconds", 60)
    options.set("require_org_roles", True)
    settings.permission.options = options
    app.state.settings = settings
    app.state.engine_registry = cast("EngineRegistry", object())
    app.state.cache = MemoryCacheRegion()
    app.state.service_client = cast("BaseServiceClient", object())
    request = Request(scope={"type": "http", "method": "GET", "path": "/x", "headers": [], "app": app})
    source = await build_platform_source(request)
    assert isinstance(source, PlatformPermissionDataSource)
    assert source._ttl == 60  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2320)
async def test_build_platform_source_falls_back_on_bad_option_types() -> None:
    """装配容错：`snapshot_ttl_seconds` 非整数 / 未配置 → 回落缺省 TTL；`require_org_roles` 缺省 False。"""
    app = FastAPI()
    settings = Settings()
    options: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    options.set("snapshot_ttl_seconds", "600")
    settings.permission.options = options
    app.state.settings = settings
    app.state.engine_registry = cast("EngineRegistry", object())
    app.state.cache = MemoryCacheRegion()
    app.state.service_client = cast("BaseServiceClient", object())
    request = Request(scope={"type": "http", "method": "GET", "path": "/x", "headers": [], "app": app})
    source = await build_platform_source(request)
    assert source._ttl == DEFAULT_METADATA_TTL  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2320)
async def test_build_platform_source_tolerates_non_mapping_options() -> None:
    """装配容错：`options` 非映射（异常装配）→ 全部回落缺省，不抛错。"""
    from types import SimpleNamespace

    app = FastAPI()
    app.state.settings = SimpleNamespace(permission=SimpleNamespace(options="bad-options", profile="smb"))
    app.state.engine_registry = cast("EngineRegistry", object())
    app.state.cache = MemoryCacheRegion()
    app.state.service_client = cast("BaseServiceClient", object())
    request = Request(scope={"type": "http", "method": "GET", "path": "/x", "headers": [], "app": app})
    source = await build_platform_source(request)
    assert source._ttl == DEFAULT_METADATA_TTL  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2320)
def test_stable_rows_tolerates_bad_shapes() -> None:
    """规则行规整：非序列（None / 字符串）→ 空；序列内非映射项跳过。"""
    from bms_platform.permission.source import _stable_rows  # pyright: ignore[reportPrivateUsage]

    assert list(_stable_rows(None)) == []
    assert list(_stable_rows("not-a-sequence")) == []
    rows = _stable_rows([{"field": "area_code"}, "bad", 5])
    assert [dict(item) for item in rows] == [{"field": "area_code"}]


@pytest.mark.kiwi_id(2320)
def test_register_platform_permission_wires_everything() -> None:
    """装配登记：真实校验器 + 数据来源工厂（按 key 命中）+ 字段权限工厂；重复调用幂等。"""
    settings = Settings()
    register_platform_permission(settings)
    register_platform_permission(settings)
    factories = _source_factories()
    assert factories.get(PLATFORM_DATA_SOURCE_KEY) is build_platform_source
    assert current_field_permission_provider_factory() is build_static_field_provider
    assert PLATFORM_DATA_SOURCE_KEY == "platform_permission_data_source"
    assert default_plugin_registry() is not None
    assert isinstance(RbacPermissionChecker(), RbacPermissionChecker)


def _source_factories() -> ConcurrentStableDict[str, object]:
    """取数据来源工厂注册表的拷贝（按 key 断言，不依赖登记顺序与其他套件残留）。

    Returns:
        ConcurrentStableDict[str, object]: 工厂注册表拷贝。
    """
    from bms_core.permission import sources as sources_module

    return ConcurrentStableDict(sources_module._FACTORIES)  # pyright: ignore[reportPrivateUsage]
