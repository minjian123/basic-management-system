"""动态菜单端点测试（Kiwi 2242）：`GET /api/v1/menus/my`。

覆盖：菜单树按业务权限过滤、按钮按动作权限标记、字段按字段权限标记、hidden 菜单仍下发、
挂接链断裂 / 停用不可见、locale 文案与缺省回退、元数据版本号与写后缓存失效。
"""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient

from bms_core.permission.cache import current_permission_cache_store
from bms_core.permission.sources import PermissionMetadata
from bms_core.permission.version import permission_version_key
from bms_core.testing.namespace import Namespace
from tests_support.auth import TEST_TENANT_ID
from tests_support.menu_metadata import insert_form, seed_business, seed_permission, set_business_status
from tests_support.permission_admin import setup_min_tenant


@pytest_asyncio.fixture(autouse=True)
async def permission_engine(tenant_db: str) -> None:
    """真实权限校验所需的租户库（**共享租户库**）+ 内置系统管理员主体。

    Args:
        tenant_db: 共享租户库连接串（套件夹具已注入 `BMS_DATABASE__TENANTS__URL`）。
    """
    await setup_min_tenant(tenant_db)


def _path(ns: Namespace, suffix: str) -> str:
    """本用例的菜单路径（叠加下不与他人路径相撞）。

    Args:
        ns: 用例命名空间。
        suffix: 路径后缀。

    Returns:
        str: 菜单路径。
    """
    return f"/{ns.prefix}/{suffix}"


def _business(ns: Namespace, suffix: str) -> str:
    """本用例的业务码。

    Args:
        ns: 用例命名空间。
        suffix: 业务后缀。

    Returns:
        str: 业务码。
    """
    return ns.code(suffix).replace("-", "_")


def _data_or_fail(response: Any, label: str) -> Any:
    """取统一响应的 `data`；失败时把**完整响应体**写进断言信息。

    原写法 `response.json()["data"]["id"]` 在链路异常时只报
    `TypeError: 'NoneType' object is not subscriptable`，把真实的错误码 / 提示全部吞掉，
    排查时无法区分「权限拒绝」「库表缺失」「并发锁」等成因。此辅助把响应体带进失败信息。

    Args:
        response: httpx 响应。
        label: 调用标识（写入断言信息）。

    Returns:
        Any: 响应的 `data` 字段。

    Raises:
        AssertionError: `data` 为空时抛出，信息含状态码与响应体。
    """
    body = response.json()
    data = body.get("data")
    assert data is not None, f"{label} 失败（HTTP {response.status_code}）：{response.text}"
    return data


_MENUS = "/api/v1/menus"
_FORMS = "/api/v1/forms"
_BUTTONS = "/api/v1/buttons"
_FIELDS = "/api/v1/fields"
_MY = "/api/v1/menus/my"


def _find(nodes: Any, path: str) -> Any:
    """在菜单树中按路径查找节点（递归）。

    响应体为 JSON 解析后的内置容器（测试断言侧不做集合类规整，故签名用 `Any`）。

    Args:
        nodes: 菜单节点清单。
        path: 目标路径。

    Returns:
        命中节点（内置字典）；无则 None。
    """
    for node in nodes:
        if node["path"] == path:
            return node
        found = _find(node.get("children") or [], path)
        if found is not None:
            return found
    return None


