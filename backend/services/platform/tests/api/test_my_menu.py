"""动态菜单端点测试（Kiwi 2242）：`GET /api/v1/menus/my`。

覆盖：菜单树按业务权限过滤、按钮按动作权限标记、字段按字段权限标记、hidden 菜单仍下发、
挂接链断裂 / 停用不可见、locale 文案与缺省回退、元数据版本号与写后缓存失效。
"""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests_support.menu_metadata import (
    insert_form,
    reset_menu_tables,
    seed_action,
    seed_business,
    set_business_status,
)


@pytest_asyncio.fixture(autouse=True)
async def clean_menu_tables(platform_db: None) -> None:
    """菜单元数据表逐用例清场（会话级平台库共享）。

    Args:
        platform_db: 平台库夹具（确保平台库连接串已注入）。
    """
    await reset_menu_tables()


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
    businesses = (await client.get("/api/v1/businesses")).json()["data"]["items"]
    business_id = next(item["id"] for item in businesses if item["code"] == business)
    menu = await client.post(
        _MENUS,
        json={
            "parent_id": 0,
            "name": name,
            "path": path,
            "component": path.strip("/"),
            "icon": "el:document",
            "sort": 1,
            "hidden": False,
            "status": "enabled",
            "i18n": {"en-US": en},
        },
    )
    menu_id = int(menu.json()["data"]["id"])
    form = await client.post(_FORMS, json={"menu_id": menu_id, "business_id": int(business_id), "status": "enabled"})
    assert form.json()["code"] == 0
    return menu.json()["data"]


@pytest.mark.kiwi_id(2242)
async def test_my_menu_filters_marks_and_locale(client: AsyncClient) -> None:
    """菜单树 + 表单 / 按钮 / 字段元数据 + 权限码集合；文案按 locale 本地化。"""
    business_id = await seed_business("t_my", "我的业务")
    action_id = await seed_action(business_id, "create", "新建")
    menu = await _create_page(client, "/t-my", "我的页面", "My page", "t_my")
    menu_id = int(menu["id"])

    forms = (await client.get(_FORMS, params={"menu_id": menu_id})).json()["data"]["items"]
    form_id = int(forms[0]["id"])
    await client.post(
        _BUTTONS, json={"form_id": form_id, "action_id": action_id, "name": "新增", "type": "toolbar", "sort": 1}
    )
    await client.post(
        _FIELDS,
        json={
            "form_id": form_id,
            "field_key": "username",
            "name": "用户名",
            "type": "input",
            "sort": 1,
            "i18n": {"en-US": "Username"},
        },
    )

    response = await client.get(_MY, headers={"accept-language": "zh-CN"})
    assert response.json()["code"] == 0
    data = response.json()["data"]
    assert data["locale"] == "zh-CN"
    assert isinstance(data["version"], int)
    assert "t_my" in data["permissions"]
    assert "t_my:create" in data["permissions"]

    node = _find(data["menus"], "/t-my")
    assert node is not None
    assert node["name"] == "我的页面"
    assert node["form"]["business_code"] == "t_my"
    assert node["form"]["buttons"][0]["action_code"] == "t_my:create"
    assert node["form"]["buttons"][0]["visible"] is True
    assert node["form"]["fields"][0]["name"] == "用户名"
    assert node["form"]["fields"][0]["visible"] is True
    assert node["form"]["fields"][0]["editable"] is True

    english = await client.get(_MY, headers={"accept-language": "en-US"})
    english_node = _find(english.json()["data"]["menus"], "/t-my")
    assert english_node is not None
    assert english_node["name"] == "My page"
    assert english_node["form"]["fields"][0]["name"] == "Username"


@pytest.mark.kiwi_id(2242)
async def test_my_menu_hides_broken_disabled_keeps_hidden(client: AsyncClient) -> None:
    """挂接链断裂 / 停用不可见；hidden 菜单仍下发（路由可直达）；缺省回退主表文案。"""
    business_id = await seed_business("t_hide", "隐藏业务")
    hidden_menu = await client.post(
        _MENUS,
        json={
            "parent_id": 0,
            "name": "隐藏页",
            "path": "/t-hidden",
            "component": None,
            "icon": None,
            "sort": 1,
            "hidden": True,
            "status": "enabled",
        },
    )
    hidden_id = int(hidden_menu.json()["data"]["id"])
    await client.post(_FORMS, json={"menu_id": hidden_id, "business_id": business_id, "status": "enabled"})

    disabled_business = await seed_business("t_disabled", "停用业务")
    await _create_page(client, "/t-disabled", "停用页", "Disabled page", "t_disabled")
    await set_business_status(disabled_business, "disabled")

    # 挂接链断裂：表单指向不存在的业务码（直插绕过校验）
    broken_menu = await client.post(
        _MENUS, json={"parent_id": 0, "name": "断裂页", "path": "/t-broken2", "status": "enabled"}
    )
    await insert_form(int(broken_menu.json()["data"]["id"]), 999999999)

    # 菜单自身停用
    off_menu = await client.post(
        _MENUS, json={"parent_id": 0, "name": "停用菜单", "path": "/t-off", "status": "disabled"}
    )
    assert off_menu.json()["code"] == 0

    data = (await client.get(_MY)).json()["data"]
    hidden_node = _find(data["menus"], "/t-hidden")
    assert hidden_node is not None
    assert hidden_node["name"] == "隐藏页"
    assert hidden_node["hidden"] is True
    assert _find(data["menus"], "/t-disabled") is None
    assert _find(data["menus"], "/t-broken2") is None
    assert _find(data["menus"], "/t-off") is None


@pytest.mark.kiwi_id(2242)
async def test_my_menu_version_bump_invalidates_cache(client: AsyncClient) -> None:
    """元数据写操作后版本号递增，新增菜单即时可见（缓存按版本键失效）。"""
    await seed_business("t_cache_a", "缓存业务A")
    await seed_business("t_cache_b", "缓存业务B")
    await _create_page(client, "/t-cache-a", "缓存页A", "Cache A", "t_cache_a")

    first = (await client.get(_MY)).json()["data"]
    assert _find(first["menus"], "/t-cache-a") is not None
    assert _find(first["menus"], "/t-cache-b") is None

    await _create_page(client, "/t-cache-b", "缓存页B", "Cache B", "t_cache_b")

    second = (await client.get(_MY)).json()["data"]
    assert second["version"] > first["version"]
    assert _find(second["menus"], "/t-cache-b") is not None
