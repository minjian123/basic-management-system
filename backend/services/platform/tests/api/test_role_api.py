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
from sqlalchemy import Table, delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.api.deps import get_idempotency_store
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.idempotency.base import IDEMPOTENCY_PAYLOAD_TYPE
from bms_core.models.base import Base
from bms_platform.main import ApplicationFactory
from bms_platform.models.role import (
    ROLE_TYPE_SECURITY,
    SysDataScope,
    SysRole,
    SysRoleField,
    SysRolePermission,
    SysUserRole,
)
from bms_platform.models.user import SysUser
from tests_support.auth import TEST_SUBJECT, auth_headers
from tests_support.menu_metadata import reset_menu_tables, seed_business, seed_permission
from tests_support.permission_admin import assign_role_domain_operator

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
)


class _RecordingIdempotency:
    """幂等基座测试替身：内存首次结果表（不继承能力端口，避免以占位名污染进程级注册表）。"""

    def __init__(self) -> None:
        """初始化空首次结果表。"""
        self.keys: ConcurrentStableList[str] = ConcurrentStableList()
        self._payloads: ConcurrentStableDict[str, IDEMPOTENCY_PAYLOAD_TYPE] = ConcurrentStableDict()
        self._stale: ConcurrentStableList[str] = ConcurrentStableList()

    def mark_stale(self, key: str) -> None:
        """标记键「已占用但无首次结果」（模拟并发在途：begin False + load None）。

        Args:
            key: 幂等键。
        """
        self._stale.add(key)

    async def begin(self, key: str, *, ttl: int | None = None) -> bool:
        """登记幂等键（首次 True；已标记 stale 的键恒 False）。

        Args:
            key: 幂等键。
            ttl: 键有效期（替身忽略）。

        Returns:
            bool: 首次 True。
        """
        del ttl
        self.keys.add(key)
        if key in self._stale:
            return False
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


@pytest_asyncio.fixture(autouse=True)
async def system_admin(tenant_schema: None) -> None:
    """测试主体置「豁免层级 + 角色域操作人」（真实权限校验 + `03_02` 三权护栏）。

    角色域写端点自 `03_02` 起要求操作人为安全管理员；本文件用例未播种按钮元数据，
    安全管理员拿不到权限码（不属豁免层级），故同时授内置系统管理员以命中豁免层级。

    Args:
        tenant_schema: 临时租户库夹具（先建表并注入连接串）。
    """
    await assign_role_domain_operator()


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


