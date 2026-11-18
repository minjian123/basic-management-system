"""模板维护：角色模板增删改 / 平台层级权限与唯一性（Kiwi 2528）。"""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient

from bms_core.testing.namespace import Namespace
from tests_support.auth import auth_headers

from .conftest import PLATFORM_PROBE_CARD
from .helpers import (
    DEFAULT_USER_ID,
    card_code,
    clear_dashboard_pref,
    delete_role,
    prepare,
    role_template_layout,
    seed_card,
    seed_role,
    tenant_url,
)

pytestmark = pytest.mark.kiwi_id(2528)

_TEMPLATES = "/api/v1/dashboard/templates"


def _body(response: Any) -> Any:
    """取响应体。

    Args:
        response: httpx 响应。

    Returns:
        Any: 响应 JSON。
    """
    return response.json()


@pytest_asyncio.fixture(autouse=True)
async def prepared(tenant_db: str) -> None:
    """准备集 + 偏好清理。

    Args:
        tenant_db: 共享测试租户库连接串。
    """
    assert tenant_db
    await prepare()
    await clear_dashboard_pref(tenant_url(), DEFAULT_USER_ID)


async def test_list_templates_includes_platform(client: AsyncClient) -> None:
    """列表：平台默认模板在前，含卡片数。"""
    data = _body(await client.get(_TEMPLATES))["data"]
    scopes = [item["scope"] for item in data["items"]]
    assert "platform" in scopes
    platform_row = next(item for item in data["items"] if item["scope"] == "platform")
    assert int(platform_row["role_id"]) == 0
    assert platform_row["card_count"] >= 1
    assert data["total"] == len(data["items"])


async def test_list_templates_filtered_by_scope(client: AsyncClient, ns: Namespace) -> None:
    """按层级筛选：仅返回该层级模板。"""
    role_code = f"{ns.prefix}_tpl_scope"
    role_id = await seed_role(tenant_url(), role_code)
    try:
        await client.post(
            _TEMPLATES,
            json={"scope": "role", "role_id": role_id, "name": "x", "layout_config": {"cards": []}},
        )
        filtered = _body(await client.get(_TEMPLATES, params={"scope": "role"}))["data"]
        assert filtered["items"]
        assert all(item["scope"] == "role" for item in filtered["items"])
    finally:
        await delete_role(tenant_url(), role_code)


async def test_create_update_delete_role_template(client: AsyncClient, ns: Namespace) -> None:
    """角色模板：新建 → 编辑（名称 / 状态 / 布局）→ 删除。"""
    role_code = f"{ns.prefix}_tpl_role"
    role_id = await seed_role(tenant_url(), role_code)
    card = card_code(ns, "tplcard")
    await seed_card(tenant_url(), card, name="模板卡", sort=120)
    try:
        created = _body(
            await client.post(
                _TEMPLATES,
                json={
                    "scope": "role",
                    "role_id": role_id,
                    "name": "角色布局",
                    "layout_config": role_template_layout(card),
                },
            )
        )
        assert created["code"] == 0
        template_id = int(created["data"]["id"])
        assert created["data"]["card_count"] == 1

        updated = _body(
            await client.put(
                f"{_TEMPLATES}/{template_id}",
                json={"name": "改名布局", "status": "disabled", "layout_config": {"cards": []}},
            )
        )
        assert updated["code"] == 0
        assert updated["data"]["name"] == "改名布局"
        assert updated["data"]["status"] == "disabled"
        assert updated["data"]["card_count"] == 0

        deleted = _body(await client.delete(f"{_TEMPLATES}/{template_id}"))
        assert deleted["code"] == 0
        assert deleted["data"]["applied"] is True
        assert (await client.delete(f"{_TEMPLATES}/{template_id}")).json()["code"] == 10002
    finally:
        await delete_role(tenant_url(), role_code)


