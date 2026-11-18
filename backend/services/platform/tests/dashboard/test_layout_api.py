"""个人布局保存：严格校验 / 非法引用 / 空布局 / 停用告警（Kiwi 2528）。"""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient

from bms_core.testing.namespace import Namespace
from tests_support.auth import auth_headers

from .helpers import (
    DEFAULT_USER_ID,
    card_code,
    clear_dashboard_pref,
    prepare,
    role_template_layout,
    seed_card,
    tenant_url,
)

pytestmark = pytest.mark.kiwi_id(2528)

_LAYOUT = "/api/v1/dashboard/layout"


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
    """准备集 + 个人布局清理。

    Args:
        tenant_db: 共享测试租户库连接串。
    """
    assert tenant_db
    await prepare()
    for user_id in (DEFAULT_USER_ID, 3103):
        await clear_dashboard_pref(tenant_url(), user_id)


async def test_save_rejects_invalid_structure(client: AsyncClient) -> None:
    """结构非法（尺寸越界 / 重叠 / 重复码）→ `40304` 并回传问题项。"""
    out_of_range = await client.put(
        _LAYOUT,
        json={"layout": {"cards": [{"code": "todo", "w": 1, "h": 9}]}},
        headers=auth_headers("3103"),
    )
    assert out_of_range.json()["code"] == 40304
    assert "width-out-of-range" in out_of_range.text

    overlap = await client.put(
        _LAYOUT,
        json={
            "layout": {
                "cards": [
                    {"code": "todo", "x": 0, "y": 0, "w": 6, "h": 2},
                    {"code": "notice", "x": 2, "y": 1, "w": 6, "h": 2},
                ]
            }
        },
        headers=auth_headers("3103"),
    )
    assert overlap.json()["code"] == 40304
    assert "overlap" in overlap.text

    duplicate = await client.put(
        _LAYOUT,
        json={"layout": {"cards": [{"code": "todo"}, {"code": "todo"}]}},
        headers=auth_headers("3103"),
    )
    assert duplicate.json()["code"] == 40304


async def test_save_rejects_unknown_card(client: AsyncClient, ns: Namespace) -> None:
    """引用未注册卡片 → `40301`。"""
    response = await client.put(
        _LAYOUT,
        json={"layout": role_template_layout(card_code(ns, "ghost"))},
        headers=auth_headers("3103"),
    )
    assert response.json()["code"] == 40301


async def test_save_warns_on_disabled_card(client: AsyncClient, ns: Namespace) -> None:
    """引用已停用卡片可保存，但响应带 `card_disabled` 告警。"""
    card = card_code(ns, "disabledcard")
    await seed_card(tenant_url(), card, name="停用卡", status="disabled")
    body = _body(await client.put(_LAYOUT, json={"layout": role_template_layout(card)}, headers=auth_headers("3103")))
    assert body["code"] == 0
    assert body["data"]["applied"] is True
    assert [(item["code"], item["reason"]) for item in body["data"]["warnings"]] == [(card, "card_disabled")]


async def test_empty_layout_is_allowed_and_falls_back(client: AsyncClient) -> None:
    """空布局允许保存（整页空态由前端给恢复默认），解析回退平台默认。"""
    saved = _body(await client.put(_LAYOUT, json={"layout": {"cards": []}}, headers=auth_headers("3103")))
    assert saved["code"] == 0
    assert saved["data"]["applied"] is True
    data = _body(await client.get(_LAYOUT, headers=auth_headers("3103")))["data"]
    assert data["source"] == "platform"
