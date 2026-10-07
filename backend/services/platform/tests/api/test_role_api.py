"""角色管理端点测试（Kiwi 2248，02_03）：`/api/v1/roles` 与 `/api/v1/users`。

覆盖：角色 CRUD（列表含内置标记与主体数 / 详情 / 乐观锁 409 / 内置保护 30043 / 删除保护 30044）、
用户分配（批量分配 + 解绑 + 幂等键复用首次结果 + 用户无效 30045）、
授权全量覆盖（含来源校验 30046 + 幂等键）、字段权限（30049）、数据权限（策略结构校验）、
最小用户只读查询（关键字 / 状态筛选、最小字段集）。

角色 / 用户 / 字典表落**临时租户库**；菜单元数据（授权目标）落会话级平台库，两库分置与生产同构。
"""

import os
from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.api.deps import get_idempotency_store
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.dict.models import SysDictAttr, SysDictType
from bms_core.idempotency.base import IDEMPOTENCY_PAYLOAD_TYPE
from bms_core.models.base import Base
from bms_platform.main import ApplicationFactory
from bms_platform.models.role import SysDataScope, SysRole, SysRoleField, SysRolePermission, SysUserRole
from bms_platform.models.user import SysUser
from tests_support.auth import auth_headers
from tests_support.menu_metadata import reset_menu_tables, seed_action, seed_business

_ROLES = "/api/v1/roles"
_USERS = "/api/v1/users"
_MENUS = "/api/v1/menus"
_FORMS = "/api/v1/forms"
_FIELDS = "/api/v1/fields"

_TENANT_MODELS = (
    SysRole,
    SysUserRole,
    SysRolePermission,
    SysRoleField,
    SysDataScope,
    SysUser,
    SysDictType,
    SysDictAttr,
)


class _RecordingIdempotency:
    """幂等基座测试替身：内存首次结果表（不继承能力端口，避免以占位名污染进程级注册表）。"""

    def __init__(self) -> None:
        """初始化空首次结果表。"""
        self.keys: ConcurrentStableList[str] = ConcurrentStableList()
        self._payloads: ConcurrentStableDict[str, IDEMPOTENCY_PAYLOAD_TYPE] = ConcurrentStableDict()

    async def begin(self, key: str, *, ttl: int | None = None) -> bool:
        """登记幂等键（首次 True）。

        Args:
            key: 幂等键。
            ttl: 键有效期（替身忽略）。

        Returns:
            bool: 首次 True。
        """
        del ttl
        self.keys.add(key)
        return key not in self._payloads

    async def load(self, key: str) -> IDEMPOTENCY_PAYLOAD_TYPE | None:
        """取首次结果载荷。

        Args:
            key: 幂等键。

        Returns:
            IDEMPOTENCY_PAYLOAD_TYPE | None: 首次结果；未缓存为 None。
        """
        return self._payloads.get(key)

    async def save(self, key: str, payload: IDEMPOTENCY_PAYLOAD_TYPE, *, ttl: int | None = None) -> None:
        """写首次结果。

        Args:
            key: 幂等键。
            payload: 首次结果载荷。
            ttl: 键有效期（替身忽略）。
        """
        del ttl
        self._payloads.set(key, payload)


_IDEMPOTENCY = _RecordingIdempotency()


@pytest_asyncio.fixture(autouse=True)
async def tenant_schema(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """建临时租户库（角色 / 用户 / 字典表）并指向服务租户库；清场平台库菜单元数据。

    Args:
        tmp_path_factory: 临时目录工厂。
        monkeypatch: 环境变量覆盖。
    """
    url = f"sqlite+aiosqlite:///{tmp_path_factory.mktemp('role_tenant') / 'tenant.db'}"
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", url)
    get_settings.cache_clear()
    engine = create_async_engine(url)
    tables = [cast("Table", model.__table__) for model in _TENANT_MODELS]
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables))
    await engine.dispose()
    await reset_menu_tables()
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def role_client() -> AsyncIterator[AsyncClient]:
    """角色域用例客户端：**本夹具内建应用**（确保在租户库环境注入之后才解析引擎）。

    注入内存幂等基座替身，使 `Idempotency-Key` 复用首次结果可断言。

    Yields:
        AsyncClient: 携带测试登录态的 ASGI 客户端。
    """
    app = ApplicationFactory().create(None)
    app.dependency_overrides[get_idempotency_store] = lambda: _IDEMPOTENCY
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        client.headers.update(auth_headers())
        yield client


