# kiwi_id: 2504
"""选项集只读接口（任务 09-03-1）：快照返回 / 指定 keys / 未登记即 404。"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.kiwi_id(2504)


async def test_option_sets_snapshot(client: AsyncClient) -> None:
    """GET /api/v1/option-sets：平台三条选项集，条目按 sort 升序。"""
    resp = await client.get(
        "/api/v1/option-sets",
        params={"keys": "bms.tenant.status,bms.datasource.kind"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    items = body["data"]["items"]
    assert [item["option_set_key"] for item in items] == ["bms.tenant.status", "bms.datasource.kind"]
    tenant_status = items[0]
    assert tenant_status["namespace"] == "bms"
    assert [item["value"] for item in tenant_status["items"]] == ["provisioning", "active", "suspended", "deleted"]
    assert tenant_status["items"][0]["label"] == "开通中"
    assert tenant_status["items"][0]["color"] == "warning"
    data_source_kind = items[1]
    assert [item["value"] for item in data_source_kind["items"]] == ["dict", "form", "quota"]


async def test_option_sets_all_and_key_normalization(client: AsyncClient) -> None:
    """空 keys = 全部已登记；逗号项去空白 / 去重 / 忽略空项。"""
    all_items = (await client.get("/api/v1/option-sets")).json()["data"]["items"]
    keys = [item["option_set_key"] for item in all_items]
    assert set(keys) == {"bms.tenant.status", "bms.tenant.module_status", "bms.datasource.kind"}

    normalized = (
        await client.get(
            "/api/v1/option-sets",
            params={"keys": " bms.tenant.status , bms.tenant.status ,, "},
        )
    ).json()["data"]["items"]
    assert [item["option_set_key"] for item in normalized] == ["bms.tenant.status"]


async def test_option_sets_missing_key(client: AsyncClient) -> None:
    """未登记的选项集标识：404 / 10002（不静默返回空集）。"""
    resp = await client.get("/api/v1/option-sets", params={"keys": "bms.absent"})
    assert resp.status_code == 404
    assert resp.json()["code"] == 10002
