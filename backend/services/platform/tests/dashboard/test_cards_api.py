"""卡片注册：数据集卡增删改 / 内置卡锁定 / 标识与类型校验（Kiwi 2528）。"""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient

from bms_core.testing.namespace import Namespace

from .helpers import DEFAULT_USER_ID, card_code, clear_dashboard_pref, prepare, seed_card, tenant_url

pytestmark = pytest.mark.kiwi_id(2528)

_CARDS = "/api/v1/dashboard/cards"


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
    """准备集（系统管理员持 `dashboard:query` / `dashboard:manage`）+ 偏好清理。

    Args:
        tenant_db: 共享测试租户库连接串。
    """
    assert tenant_db
    await prepare()
    await clear_dashboard_pref(tenant_url(), DEFAULT_USER_ID)


def _create_payload(code: str, **overrides: object) -> object:
    """构造新建数据集卡请求体。

    Args:
        code: 卡片标识。
        **overrides: 覆盖字段。

    Returns:
        object: 请求体（内置结构，供 httpx 直接序列化）。
    """
    payload: Any = {
        "code": code,
        "name": "数据集卡",
        "card_type": "dataset",
        "dataset_id": "ds-1",
        "chart_type": "bar",
        "default_width": 6,
        "default_height": 4,
        "sort": 100,
    }
    payload.update(overrides)
    return payload


async def test_list_cards_returns_builtin_catalog(client: AsyncClient, ns: Namespace) -> None:
    """列表含内置卡与数据集卡，支持按类型筛选。"""
    code = card_code(ns, "listcard")
    created = _body(await client.post(_CARDS, json=_create_payload(code)))
    assert created["code"] == 0
    listed = _body(await client.get(_CARDS))["data"]
    codes = [item["code"] for item in listed["items"]]
    assert code in codes
    assert "zz_platform_probe" in codes
    assert listed["total"] == len(listed["items"])

    dataset_only = _body(await client.get(_CARDS, params={"card_type": "dataset"}))["data"]
    dataset_codes = [item["code"] for item in dataset_only["items"]]
    assert code in dataset_codes
    assert all(item["card_type"] == "dataset" for item in dataset_only["items"])


async def test_create_dataset_card_with_i18n_and_config(client: AsyncClient, ns: Namespace) -> None:
    """新建数据集卡：多语言名派生、图表样式覆盖、默认尺寸与移动端标记保留。"""
    code = card_code(ns, "newcard")
    body = _body(
        await client.post(
            _CARDS,
            json=_create_payload(
                code,
                name="中文名",
                i18n={"zh-CN": "中文名", "en-US": "English name"},
                chart_config={"legend": {"show": False}},
                mobile_supported=False,
            ),
        )
    )
    assert body["code"] == 0
    row = body["data"]
    assert row["code"] == code
    assert row["card_type"] == "dataset"
    assert row["name"] == "中文名"
    assert row["i18n"] == {"zh-CN": "中文名", "en-US": "English name"}
    assert row["chart_config"] == {"legend": {"show": False}}
    assert row["mobile_supported"] is False

    listed = _body(await client.get(_CARDS))["data"]
    stored = next(item for item in listed["items"] if item["code"] == code)
    assert stored["i18n"] == {"zh-CN": "中文名", "en-US": "English name"}


async def test_create_rejects_builtin_and_invalid_payload(client: AsyncClient, ns: Namespace) -> None:
    """新建内置卡 `40308`；标识 / 类型 / 状态非法 `10001`；码重复 `40302`。"""
    builtin = _body(await client.post(_CARDS, json=_create_payload(card_code(ns, "b"), card_type="builtin")))
    assert builtin["code"] == 40308

    bad_code = _body(await client.post(_CARDS, json=_create_payload("Bad-Code")))
    assert bad_code["code"] == 10001

    bad_chart = _body(await client.post(_CARDS, json=_create_payload(card_code(ns, "c"), chart_type="radial")))
    assert bad_chart["code"] == 10001

    bad_status = _body(await client.post(_CARDS, json=_create_payload(card_code(ns, "d"), status="paused")))
    assert bad_status["code"] == 10001

    code = card_code(ns, "dup")
    assert (await client.post(_CARDS, json=_create_payload(code))).json()["code"] == 0
    duplicated = _body(await client.post(_CARDS, json=_create_payload(code)))
    assert duplicated["code"] == 40302


async def test_update_dataset_card_fields(client: AsyncClient, ns: Namespace) -> None:
    """数据集卡全字段可改（含多语言名整份覆盖与主表名派生）。"""
    code = card_code(ns, "updcard")
    created = _body(await client.post(_CARDS, json=_create_payload(code)))["data"]
    updated = _body(
        await client.put(
            f"{_CARDS}/{code}",
            json={
                "name": "改名",
                "dataset_id": "ds-2",
                "chart_type": "line",
                "chart_config": {"xAxis": {"show": True}},
                "default_width": 12,
                "default_height": 6,
                "mobile_supported": True,
                "sort": 200,
                "status": "disabled",
            },
        )
    )
    assert updated["code"] == 0
    row = updated["data"]
    assert row["name"] == "改名"
    assert row["dataset_id"] == "ds-2"
    assert row["chart_type"] == "line"
    assert row["default_width"] == 12
    assert row["status"] == "disabled"

    renamed = _body(await client.put(f"{_CARDS}/{code}", json={"i18n": {"en-US": "Renamed", "zh-CN": "重命名"}}))[
        "data"
    ]
    assert renamed["name"] == "重命名"
    assert int(renamed["id"]) == int(created["id"])


async def test_update_rejects_invalid_changes(client: AsyncClient, ns: Namespace) -> None:
    """不存在的卡片 `40301`；图表类型 / 状态非法 `10001`。"""
    missing = _body(await client.put(f"{_CARDS}/{card_code(ns, 'none')}", json={"name": "x"}))
    assert missing["code"] == 40301

    code = card_code(ns, "badupd")
    await client.post(_CARDS, json=_create_payload(code))
    assert (await client.put(f"{_CARDS}/{code}", json={"chart_type": "radial"})).json()["code"] == 10001
    assert (await client.put(f"{_CARDS}/{code}", json={"status": "paused"})).json()["code"] == 10001


async def test_builtin_card_only_status_is_editable(client: AsyncClient, ns: Namespace) -> None:
    """内置卡：改状态成功；改名称 / 默认尺寸 `40308`；删除 `40308`。"""
    code = card_code(ns, "builtincard")
    await seed_card(tenant_url(), code, card_type="builtin", name="内置卡", render_key="x")

    toggled = _body(await client.put(f"{_CARDS}/{code}", json={"status": "disabled"}))
    assert toggled["code"] == 0
    assert toggled["data"]["status"] == "disabled"

    blocked = _body(await client.put(f"{_CARDS}/{code}", json={"name": "改名"}))
    assert blocked["code"] == 40308
    assert (await client.put(f"{_CARDS}/{code}", json={"default_width": 6})).json()["code"] == 40308
    assert (await client.delete(f"{_CARDS}/{code}")).json()["code"] == 40308


async def test_delete_dataset_card(client: AsyncClient, ns: Namespace) -> None:
    """数据集卡软删除后不可再取；重复删除 `40301`。"""
    code = card_code(ns, "delcard")
    await client.post(_CARDS, json=_create_payload(code))
    deleted = _body(await client.delete(f"{_CARDS}/{code}"))
    assert deleted["code"] == 0
    assert deleted["data"]["applied"] is True
    assert (await client.delete(f"{_CARDS}/{code}")).json()["code"] == 40301