async def _create_page(client: AsyncClient, path: str, name: str, en: str, business: str) -> Any:
    """建「菜单 + 表单（挂业务）」并返回菜单行。

    Args:
        client: 测试客户端。
        path: 菜单路径。
        name: 中文名。
        en: 英文名。
        business: 业务码。

    Returns:
        菜单行（内置字典，含 id）。
    """
    listed = await client.get("/api/v1/businesses")
    payload = _data_or_fail(listed, "GET /api/v1/businesses")
    business_id = next(item["id"] for item in payload["items"] if item["code"] == business)
    menu = await client.post(
        _MENUS,
        json={
            "parent_id": 0,
            "path": path,
            "component": path.strip("/"),
            "icon": "el:document",
            "sort": 1,
            "hidden": False,
            "status": "enabled",
            "i18n": {"zh-CN": name, "en-US": en},
        },
    )
    menu_id = int(_data_or_fail(menu, "POST /api/v1/menus")["id"])
    form = await client.post(_FORMS, json={"menu_ids": [menu_id], "business_id": int(business_id), "status": "enabled"})
    assert form.json()["code"] == 0, f"POST /api/v1/forms 失败：{form.text}"
    return _data_or_fail(menu, "POST /api/v1/menus")


@pytest.mark.kiwi_id(2242)
async def test_my_menu_filters_marks_and_locale(client: AsyncClient, ns: Namespace) -> None:
    """菜单树 + 表单 / 按钮 / 字段元数据 + 权限码集合；文案按 locale 本地化。"""
    business = _business(ns, "my")
    path = _path(ns, "my")
    business_id = await seed_business(business, "我的业务")
    permission_id = await seed_permission(business_id, "create", "新建")
    menu = await _create_page(client, path, "我的页面", "My page", business)
    menu_id = int(menu["id"])

    forms = (await client.get(_FORMS, params={"menu_id": menu_id})).json()["data"]["items"]
    form_id = int(forms[0]["id"])
    await client.post(
        _BUTTONS,
        json={"form_id": form_id, "permission_id": permission_id, "name": "新增", "type": "toolbar", "sort": 1},
    )
    await client.post(
        _FIELDS,
        json={
            "form_id": form_id,
            "field_key": "username",
            "type": "input",
            "sort": 1,
            "i18n": {"zh-CN": "用户名", "en-US": "Username"},
        },
    )

    response = await client.get(_MY, headers={"accept-language": "zh-CN"})
    assert response.json()["code"] == 0
    data = response.json()["data"]
    assert data["locale"] == "zh-CN"
    assert isinstance(data["version"], int)
    assert f"{business}:create" in data["permissions"]

    node = _find(data["menus"], path)
    assert node is not None
    assert node["name"] == "我的页面"
    assert len(node["forms"]) == 1
    assert node["forms"][0]["business_code"] == business
    assert int(node["forms"][0]["menu_id"]) == menu_id
    assert node["forms"][0]["buttons"][0]["permission_code"] == f"{business}:create"
    assert node["forms"][0]["buttons"][0]["visible"] is True
    assert node["forms"][0]["fields"][0]["name"] == "用户名"
    assert node["forms"][0]["fields"][0]["visible"] is True
    assert node["forms"][0]["fields"][0]["editable"] is True

    english = await client.get(_MY, headers={"accept-language": "en-US"})
    english_node = _find(english.json()["data"]["menus"], path)
    assert english_node is not None
    assert english_node["name"] == "My page"
    assert english_node["forms"][0]["fields"][0]["name"] == "Username"