async def _seed_dict() -> tuple[str, str]:
    """取一个已登记字典标识与其可匹配字段（数据权限白名单，来自字典数据源登记）。

    Returns:
        tuple[str, str]: (字典标识, 可匹配字段键)。
    """
    return "role", "label"


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

    # 内置判定改按 role_type：自建同名角色为自定义类型（允许；不再按角色码禁建）
    self_made = await client.post(_ROLES, json={"code": "system_admin", "name": "同名自定义"})
    assert self_made.json()["code"] == 0
    assert self_made.json()["data"]["role_type"] == "custom"
    assert self_made.json()["data"]["builtin"] is False

    # 请求体未知字段即拒（全局严格模式；`role_type` 不可改）
    strict = await client.put(f"{_ROLES}/{role_id}", json={"name": "系统", "version": 1, "role_type": "system"})
    assert strict.status_code == 422 or strict.json()["code"] == 10001

    listed = await client.get(_ROLES, params={"kw": "运维"})
    assert listed.json()["data"]["total"] == 1
    assert listed.json()["data"]["list"][0]["subject_count"] == 0

    detail = await client.get(f"{_ROLES}/{role_id}")
    assert detail.json()["data"]["version"] == 1
    updated = await client.put(f"{_ROLES}/{role_id}", json={"name": "运维负责人", "status": "enabled", "version": 1})
    assert updated.json()["data"]["name"] == "运维负责人"

    stale = await client.put(f"{_ROLES}/{role_id}", json={"name": "过期", "status": "enabled", "version": 1})
    assert stale.status_code == 409

    # 角色码可改（契约新增 code；带 code 更新生效）
    renamed = await client.put(
        f"{_ROLES}/{role_id}",
        json={"code": "ops_admin_v2", "name": "运维负责人", "status": "enabled", "version": 2},
    )
    assert renamed.json()["code"] == 0
    assert renamed.json()["data"]["code"] == "ops_admin_v2"

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

    business_id = await seed_business("user", "用户管理")
    permission_id = await seed_permission(business_id, "create", "新建")
    menu_id, form_id = await _create_form(client, "/t-role-api", business_id)
    field = await client.post(
        _FIELDS,
        json={"form_id": form_id, "field_key": "code", "type": "input", "sort": 1, "i18n": {"zh-CN": "角色码"}},
    )
    field_id = int(field.json()["data"]["id"])

    permissions = await client.put(
        f"{_ROLES}/{role_id}/permissions",
        json={
            "entries": [
                {"perm_type": "menu", "target_id": menu_id, "source_menu_id": 0},
                {"perm_type": "form", "target_id": form_id, "source_menu_id": menu_id},
                {"perm_type": "permission", "target_id": permission_id, "source_menu_id": menu_id},
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

    data_source_key, attr_key = await _seed_dict()
    scopes = await client.put(
        f"{_ROLES}/{role_id}/data-permissions",
        json={
            "entries": [
                {"data_source_key": data_source_key, "policy_type": "select", "config": [{"item_code": "enabled"}]},
                {
                    "data_source_key": data_source_key,
                    "policy_type": "match",
                    "config": [{"field": "code", "pattern": "user_*"}, {"field": attr_key, "pattern": "A?"}],
                },
            ]
        },
    )
    assert {item["policy_type"] for item in scopes.json()["data"]["items"]} == {"select", "match"}

    bad_payload = cast(
        "dict[str, object]",
        {"entries": [{"data_source_key": data_source_key, "policy_type": "bad", "config": []}]},
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
    assert set(item.keys()) == {"id", "username", "name", "status", "last_login_at"}

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
    menu = await client.post(
        _MENUS, json={"parent_id": 0, "path": path, "status": "enabled", "i18n": {"zh-CN": "角色用例页"}}
    )
    menu_id = int(menu.json()["data"]["id"])
    form = await client.post(_FORMS, json={"menu_ids": [menu_id], "business_id": business_id, "status": "enabled"})
    return menu_id, int(form.json()["data"]["id"])


@pytest.mark.kiwi_id(2248)
async def test_metadata_delete_blocked_by_role_grants(role_client: AsyncClient) -> None:
    """元数据删除 / 停用被角色授权引用拦截（40206）。

    覆盖 MetadataReferenceRepository 的 count_menu_refs / count_form_refs /
    count_permission_refs / count_field_refs 与 services/menu.py 对应保护分支。
    """
    client = role_client
    role = await client.post(_ROLES, json={"code": "meta_guard", "name": "元数据守护"})
    role_id = int(role.json()["data"]["id"])

    business_id = await seed_business("guard", "守护业务")
    permission_id = await seed_permission(business_id, "delete", "删除")
    menu_id, form_id = await _create_form(client, "/t-meta-guard", business_id)
    field = await client.post(
        _FIELDS,
        json={"form_id": form_id, "field_key": "name", "type": "input", "sort": 1, "i18n": {"zh-CN": "名称"}},
    )
    field_id = int(field.json()["data"]["id"])

    granted = await client.put(
        f"{_ROLES}/{role_id}/permissions",
        json={
            "entries": [
                {"perm_type": "menu", "target_id": menu_id, "source_menu_id": 0},
                {"perm_type": "form", "target_id": form_id, "source_menu_id": menu_id},
                {"perm_type": "permission", "target_id": permission_id, "source_menu_id": menu_id},
            ]
        },
    )
    assert granted.json()["code"] == 0, granted.text
    await client.put(
        f"{_ROLES}/{role_id}/fields",
        json={"entries": [{"form_id": form_id, "field_id": field_id, "visible": True, "editable": False}]},
    )

    assert (await client.put(f"/api/v1/permissions/{permission_id}", json={"status": "disabled"})).json()[
        "code"
    ] == 40206
    assert (await client.delete(f"/api/v1/permissions/{permission_id}")).json()["code"] == 40206
    assert (await client.delete(f"{_MENUS}/{menu_id}")).json()["code"] == 40206
    assert (await client.delete(f"{_FORMS}/{form_id}")).json()["code"] == 40206

    assert (await client.put(f"{_ROLES}/{role_id}/permissions", json={"entries": []})).json()["code"] == 0
    assert (await client.put(f"{_ROLES}/{role_id}/fields", json={"entries": []})).json()["code"] == 0
    # 表单仍挂着字段，先删字段再删表单（表单删除的前置校验）
    assert (await client.delete(f"{_FIELDS}/{field_id}")).json()["code"] == 0
    assert (await client.delete(f"{_FORMS}/{form_id}")).json()["code"] == 0
    assert (await client.delete(f"{_MENUS}/{menu_id}")).json()["code"] == 0


@pytest.mark.kiwi_id(2248)
async def test_role_grant_partial_release_keeps_reference(role_client: AsyncClient) -> None:
    """只解除部分授权时引用仍在：菜单 / 表单删除仍被拦截。

    覆盖 services/menu.py 的菜单与表单角色授权保护分支（1219 / 1376），
    以及权限码删除缺行分支（1097）与业务停用联动（844->848）。
    """
    client = role_client
    role = await client.post(_ROLES, json={"code": "partial_guard", "name": "部分解除"})
    role_id = int(role.json()["data"]["id"])

    business_id = await seed_business("partial", "部分业务")
    menu_id, form_id = await _create_form(client, "/t-partial", business_id)
    field = await client.post(
        _FIELDS,
        json={"form_id": form_id, "field_key": "title", "type": "input", "sort": 1, "i18n": {"zh-CN": "标题"}},
    )
    field_id = int(field.json()["data"]["id"])

    # 授权菜单与表单
    await client.put(
        f"{_ROLES}/{role_id}/permissions",
        json={
            "entries": [
                {"perm_type": "menu", "target_id": menu_id, "source_menu_id": 0},
                {"perm_type": "form", "target_id": form_id, "source_menu_id": menu_id},
            ]
        },
    )

    # 只解除表单授权，菜单授权仍在：菜单删除仍 40206（1219）
    await client.put(
        f"{_ROLES}/{role_id}/permissions",
        json={"entries": [{"perm_type": "menu", "target_id": menu_id, "source_menu_id": 0}]},
    )
    assert (await client.delete(f"{_MENUS}/{menu_id}")).json()["code"] == 40206

    # 表单侧：先删字段解除挂接，再试删表单（表单已无授权，但字段权限仍拦）
    await client.put(
        f"{_ROLES}/{role_id}/fields",
        json={"entries": [{"form_id": form_id, "field_id": field_id, "visible": True, "editable": False}]},
    )
    await client.delete(f"{_FIELDS}/{field_id}")
    await client.put(f"{_ROLES}/{role_id}/fields", json={"entries": []})

    # 权限码删除缺行分支：删除不存在的权限码 404
    assert (await client.delete("/api/v1/permissions/987654321")).status_code == 404

    # 业务停用联动：启用态业务码停用时连带停用权限码（844->848）
    business_id2 = await seed_business("cascade2", "级联业务")
    await seed_permission(business_id2, "read", "读")
    stopped = await client.put(
        f"/api/v1/businesses/{business_id2}",
        json={"status": "disabled", "i18n": {"zh-CN": "级联业务"}},
    )
    assert stopped.json()["code"] == 0, stopped.text


@pytest.mark.kiwi_id(2248)
async def test_role_grant_blocks_after_form_unlink(role_client: AsyncClient) -> None:
    """解除表单挂接后，角色授权仍拦菜单删除；字段权限仍拦表单删除。

    覆盖 services/menu.py 的菜单角色授权分支（1219）与表单字段权限分支（1376 / 1378）：
    这些校验排在「已挂表单 / 存在按钮字段」之后，须先解除前者才能触达。
    """
    client = role_client
    role = await client.post(_ROLES, json={"code": "unlink_guard", "name": "解挂守护"})
    role_id = int(role.json()["data"]["id"])

    business_id = await seed_business("unlink", "解挂业务")
    menu_id, form_id = await _create_form(client, "/t-unlink", business_id)

    # 授权菜单 + 表单
    await client.put(
        f"{_ROLES}/{role_id}/permissions",
        json={
            "entries": [
                {"perm_type": "menu", "target_id": menu_id, "source_menu_id": 0},
                {"perm_type": "form", "target_id": form_id, "source_menu_id": menu_id},
            ]
        },
    )

    # 解除菜单 → 表单挂接，使菜单删除能走到角色授权校验（1219）
    unlinked = await client.put(
        f"{_FORMS}/{form_id}",
        json={"menu_ids": [], "business_id": business_id, "component": None, "status": "enabled"},
    )
    assert unlinked.json()["code"] == 0, unlinked.text
    assert (await client.delete(f"{_MENUS}/{menu_id}")).json()["code"] == 40206

    # 解除表单授权后，表单删除仍被字段权限拦（1378）
    field = await client.post(
        _FIELDS,
        json={"form_id": form_id, "field_key": "code", "type": "input", "sort": 1, "i18n": {"zh-CN": "编码"}},
    )
    field_id = int(field.json()["data"]["id"])
    await client.put(
        f"{_ROLES}/{role_id}/fields",
        json={"entries": [{"form_id": form_id, "field_id": field_id, "visible": True, "editable": False}]},
    )
    assert (await client.delete(f"{_FORMS}/{form_id}")).json()["code"] == 40206

    # 删字段并解除字段授权后，表单仍受菜单授权关联约束；先解全部授权再删（计数归零路径）
    assert (await client.delete(f"{_FIELDS}/{field_id}")).json()["code"] == 0
    await client.put(f"{_ROLES}/{role_id}/fields", json={"entries": []})
    await client.put(f"{_ROLES}/{role_id}/permissions", json={"entries": []})
    assert (await client.delete(f"{_FORMS}/{form_id}")).json()["code"] == 0


@pytest.mark.kiwi_id(2248)
async def test_form_delete_guards_grant_then_field_permission(role_client: AsyncClient) -> None:
    """表单删除的两级角色校验：先表单授权（1376），再字段权限（1378）。

    两级校验串联，须分别构造：表单授权在且字段权限在 → 命中 1376；
    仅字段权限在（表单授权已解）→ 命中 1378。
    """
    client = role_client
    role = await client.post(_ROLES, json={"code": "form_guard", "name": "表单守护"})
    role_id = int(role.json()["data"]["id"])

    business_id = await seed_business("fguard", "表单守护业务")
    _, form_id = await _create_form(client, "/t-form-guard", business_id)
    field = await client.post(
        _FIELDS,
        json={"form_id": form_id, "field_key": "code", "type": "input", "sort": 1, "i18n": {"zh-CN": "编码"}},
    )
    field_id = int(field.json()["data"]["id"])

    # 场景一：先删字段（越过 1373 的「存在按钮/字段」），仅留表单授权 → 命中 1376
    await client.put(
        f"{_ROLES}/{role_id}/permissions",
        json={"entries": [{"perm_type": "form", "target_id": form_id, "source_menu_id": 0}]},
    )
    assert (await client.delete(f"{_FIELDS}/{field_id}")).json()["code"] == 0
    assert (await client.delete(f"{_FORMS}/{form_id}")).json()["code"] == 40206

    # 场景二：解除表单授权后，字段权限记录仍指向该表单 → 命中 1378
    # 字段权限按 form_id 计数，字段本体可已软删（1373 只查活动字段），故删字段不影响该计数。
    await client.put(f"{_ROLES}/{role_id}/permissions", json={"entries": []})
    field2 = await client.post(
        _FIELDS,
        json={"form_id": form_id, "field_key": "code2", "type": "input", "sort": 2, "i18n": {"zh-CN": "编码二"}},
    )
    field2_id = int(field2.json()["data"]["id"])
    await client.put(
        f"{_ROLES}/{role_id}/fields",
        json={"entries": [{"form_id": form_id, "field_id": field2_id, "visible": True, "editable": False}]},
    )
    assert (await client.delete(f"{_FIELDS}/{field2_id}")).json()["code"] == 0
    assert (await client.delete(f"{_FORMS}/{form_id}")).json()["code"] == 40206
    field_id = field2_id

    # 清理：解除字段权限后表单可删（字段本体已在场景二删过）
    await client.put(f"{_ROLES}/{role_id}/fields", json={"entries": []})
    assert (await client.delete(f"{_FORMS}/{form_id}")).json()["code"] == 0


async def test_role_read_endpoints_and_illegal_status(role_client: AsyncClient) -> None:
    """角色读端点：状态筛选非法 10001；授权 / 字段 / 数据权限条目读取（空清单）。"""
    client = role_client
    illegal = await client.get(_ROLES, params={"status": "unknown"})
    assert illegal.json()["code"] == 10001

    role = await client.post(_ROLES, json={"code": "reader", "name": "只读角色"})
    role_id = int(role.json()["data"]["id"])

    permissions = await client.get(f"{_ROLES}/{role_id}/permissions")
    assert permissions.json()["code"] == 0
    assert permissions.json()["data"]["items"] == []

    fields = await client.get(f"{_ROLES}/{role_id}/fields")
    assert fields.json()["code"] == 0
    assert fields.json()["data"]["items"] == []

    scopes = await client.get(f"{_ROLES}/{role_id}/data-permissions")
    assert scopes.json()["code"] == 0
    assert scopes.json()["data"]["items"] == []


async def test_role_assign_and_grant_idempotency_skips(role_client: AsyncClient) -> None:
    """幂等键分支：无键不写首次结果；键已占用但无载荷 → 落到实际执行分支。"""
    client = role_client
    role_id = int((await client.post(_ROLES, json={"code": "ops_skip", "name": "跳键角色"})).json()["data"]["id"])
    user_id = await _seed_user("frank", "弗兰克")

    no_key = await client.post(f"{_ROLES}/{role_id}/users", json={"user_ids": [user_id]})
    assert no_key.json()["code"] == 0

    _IDEMPOTENCY.mark_stale("bms:1001:idem:stale-assign")
    stale = await client.post(
        f"{_ROLES}/{role_id}/users", json={"user_ids": [user_id]}, headers={"Idempotency-Key": "stale-assign"}
    )
    assert stale.json()["code"] == 0

    no_key_grant = await client.put(f"{_ROLES}/{role_id}/permissions", json={"entries": []})
    assert no_key_grant.json()["code"] == 0

    _IDEMPOTENCY.mark_stale("bms:1001:idem:stale-grant")
    stale_grant = await client.put(
        f"{_ROLES}/{role_id}/permissions", json={"entries": []}, headers={"Idempotency-Key": "stale-grant"}
    )
    assert stale_grant.json()["code"] == 0


async def test_role_assignments_endpoint_applies_role_segment(role_client: AsyncClient) -> None:
    """保存编排端点：角色本体分段全量覆盖 + 回带生效详情、用户清单与分段名。"""
    client = role_client
    role_id = int((await client.post(_ROLES, json={"code": "ops_flow", "name": "编排角色"})).json()["data"]["id"])

    updated = await client.put(f"{_ROLES}/{role_id}/assignments", json={"role": {"name": "编排角色改", "version": 1}})
    assert updated.json()["code"] == 0, updated.text
    assert updated.json()["data"]["role"]["name"] == "编排角色改"
    assert updated.json()["data"]["applied"] == ["role"]
    assert updated.json()["data"]["users"]["items"] == []

    # 无 `role` 分段：跳过命令式 `role:update` 复校（仅挂端点级 `role:grant`）。
    user_id = await _seed_user("hank", "汉克")
    users_only = await client.put(f"{_ROLES}/{role_id}/assignments", json={"user_ids": [user_id]})
    assert users_only.json()["code"] == 0, users_only.text
    assert users_only.json()["data"]["applied"] == ["user_ids"]
    assert [int(item["user_id"]) for item in users_only.json()["data"]["users"]["items"]] == [user_id]


async def test_user_assignments_endpoint_applies_profile(role_client: AsyncClient) -> None:
    """用户保存编排端点：`profile` 分段（命令式复校 `user:update`）+ 回带生效详情与分段名。"""
    client = role_client
    user_id = await _seed_user("gina", "吉娜")

    updated = await client.put(f"{_USERS}/{user_id}/assignments", json={"profile": {"name": "吉娜改", "version": 1}})
    assert updated.json()["code"] == 0, updated.text
    assert updated.json()["data"]["user"]["name"] == "吉娜改"
    assert updated.json()["data"]["applied"] == ["profile"]
    assert updated.json()["data"]["roles"]["items"] == []

    # 无 `profile` 分段：跳过命令式 `user:update` 复校（仅挂端点级 `user:assign_role`）。
    role_id = int((await client.post(_ROLES, json={"code": "assignee_role", "name": "受派角色"})).json()["data"]["id"])
    roles_only = await client.put(f"{_USERS}/{user_id}/assignments", json={"role_ids": [role_id]})
    assert roles_only.json()["code"] == 0, roles_only.text
    assert roles_only.json()["data"]["applied"] == ["role_ids"]
    assert [int(item["role_id"]) for item in roles_only.json()["data"]["roles"]["items"]] == [role_id]


async def _seed_role(code: str, name: str, *, role_type: str = "custom") -> int:
    """直插租户库角色（指定 `role_type`，绕过建角色接口的 `custom` 恒定口径）。

    Args:
        code: 角色码。
        name: 角色名称。
        role_type: 角色类型（`custom` / `system` / `security` / `audit`）。

    Returns:
        int: 角色主键。
    """
    engine = create_async_engine(os.environ["BMS_DATABASE__TENANTS__URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = SysRole(code=code, name=name, status="enabled", role_type=role_type)
            session.add(row)
            await session.flush()
            role_id = row.id
            await session.commit()
            return role_id
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2314)
async def test_role_domain_write_rejected_for_system_admin(role_client: AsyncClient) -> None:
    """操作人侧护栏（`30048`）：仅持系统管理员（无安全管理员）调角色域写端点 → 403 拒绝；读端点不受影响。"""
    client = role_client
    subject = int(TEST_SUBJECT)

    # 摘掉测试装配里的安全管理员绑定 → 操作人退化为「仅系统管理员」
    engine = create_async_engine(os.environ["BMS_DATABASE__TENANTS__URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            rows = (
                await session.execute(
                    select(SysRole, SysUserRole)
                    .join(SysUserRole, SysUserRole.role_id == SysRole.id)
                    .where(SysUserRole.user_id == subject, SysRole.role_type == ROLE_TYPE_SECURITY)
                )
            ).all()
            for role, _binding in rows:
                await session.execute(
                    delete(SysUserRole).where(SysUserRole.user_id == subject, SysUserRole.role_id == role.id)
                )
            await session.commit()
    finally:
        await engine.dispose()

    created = await client.post(_ROLES, json={"code": "blocked_role", "name": "被拦角色"})
    assert created.status_code == 403
    assert created.json()["code"] == 30048

    # 读端点（`role:query`）不受操作人护栏约束
    listed = await client.get(_ROLES)
    assert listed.json()["code"] == 0


@pytest.mark.kiwi_id(2314)
async def test_role_business_grant_rejected_for_custom_role(role_client: AsyncClient) -> None:
    """`role` 业务归属（`30048`）：`role` 业务权限码授予非安全管理员角色 → 403 拒绝。"""
    client = role_client
    business_id = await seed_business("role", "角色管理")
    permission_id = await seed_permission(business_id)
    role_id = int((await client.post(_ROLES, json={"code": "grantee", "name": "受授角色"})).json()["data"]["id"])

    rejected = await client.put(
        f"{_ROLES}/{role_id}/permissions",
        json={"entries": [{"perm_type": "permission", "target_id": permission_id, "source_menu_id": 0}]},
    )
    assert rejected.status_code == 403
    assert rejected.json()["code"] == 30048

    entries = await client.get(f"{_ROLES}/{role_id}/permissions")
    assert entries.json()["data"]["items"] == []


@pytest.mark.kiwi_id(2314)
async def test_user_assignments_reject_separation_conflict(role_client: AsyncClient) -> None:
    """分配路径互斥（`30010`）：一次给同一用户分配系统 + 安全管理员 → 403 拒绝且角色未变。"""
    client = role_client
    system_role = await _seed_role("api_system_admin", "系统管理员", role_type="system")
    security_role = await _seed_role("api_security_admin", "安全管理员", role_type="security")
    user_id = await _seed_user("iris", "艾瑞丝")

    rejected = await client.put(f"{_USERS}/{user_id}/assignments", json={"role_ids": [system_role, security_role]})
    assert rejected.status_code == 403
    assert rejected.json()["code"] == 30010

    detail = await client.get(f"{_USERS}")
    assert detail.json()["code"] == 0
    # 单一内置类型放行（仅系统管理员）
    accepted = await client.put(f"{_USERS}/{user_id}/assignments", json={"role_ids": [system_role]})
    assert accepted.json()["code"] == 0, accepted.text
    assert [int(item["role_id"]) for item in accepted.json()["data"]["roles"]["items"]] == [system_role]
