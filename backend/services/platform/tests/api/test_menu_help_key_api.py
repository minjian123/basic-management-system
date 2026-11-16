"""元数据 `help_key` 写读 / 唯一性 / 清空 / 审计 / 鉴权回归（08_01；Kiwi 2520）。

覆盖：五类元数据接口的锚点往返与清空、`40211`（格式 / 形状 / 跨表重复）、
锚点变更显式落字段级审计（同值不记）、锚点不影响动态菜单权限与可见性。
"""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.testing.namespace import Namespace
from tests_support.menu_metadata import outbox_payloads
from tests_support.permission_admin import setup_min_tenant

_MENUS = "/api/v1/menus"
_FORMS = "/api/v1/forms"
_BUTTONS = "/api/v1/buttons"
_FIELDS = "/api/v1/fields"
_ACTIONS = "/api/v1/actions"
_BUSINESSES = "/api/v1/businesses"
_PERMISSIONS = "/api/v1/permissions"


@pytest_asyncio.fixture(autouse=True)
async def permission_engine(tenant_db: str) -> None:
    """真实权限校验所需的租户库（共享租户库）+ 内置系统管理员主体。

    Args:
        tenant_db: 共享租户库连接串。
    """
    await setup_min_tenant(tenant_db)


def _code(ns: Namespace, suffix: str) -> str:
    """本用例的业务 / 动作码（小写下划线，叠加下不与他人相撞）。

    Args:
        ns: 用例命名空间。
        suffix: 后缀。

    Returns:
        str: 业务 / 动作码。
    """
    return f"{ns.prefix}_{suffix}"


def _path(ns: Namespace, suffix: str) -> str:
    """本用例的菜单路径。

    Args:
        ns: 用例命名空间。
        suffix: 路径后缀。

    Returns:
        str: 菜单路径。
    """
    return f"/{ns.prefix}/{suffix}"


def _data(response: Any, label: str) -> Any:
    """取统一响应 `data`；失败时把完整响应体写进断言信息。

    Args:
        response: httpx 响应。
        label: 调用标识。

    Returns:
        Any: `data` 字段。
    """
    body = response.json()
    data = body.get("data")
    assert data is not None, f"{label} 失败（HTTP {response.status_code}）：{response.text}"
    return data


async def _create_menu(
    client: AsyncClient, path: str, *, help_key: str | None = None
) -> ConcurrentStableDict[str, Any]:
    """新增菜单（可选锚点）。

    Args:
        client: 测试客户端。
        path: 路由路径。
        help_key: 锚点值。

    Returns:
        ConcurrentStableDict[str, Any]: 菜单行。
    """
    payload: ConcurrentStableDict[str, Any] = ConcurrentStableDict(
        {
            "parent_id": 0,
            "path": path,
            "sort": 1,
            "hidden": False,
            "status": "enabled",
            "i18n": {"zh-CN": "锚点测试", "en-US": "Anchor test"},
        }
    )
    if help_key is not None:
        payload.set("help_key", help_key)
    return ConcurrentStableDict(_data(await client.post(_MENUS, json=dict(payload)), "新增菜单"))


async def _update_menu(client: AsyncClient, menu_id: int, path: str, *, help_key: str | None) -> Any:
    """更新菜单（整体替换，`help_key=None` 即清空）。

    Args:
        client: 测试客户端。
        menu_id: 菜单主键。
        path: 路由路径。
        help_key: 锚点值。

    Returns:
        Any: httpx 响应。
    """
    return await client.put(
        f"{_MENUS}/{menu_id}",
        json={
            "parent_id": 0,
            "path": path,
            "sort": 1,
            "hidden": False,
            "status": "enabled",
            "i18n": {"zh-CN": "锚点测试", "en-US": "Anchor test"},
            "help_key": help_key,
        },
    )


async def _audit_help_key_rows(model_id: int) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """取指定菜单行的 `help_key` 字段级审计载荷。

    Args:
        model_id: 菜单主键。

    Returns:
        ConcurrentStableList[ConcurrentStableDict[str, object]]: 事件载荷（插入序）。
    """
    rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    for payload in await outbox_payloads("sys.data.changed"):
        if (
            payload.get("table") == "sys_menu"
            and payload.get("field") == "help_key"
            and payload.get("model_id") == str(model_id)
        ):
            rows.add(payload)
    return rows


@pytest.mark.kiwi_id(2520)
async def test_menu_help_key_roundtrip_clear_and_invalid(client: AsyncClient, ns: Namespace) -> None:
    """菜单锚点：写入可读回、传 null 清空、非法值返回 40211。"""
    path = _path(ns, "menu")
    key = f"platform:{ns.prefix}:::"
    created = await _create_menu(client, path, help_key=key)
    assert created["help_key"] == key

    listed = _data(await client.get(_MENUS), "菜单树")
    assert any(item["path"] == path and item["help_key"] == key for item in listed["items"])

    cleared = await _update_menu(client, int(created["id"]), path, help_key=None)
    assert _data(cleared, "清空锚点")["help_key"] is None

    invalid = await _update_menu(client, int(created["id"]), path, help_key="platform:platform")
    assert invalid.json()["code"] == 40211
    assert "段数" in invalid.json()["message"]