async def _seed_user(username: str, name: str, *, status: str = "enabled") -> int:
    """直插租户库用户（绕过建号链路）。

    Args:
        username: 登录账号。
        name: 姓名。
        status: 状态。

    Returns:
        int: 用户主键。
    """
    engine = create_async_engine(os.environ["BMS_DATABASE__TENANTS__URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = SysUser(username=username, password_hash="x", name=name, status=status)
            session.add(row)
            await session.flush()
            user_id = row.id
            await session.commit()
        return user_id
    finally:
        await engine.dispose()


async def _seed_dict() -> tuple[int, str]:
    """直插租户库字典类型与已启用扩展属性。

    Returns:
        tuple[int, str]: (字典类型主键, 扩展属性键)。
    """
    engine = create_async_engine(os.environ["BMS_DATABASE__TENANTS__URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = SysDictType(type="area", name="区域", sort=1, status="enabled")
            session.add(row)
            await session.flush()
            session.add(
                SysDictAttr(type_id=row.id, attr_key="area_code", name="区域码", data_type="text", status="enabled")
            )
            await session.commit()
            return row.id, "area_code"
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2248)
async def test_role_crud_assign_and_grant_flow(role_client: AsyncClient) -> None:
    """角色 CRUD → 用户分配（含幂等键）→ 授权 / 字段 / 数据权限 → 删除保护。"""
    client = role_client
    role = await client.post(_ROLES, json={"code": "ops_admin", "name": "运维管理员"})
    assert role.json()["code"] == 0
    role_id = int(role.json()["data"]["id"])
    assert role.json()["data"]["builtin"] is False

    duplicated = await client.post(_ROLES, json={"code": "ops_admin", "name": "重复"})
    assert duplicated.json()["code"] == 30042

    builtin = await client.post(_ROLES, json={"code": "system_admin", "name": "系统管理员"})
    assert builtin.json()["code"] == 30043

    listed = await client.get(_ROLES, params={"kw": "运维"})
    assert listed.json()["data"]["total"] == 1
    assert listed.json()["data"]["list"][0]["subject_count"] == 0

    detail = await client.get(f"{_ROLES}/{role_id}")
    assert detail.json()["data"]["version"] == 1
    updated = await client.put(f"{_ROLES}/{role_id}", json={"name": "运维负责人", "status": "enabled", "version": 1})
    assert updated.json()["data"]["name"] == "运维负责人"

    stale = await client.put(f"{_ROLES}/{role_id}", json={"name": "过期", "status": "enabled", "version": 1})
    assert stale.status_code == 409

    user_a = await _seed_user("alice", "爱丽丝")
    user_b = await _seed_user("bob", "鲍勃")
    disabled = await _seed_user("carol", "卡罗", status="disabled")

    invalid = await client.post(f"{_ROLES}/{role_id}/users", json={"user_ids": [disabled]})
    assert invalid.json()["code"] == 30045

    assigned = await client.post(
        f"{_ROLES}/{role_id}/users",
        json={"user_ids": [user_a, user_b]},
        headers={"Idempotency-Key": "assign-1"},
    )
    assert assigned.json()["code"] == 0, assigned.text
    assert [int(item["user_id"]) for item in assigned.json()["data"]["items"]] == [user_a, user_b]

    replayed = await client.post(
        f"{_ROLES}/{role_id}/users",
        json={"user_ids": [user_b]},
        headers={"Idempotency-Key": "assign-1"},
    )
    assert [int(item["user_id"]) for item in replayed.json()["data"]["items"]] == [user_a, user_b]
    assert _IDEMPOTENCY.keys == ["bms:1001:idem:assign-1", "bms:1001:idem:assign-1"]

    assigned_users = await client.get(f"{_ROLES}/{role_id}/users", params={"kw": "ali"})
    assert assigned_users.json()["data"]["total"] == 1
    assert assigned_users.json()["data"]["list"][0]["username"] == "alice"

    assert (await client.delete(f"{_ROLES}/{role_id}/users/{user_a}")).json()["code"] == 0
    assert (await client.delete(f"{_ROLES}/{role_id}")).json()["code"] == 30044

    business_id = await seed_business("role", "角色管理")
    action_id = await seed_action(business_id, "create", "新建")
    menu_id, form_id = await _create_form(client, "/t-role-api", business_id)
    field = await client.post(
        _FIELDS,
        json={"form_id": form_id, "field_key": "code", "name": "角色码", "type": "input", "sort": 1},
    )
    field_id = int(field.json()["data"]["id"])

    permissions = await client.put(
        f"{_ROLES}/{role_id}/permissions",
        json={
            "entries": [
                {"perm_type": "menu", "target_id": menu_id, "source_menu_id": 0},
                {"perm_type": "form", "target_id": form_id, "source_menu_id": menu_id},
                {"perm_type": "action", "target_id": action_id, "source_menu_id": menu_id},
            ]
        },
        headers={"Idempotency-Key": "grant-1"},
    )
    assert len(permissions.json()["data"]["items"]) == 3

    replayed_grant = await client.put(
        f"{_ROLES}/{role_id}/permissions",
        json={"entries": [{"perm_type": "menu", "target_id": menu_id, "source_menu_id": 0}]},
        headers={"Idempotency-Key": "grant-1"},
    )
    assert len(replayed_grant.json()["data"]["items"]) == 3

    bad_source = await client.put(
        f"{_ROLES}/{role_id}/permissions",
        json={"entries": [{"perm_type": "form", "target_id": form_id, "source_menu_id": menu_id}]},
    )
    assert bad_source.json()["code"] == 30046

    fields = await client.put(
        f"{_ROLES}/{role_id}/fields",
        json={"entries": [{"form_id": form_id, "field_id": field_id, "visible": True, "editable": False}]},
    )
    assert fields.json()["data"]["items"][0]["editable"] is False

    mismatch = await client.put(
        f"{_ROLES}/{role_id}/fields",
        json={"entries": [{"form_id": form_id, "field_id": 999999999, "visible": True, "editable": True}]},
    )
    assert mismatch.json()["code"] == 30049

    dict_type_id, attr_key = await _seed_dict()
    scopes = await client.put(
        f"{_ROLES}/{role_id}/data-permissions",
        json={
            "entries": [
                {"dict_type_id": dict_type_id, "policy_type": "select", "config": [{"item_code": "enabled"}]},
                {
                    "dict_type_id": dict_type_id,
                    "policy_type": "match",
                    "config": [{"field": "code", "pattern": "user_*"}, {"field": attr_key, "pattern": "A?"}],
                },
            ]
        },
    )
    assert {item["policy_type"] for item in scopes.json()["data"]["items"]} == {"select", "match"}

    bad_payload = cast(
        "dict[str, object]",
        {"entries": [{"dict_type_id": dict_type_id, "policy_type": "bad", "config": []}]},
    )
    bad_policy = await client.put(f"{_ROLES}/{role_id}/data-permissions", json=bad_payload)
    assert bad_policy.json()["code"] == 10001

    assert (await client.delete(f"{_ROLES}/{role_id}/users/{user_b}")).json()["code"] == 0
    assert (await client.delete(f"{_ROLES}/{role_id}")).json()["code"] == 0
    assert (await client.get(f"{_ROLES}/{role_id}")).json()["code"] == 30041


@pytest.mark.kiwi_id(2248)
async def test_minimal_user_query_filters_and_fields(role_client: AsyncClient) -> None:
    """最小用户只读查询：关键字 / 状态筛选 + 最小字段集（不含口令哈希与联系方式）。"""
    client = role_client
    await _seed_user("dave", "戴夫")
    await _seed_user("erin", "艾琳", status="disabled")

    all_users = await client.get(_USERS)
    assert all_users.json()["data"]["total"] == 2

    by_keyword = await client.get(_USERS, params={"kw": "dav"})
    assert by_keyword.json()["data"]["total"] == 1
    item: Any = by_keyword.json()["data"]["list"][0]
    assert set(item.keys()) == {"id", "username", "name", "status"}

    by_status = await client.get(_USERS, params={"status": "disabled"})
    assert by_status.json()["data"]["total"] == 1
    assert by_status.json()["data"]["list"][0]["username"] == "erin"

    illegal = await client.get(_USERS, params={"status": "unknown"})
    assert illegal.json()["code"] == 10001


async def _create_form(client: AsyncClient, path: str, business_id: int) -> tuple[int, int]:
    """经接口建菜单 + 挂接表单（业务码由用例直插平台库）。

    Args:
        client: 测试客户端。
        path: 菜单路径。
        business_id: 业务码主键。

    Returns:
        tuple[int, int]: (菜单 ID, 表单 ID)。
    """
    menu = await client.post(_MENUS, json={"parent_id": 0, "name": "角色用例页", "path": path, "status": "enabled"})
    menu_id = int(menu.json()["data"]["id"])
    form = await client.post(_FORMS, json={"menu_ids": [menu_id], "business_id": business_id, "status": "enabled"})
    return menu_id, int(form.json()["data"]["id"])
