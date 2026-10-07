"""产品档案只读接口测试（Kiwi 2250）：清单分页 / 筛选 / 明细 / 404 / 字段护栏 / 空库 / 路由只读。"""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from bms_core.application import service_lifespan as lifespan
from bms_core.core.concurrent import ConcurrentStableSet
from bms_core.core.config import get_settings
from bms_core.schemas.product import ProductResponse
from bms_platform.main import ApplicationFactory
from tests_support.auth import auth_headers

_EXPECTED_KEYS = ["biz", "cw", "mdm"]


@pytest.mark.kiwi_id(2250)
async def test_list_products_contract() -> None:
    """GET /api/v1/products 分页结构（3 行）；status 筛选；POST/PUT/DELETE 405。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers.update(auth_headers())
        resp = await client.get("/api/v1/products")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        data = body["data"]
        assert (data["total"], data["page"], data["size"]) == (3, 1, 20)
        assert [item["product_key"] for item in data["list"]] == _EXPECTED_KEYS
        assert data["list"][0]["frontend_package_source"] is None

        planned = await client.get("/api/v1/products", params={"status": "planned"})
        assert [item["product_key"] for item in planned.json()["data"]["list"]] == ["mdm"]

        enabled = await client.get("/api/v1/products", params={"status": "enabled"})
        assert enabled.json()["data"]["total"] == 2

        retired = await client.get("/api/v1/products", params={"status": "retired"})
        assert retired.json()["data"] == {"list": [], "total": 0, "page": 1, "size": 20}

        created = await client.post("/api/v1/products", json={"product_key": "ghost"})
        assert created.status_code == 405
        updated = await client.put("/api/v1/products", json={"product_key": "ghost"})
        assert updated.status_code == 405
        removed = await client.delete("/api/v1/products")
        assert removed.status_code == 405


@pytest.mark.kiwi_id(2250)
async def test_list_products_pagination_and_sort(client: AsyncClient) -> None:
    """分页生效（size / 末页）；排序白名单（命中排序、非法字段忽略回落 id 升序）；页码限深 10001。"""
    first = await client.get("/api/v1/products", params={"page": 1, "size": 2})
    assert [item["product_key"] for item in first.json()["data"]["list"]] == ["biz", "cw"]
    assert first.json()["data"]["total"] == 3

    last = await client.get("/api/v1/products", params={"page": 2, "size": 2})
    assert [item["product_key"] for item in last.json()["data"]["list"]] == ["mdm"]

    sorted_by_id = await client.get("/api/v1/products", params={"order_by": "id", "order": "desc"})
    assert sorted_by_id.json()["data"]["list"][0]["product_key"] == "mdm"

    ignored = await client.get("/api/v1/products", params={"order_by": "product_key"})
    assert ignored.json()["data"]["list"][0]["product_key"] == "biz"

    too_deep = await client.get("/api/v1/products", params={"page": 101})
    assert too_deep.status_code == 200
    assert too_deep.json()["code"] == 10001


@pytest.mark.kiwi_id(2250)
async def test_get_product_detail_and_not_found(client: AsyncClient) -> None:
    """明细：命中返回字段；未登记 404 + 10002 + 统一响应体。"""
    detail = await client.get("/api/v1/products/biz")
    assert detail.status_code == 200
    data = detail.json()["data"]
    assert data["product_key"] == "biz"
    assert data["name"] == "企业运营管理"
    assert data["status"] == "enabled"

    mdm = await client.get("/api/v1/products/mdm")
    assert mdm.json()["data"]["status"] == "planned"

    missing = await client.get("/api/v1/products/ghost")
    assert missing.status_code == 404
    body = missing.json()
    assert body["code"] == 10002
    assert body["data"] is None
    assert "产品未登记" in body["message"]


@pytest.mark.kiwi_id(2250)
async def test_products_response_fields_whitelist(client: AsyncClient) -> None:
    """响应字段集严格等于 `ProductResponse`（不含密钥 / 敏感项）。"""
    expected = set(ProductResponse.model_fields)
    listed = await client.get("/api/v1/products")
    assert set(listed.json()["data"]["list"][0]) == expected
    detail = await client.get("/api/v1/products/biz")
    assert set(detail.json()["data"]) == expected
    assert not expected & {"client_secret", "secret", "password", "token", "config"}


@pytest.mark.kiwi_id(2250)
async def test_list_products_empty_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """未播种空库：清单空数组 + total=0；明细 404（与启动空目录容错口径一致）。"""
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}")
    get_settings.cache_clear()
    app = ApplicationFactory().create(None)
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers.update(auth_headers())
        listed = await client.get("/api/v1/products")
        assert listed.json()["data"] == {"list": [], "total": 0, "page": 1, "size": 20}

        missing = await client.get("/api/v1/products/biz")
        assert missing.status_code == 404
        assert missing.json()["code"] == 10002


@pytest.mark.kiwi_id(2250)
async def test_products_routes_get_only() -> None:
    """只读边界：产品档案路由仅 GET（以 OpenAPI 契约为准）。"""
    app = ApplicationFactory().create(None)
    operations: ConcurrentStableSet[str] = ConcurrentStableSet()
    for path, item in app.openapi()["paths"].items():
        if path.startswith("/api/v1/products"):
            operations.update(set(item))
    assert operations == {"get"}