@pytest.mark.kiwi_id(2520)
async def test_action_help_key_roundtrip_and_invalid(client: AsyncClient, ns: Namespace) -> None:
    """动作码锚点：全局兜底形态写入可读回、形状非法返回 40211。"""
    code = _code(ns, "anchor")
    created = _data(
        await client.post(
            _ACTIONS,
            json={
                "code": code,
                "status": "enabled",
                "i18n": {"zh-CN": "锚点动作"},
                "help_key": f"platform::::{code}",
            },
        ),
        "新增动作码",
    )
    assert created["help_key"] == f"platform::::{code}"

    listed = _data(await client.get(_ACTIONS), "动作码清单")
    assert any(item["code"] == code and item["help_key"] == f"platform::::{code}" for item in listed["items"])

    invalid = await client.put(
        f"{_ACTIONS}/{int(created['id'])}",
        json={"status": "enabled", "i18n": {"zh-CN": "锚点动作"}, "help_key": "platform:platform:::"},
    )
    assert invalid.json()["code"] == 40211


@pytest.mark.kiwi_id(2520)
async def test_form_field_button_help_keys_and_cross_table_conflict(client: AsyncClient, ns: Namespace) -> None:
    """表单 / 字段 / 按钮锚点往返；与菜单同键时返回 40211（跨表全局唯一）。"""
    menu_path = _path(ns, "owner")
    module = ns.prefix
    menu = await _create_menu(client, menu_path, help_key=f"platform:{module}:::")
    business_code = _code(ns, "biz")
    business = _data(
        await client.post(_BUSINESSES, json={"code": business_code, "i18n": {"zh-CN": "锚点业务"}}),
        "新增业务码",
    )
    form_key = f"platform:{module}:{business_code}::"
    form = _data(
        await client.post(
            _FORMS,
            json={
                "menu_ids": [menu["id"]],
                "business_id": business["id"],
                "status": "enabled",
                "help_key": form_key,
            },
        ),
        "新增表单",
    )
    assert form["help_key"] == form_key

    field = _data(
        await client.post(
            _FIELDS,
            json={
                "form_id": form["id"],
                "field_key": "username",
                "type": "input",
                "sort": 1,
                "status": "enabled",
                "i18n": {"zh-CN": "用户名"},
                "help_key": f"platform:{module}:{business_code}:username:",
            },
        ),
        "新增字段",
    )
    assert field["help_key"] == f"platform:{module}:{business_code}:username:"

    action = _data(
        await client.post(
            _ACTIONS,
            json={"code": _code(ns, "create"), "status": "enabled", "i18n": {"zh-CN": "新建"}},
        ),
        "新增动作码",
    )
    permission = _data(
        await client.post(_PERMISSIONS, json={"business_id": business["id"], "action_id": action["id"]}),
        "新增权限码",
    )
    button = _data(
        await client.post(
            _BUTTONS,
            json={
                "form_id": form["id"],
                "permission_id": permission["id"],
                "name": "新建",
                "type": "toolbar",
                "sort": 1,
                "status": "enabled",
                "help_key": f"platform:{module}:{business_code}::create",
            },
        ),
        "新增按钮",
    )
    assert button["help_key"] == f"platform:{module}:{business_code}::create"

    conflict = await client.post(
        _MENUS,
        json={
            "parent_id": 0,
            "path": _path(ns, "conflict"),
            "sort": 2,
            "hidden": False,
            "status": "enabled",
            "i18n": {"zh-CN": "重复锚点"},
            "help_key": f"platform:{module}:::",
        },
    )
    assert conflict.json()["code"] == 40211
    assert "占用" in conflict.json()["message"]


@pytest.mark.kiwi_id(2520)
async def test_help_key_change_is_audited_and_same_value_skipped(client: AsyncClient, ns: Namespace) -> None:
    """锚点实际变更落字段级审计；同值更新不产生新记录。"""
    path = _path(ns, "audited")
    first_key = f"platform:{ns.prefix}_one:::"
    second_key = f"platform:{ns.prefix}_two:::"
    created = await _create_menu(client, path, help_key=first_key)
    menu_id = int(created["id"])

    changed = await _update_menu(client, menu_id, path, help_key=second_key)
    assert _data(changed, "变更锚点")["help_key"] == second_key
    rows = await _audit_help_key_rows(menu_id)
    assert len(rows) == 1
    assert rows[0]["old_value"] == first_key
    assert rows[0]["new_value"] == second_key

    same = await _update_menu(client, menu_id, path, help_key=second_key)
    assert _data(same, "同值更新")["help_key"] == second_key
    assert len(await _audit_help_key_rows(menu_id)) == 1


@pytest.mark.kiwi_id(2520)
async def test_help_key_does_not_affect_permission_results(client: AsyncClient, ns: Namespace) -> None:
    """设置 / 变更锚点前后，动态菜单的权限码集合与树结构完全一致。"""
    path = _path(ns, "perm")
    created = await _create_menu(client, path)
    before = _data(await client.get("/api/v1/menus/my"), "动态菜单（前）")
    await _update_menu(client, int(created["id"]), path, help_key=f"platform:{ns.prefix}_perm:::")
    response = await client.get("/api/v1/menus/my")
    after = _data(response, "动态菜单（后）")
    scoped = f"{ns.prefix}_"
    assert [item for item in after["permissions"] if item.startswith(scoped)] == [
        item for item in before["permissions"] if item.startswith(scoped)
    ]
    assert [node["path"] for node in after["menus"] if ns.prefix in node["path"]] == [
        node["path"] for node in before["menus"] if ns.prefix in node["path"]
    ]
    assert "help_key" not in response.text