async def test_create_role_template_validation(client: AsyncClient, ns: Namespace) -> None:
    """角色模板：层级 / 状态 / 布局非法 `10001` / `40304`；角色不存在 `40305`；重复 `40307`。"""
    bad_scope = _body(
        await client.post(_TEMPLATES, json={"scope": "tenant", "name": "x", "layout_config": {"cards": []}})
    )
    assert bad_scope["code"] == 10001

    bad_status = _body(
        await client.post(
            _TEMPLATES,
            json={"scope": "role", "role_id": 1, "name": "x", "layout_config": {"cards": []}, "status": "paused"},
        )
    )
    assert bad_status["code"] == 10001

    missing_role = _body(
        await client.post(
            _TEMPLATES,
            json={"scope": "role", "role_id": 999999, "name": "x", "layout_config": {"cards": []}},
        )
    )
    assert missing_role["code"] == 40305

    role_code = f"{ns.prefix}_tpl_dup"
    role_id = await seed_role(tenant_url(), role_code)
    try:
        bad_layout = _body(
            await client.post(
                _TEMPLATES,
                json={
                    "scope": "role",
                    "role_id": role_id,
                    "name": "x",
                    "layout_config": {"cards": [{"code": "todo", "w": 1, "h": 9}]},
                },
            )
        )
        assert bad_layout["code"] == 40304

        first = await client.post(
            _TEMPLATES,
            json={"scope": "role", "role_id": role_id, "name": "x", "layout_config": {"cards": []}},
        )
        assert first.json()["code"] == 0
        duplicated = _body(
            await client.post(
                _TEMPLATES,
                json={"scope": "role", "role_id": role_id, "name": "y", "layout_config": {"cards": []}},
            )
        )
        assert duplicated["code"] == 40307
    finally:
        await delete_role(tenant_url(), role_code)


async def test_platform_template_requires_admin_and_is_singleton(client: AsyncClient, ns: Namespace) -> None:
    """平台层级：非平台超管 `30001`；超管再建一份 `40306`。"""
    denied = _body(
        await client.post(
            _TEMPLATES,
            json={"scope": "platform", "name": "平台布局", "layout_config": role_template_layout(PLATFORM_PROBE_CARD)},
        )
    )
    assert denied["code"] == 30001

    admin_code = f"{ns.prefix}_admin"
    admin_role = await seed_role(tenant_url(), admin_code, role_type="platform_admin")
    from tests_support.dashboard import assign_role

    await assign_role(tenant_url(), admin_role, 990001)
    exists = _body(
        await client.post(
            _TEMPLATES,
            json={"scope": "platform", "name": "平台布局", "layout_config": role_template_layout(PLATFORM_PROBE_CARD)},
            headers=auth_headers("990001"),
        )
    )
    assert exists["code"] == 40306
    await delete_role(tenant_url(), admin_code)


async def test_update_template_validation(client: AsyncClient, ns: Namespace) -> None:
    """编辑：不存在 `10002`；状态非法 `10001`；布局非法 `40304`。"""
    assert (await client.put(f"{_TEMPLATES}/999999", json={"name": "x"})).json()["code"] == 10002

    role_code = f"{ns.prefix}_tpl_upd"
    role_id = await seed_role(tenant_url(), role_code)
    try:
        created = _body(
            await client.post(
                _TEMPLATES,
                json={"scope": "role", "role_id": role_id, "name": "x", "layout_config": {"cards": []}},
            )
        )
        template_id = int(created["data"]["id"])
        assert (await client.put(f"{_TEMPLATES}/{template_id}", json={"status": "paused"})).json()["code"] == 10001
        bad_layout = await client.put(
            f"{_TEMPLATES}/{template_id}", json={"layout_config": {"cards": [{"code": "todo", "w": 1, "h": 2}]}}
        )
        assert bad_layout.json()["code"] == 40304
    finally:
        await delete_role(tenant_url(), role_code)
