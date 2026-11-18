"""布局三级解析：平台默认 / 角色模板 / 多角色优先级 / 个人覆盖与重置（Kiwi 2528）。"""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient

from bms_core.testing.namespace import Namespace
from tests_support.auth import auth_headers
from tests_support.dashboard import set_card_status

from .conftest import PLATFORM_PROBE_CARD
from .helpers import (
    DEFAULT_USER_ID,
    assign_role,
    card_code,
    clear_dashboard_pref,
    delete_role,
    prepare,
    read_pref,
    role_template_layout,
    seed_card,
    seed_role,
    seed_template,
    tenant_url,
)

pytestmark = pytest.mark.kiwi_id(2528)

_LAYOUT = "/api/v1/dashboard/layout"


def _data(response: Any) -> Any:
    """取统一响应 `data`（失败时带完整响应体）。

    Args:
        response: httpx 响应。

    Returns:
        Any: `data` 字段。
    """
    body = response.json()
    assert body.get("code") == 0, f"请求失败（HTTP {response.status_code}）：{response.text}"
    return body["data"]


@pytest_asyncio.fixture(autouse=True)
async def prepared(tenant_db: str) -> None:
    """准备集 + 个人布局清理（按主体精确清除，不清整表）。

    Args:
        tenant_db: 共享测试租户库连接串。
    """
    assert tenant_db
    await prepare()
    for user_id in (DEFAULT_USER_ID, 3001, 3002, 3003, 3004, 3201, 3202, 3301):
        await clear_dashboard_pref(tenant_url(), user_id)


async def test_platform_default_when_no_personal_or_role(client: AsyncClient) -> None:
    """无个人布局、无角色模板 → 平台默认模板（含会话探针卡）。"""
    data = _data(await client.get(_LAYOUT, headers=auth_headers("3001")))
    assert data["source"] == "platform"
    assert int(data["role_id"]) == 0
    assert int(data["template_id"]) > 0
    assert data["fallback"] is False
    codes = [item["code"] for item in data["available_cards"]]
    assert PLATFORM_PROBE_CARD in codes
    assert [item["code"] for item in data["layout"]["cards"]] == [PLATFORM_PROBE_CARD]


async def test_role_template_overrides_platform(client: AsyncClient, ns: Namespace) -> None:
    """绑定角色模板后该用户看到角色布局；角色无模板的用户仍走平台默认。"""
    role_code = f"{ns.prefix}_role_a"
    role_id = await seed_role(tenant_url(), role_code)
    card = card_code(ns, "rolecard")
    await seed_card(tenant_url(), card, name="角色卡", sort=20)
    try:
        await seed_template(
            tenant_url(),
            scope="role",
            role_id=role_id,
            name="角色布局",
            layout=role_template_layout(card, x=4),
        )
        await assign_role(tenant_url(), role_id, 3201)
        data = _data(await client.get(_LAYOUT, headers=auth_headers("3201")))
        assert data["source"] == "role"
        assert int(data["role_id"]) == role_id
        assert [item["code"] for item in data["layout"]["cards"]] == [card]

        other = _data(await client.get(_LAYOUT, headers=auth_headers("3002")))
        assert other["source"] == "platform"
    finally:
        await delete_role(tenant_url(), role_code)


async def test_role_priority_prefers_smaller_role_id(client: AsyncClient, ns: Namespace) -> None:
    """同类型多角色均有模板时按角色主键升序取首个（类型间优先级由基座纯函数用例覆盖）。"""
    first_code = f"{ns.prefix}_role_c"
    second_code = f"{ns.prefix}_role_d"
    first_role = await seed_role(tenant_url(), first_code)
    second_role = await seed_role(tenant_url(), second_code)
    first_card = card_code(ns, "priocard1")
    second_card = card_code(ns, "priocard2")
    await seed_card(tenant_url(), first_card, name="先建卡", sort=30)
    await seed_card(tenant_url(), second_card, name="后建卡", sort=40)
    try:
        await seed_template(
            tenant_url(),
            scope="role",
            role_id=second_role,
            name="后建角色布局",
            layout=role_template_layout(second_card),
        )
        await seed_template(
            tenant_url(),
            scope="role",
            role_id=first_role,
            name="先建角色布局",
            layout=role_template_layout(first_card, x=4),
        )
        await assign_role(tenant_url(), first_role, 3202)
        await assign_role(tenant_url(), second_role, 3202)
        data = _data(await client.get(_LAYOUT, headers=auth_headers("3202")))
        assert int(data["role_id"]) == min(first_role, second_role)
        expected = first_card if first_role < second_role else second_card
        assert [item["code"] for item in data["layout"]["cards"]] == [expected]
    finally:
        await delete_role(tenant_url(), first_code)
        await delete_role(tenant_url(), second_code)


async def test_personal_layout_overrides_and_reset(client: AsyncClient, ns: Namespace) -> None:
    """个人布局优先于角色 / 平台；重置后回退平台默认，且不影响其他用户。"""
    card = card_code(ns, "mycard")
    await seed_card(tenant_url(), card, name="我的卡", sort=50)
    saved = _data(await client.put(_LAYOUT, json={"layout": role_template_layout(card)}, headers=auth_headers("3003")))
    assert saved["applied"] is True
    stored = await read_pref(tenant_url(), 3003)
    assert stored is not None and card in stored

    mine = _data(await client.get(_LAYOUT, headers=auth_headers("3003")))
    assert mine["source"] == "personal"
    assert int(mine["template_id"]) == 0
    assert [item["code"] for item in mine["layout"]["cards"]] == [card]

    other = _data(await client.get(_LAYOUT, headers=auth_headers("3004")))
    assert other["source"] == "platform"

    reset = _data(await client.delete(_LAYOUT, headers=auth_headers("3003")))
    assert reset["applied"] is True
    assert await read_pref(tenant_url(), 3003) is None
    fallback = _data(await client.get(_LAYOUT, headers=auth_headers("3003")))
    assert fallback["source"] == "platform"

    again = _data(await client.delete(_LAYOUT, headers=auth_headers("3003")))
    assert again["applied"] is False


async def test_disabled_card_is_filtered_with_warning(client: AsyncClient, ns: Namespace) -> None:
    """个人布局引用已停用卡片：解析期剔除并给告警，其余卡片与整页不受影响。"""
    keeping = card_code(ns, "keepcard")
    dropped = card_code(ns, "offcard")
    await seed_card(tenant_url(), keeping, name="保留卡", sort=60)
    await seed_card(tenant_url(), dropped, name="停用卡", sort=70)
    layout: object = {
        "cards": [
            {"code": keeping, "x": 0, "y": 0, "w": 4, "h": 2, "visible": True},
            {"code": dropped, "x": 4, "y": 0, "w": 4, "h": 2, "visible": True},
        ]
    }
    await client.put(_LAYOUT, json={"layout": layout}, headers=auth_headers("3301"))
    await set_card_status(tenant_url(), dropped, "disabled")
    data = _data(await client.get(_LAYOUT, headers=auth_headers("3301")))
    assert data["source"] == "personal"
    assert [item["code"] for item in data["layout"]["cards"]] == [keeping]
    warning_codes = [(item["code"], item["reason"]) for item in data["warnings"]]
    assert (dropped, "card_disabled") in warning_codes