@pytest.mark.kiwi_id(2242)
async def test_my_menu_hides_broken_disabled_keeps_hidden(client: AsyncClient, ns: Namespace) -> None:
    """挂接链断裂 / 停用不可见；hidden 菜单仍下发（路由可直达）；缺省回退主表文案。"""
    hidden_path = _path(ns, "hidden")
    business_id = await seed_business(_business(ns, "hide"), "隐藏业务")
    hidden_menu = await client.post(
        _MENUS,
        json={
            "parent_id": 0,
            "path": hidden_path,
            "component": None,
            "icon": None,
            "sort": 1,
            "hidden": True,
            "status": "enabled",
            "i18n": {"zh-CN": "隐藏页"},
        },
    )
    hidden_id = int(hidden_menu.json()["data"]["id"])
    await client.post(_FORMS, json={"menu_ids": [hidden_id], "business_id": business_id, "status": "enabled"})

    disabled_path = _path(ns, "disabled")
    disabled_business = await seed_business(_business(ns, "disabled"), "停用业务")
    await _create_page(client, disabled_path, "停用页", "Disabled page", _business(ns, "disabled"))
    await set_business_status(disabled_business, "disabled")

    # 挂接链断裂：表单指向不存在的业务码（直插绕过校验）
    broken_path = _path(ns, "broken")
    broken_menu = await client.post(
        _MENUS, json={"parent_id": 0, "path": broken_path, "status": "enabled", "i18n": {"zh-CN": "断裂页"}}
    )
    await insert_form(int(broken_menu.json()["data"]["id"]), 999999999)

    # 菜单自身停用
    off_path = _path(ns, "off")
    off_menu = await client.post(
        _MENUS, json={"parent_id": 0, "path": off_path, "status": "disabled", "i18n": {"zh-CN": "停用菜单"}}
    )
    assert off_menu.json()["code"] == 0

    data = (await client.get(_MY)).json()["data"]
    hidden_node = _find(data["menus"], hidden_path)
    assert hidden_node is not None
    assert hidden_node["name"] == "隐藏页"
    assert hidden_node["hidden"] is True
    assert _find(data["menus"], disabled_path) is None
    assert _find(data["menus"], broken_path) is None
    assert _find(data["menus"], off_path) is None


@pytest.mark.kiwi_id(2242)
async def test_my_menu_version_bump_invalidates_cache(client: AsyncClient, ns: Namespace) -> None:
    """元数据写操作后版本号递增，新增菜单即时可见（缓存按版本键失效）。"""
    await seed_business(_business(ns, "cache_a"), "缓存业务A")
    await seed_business(_business(ns, "cache_b"), "缓存业务B")
    path_a = _path(ns, "cache-a")
    path_b = _path(ns, "cache-b")
    await _create_page(client, path_a, "缓存页A", "Cache A", _business(ns, "cache_a"))

    first = (await client.get(_MY)).json()["data"]
    assert _find(first["menus"], path_a) is not None
    assert _find(first["menus"], path_b) is None

    await _create_page(client, path_b, "缓存页B", "Cache B", _business(ns, "cache_b"))

    second = (await client.get(_MY)).json()["data"]
    assert second["version"] > first["version"]
    assert _find(second["menus"], path_b) is not None


@pytest.mark.kiwi_id(2321)
async def test_metadata_write_also_invalidates_permission_snapshot(
    client: AsyncClient, service_app: Any, ns: Namespace
) -> None:
    """元数据写路径同步递增权限版本并清层1 元数据（`04_2`：码集 / 入口集与服务端权限同源失效）。"""
    await seed_business(_business(ns, "perm_a"), "权限同步业务A")
    await seed_business(_business(ns, "perm_b"), "权限同步业务B")
    await _create_page(client, _path(ns, "perm-a"), "权限同步页A", "Perm A", _business(ns, "perm_a"))

    cache = service_app.state.cache
    before = cache.get(permission_version_key(TEST_TENANT_ID))
    store = current_permission_cache_store()
    store.set_metadata(source="probe", locale="zh-CN", version=0, value=PermissionMetadata())
    assert store.stats()["metadata_items"] == 1

    await _create_page(client, _path(ns, "perm-b"), "权限同步页B", "Perm B", _business(ns, "perm_b"))

    after = cache.get(permission_version_key(TEST_TENANT_ID))
    assert isinstance(after, int)
    # 一次建页含「建菜单 + 建表单」两次写，故版本至少 +1（不锁死具体次数，避免与建页实现耦合）
    assert after >= (before if isinstance(before, int) else 0) + 1
    assert store.stats()["metadata_items"] == 0

    # 连续两次读（无写）走元数据缓存命中分支，版本稳定
    first = (await client.get(_MY)).json()["data"]
    second = (await client.get(_MY)).json()["data"]
    assert second["version"] == first["version"]
