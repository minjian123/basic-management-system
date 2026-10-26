"""产品档案只读接口测试（Kiwi 2250）：清单分页 / 筛选 / 明细 / 404 / 字段护栏 / 空库 / 路由只读。

期望值一律**派生自登记视图** `product_catalog_view()`（平台种子 + 已装载产品清单），不写死产品行：
本地工作区装载产品仓清单、CI 未装载，两种环境断言同源成立（04_05 测试稳定性收口）。
"""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from bms_core.application import service_lifespan as lifespan
from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.config import get_settings
from bms_core.schemas.product import ProductResponse
from bms_core.services.module_registry import ProductRecord, product_catalog_view
from bms_platform.main import ApplicationFactory
from tests_support.auth import auth_headers


def _expected() -> ConcurrentStableList[ProductRecord]:
    """期望的产品档案（与启动播种同源的登记视图，插入序）。

    Returns:
        ConcurrentStableList[ProductRecord]: 产品档案记录。
    """
    return product_catalog_view()


def _expected_keys() -> ConcurrentStableList[str]:
    """期望的产品标识顺序。

    Returns:
        ConcurrentStableList[str]: 产品标识（插入序）。
    """
    return ConcurrentStableList(record.product_key for record in _expected())


def _keys_with_status(status: str) -> ConcurrentStableList[str]:
    """按状态取期望产品标识。

    Args:
        status: 产品状态（`enabled` / `planned` / `retired` / `disabled`）。

    Returns:
        ConcurrentStableList[str]: 该状态的产品标识（插入序）。
    """
    return ConcurrentStableList(record.product_key for record in _expected() if record.status == status)


@pytest.mark.kiwi_id(2250)
async def test_list_products_contract() -> None:
    """GET /api/v1/products 分页结构（与登记视图同量）；status 筛选；POST/PUT/DELETE 405。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers.update(auth_headers())
        resp = await client.get("/api/v1/products")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        data = body["data"]
        expected = _expected()
        assert (data["total"], data["page"], data["size"]) == (len(expected), 1, 20)
        assert [item["product_key"] for item in data["list"]] == [record.product_key for record in expected]
        # 前端包来源：产品前端工程标识（已接入产品回填、未接入留空；2026-10-08 随 03_04 定稿）
        assert {item["product_key"]: item["frontend_package_source"] for item in data["list"]} == {
            record.product_key: record.frontend_package_source for record in expected
        }

        planned = await client.get("/api/v1/products", params={"status": "planned"})
        assert [item["product_key"] for item in planned.json()["data"]["list"]] == _keys_with_status("planned")

        enabled = await client.get("/api/v1/products", params={"status": "enabled"})
        assert [item["product_key"] for item in enabled.json()["data"]["list"]] == _keys_with_status("enabled")

        retired = await client.get("/api/v1/products", params={"status": "retired"})
        assert [item["product_key"] for item in retired.json()["data"]["list"]] == _keys_with_status("retired")
        assert retired.json()["data"]["total"] == len(_keys_with_status("retired"))

        created = await client.post("/api/v1/products", json={"product_key": "ghost"})
        assert created.status_code == 405
        updated = await client.put("/api/v1/products", json={"product_key": "ghost"})
        assert updated.status_code == 405
        removed = await client.delete("/api/v1/products")
        assert removed.status_code == 405


@pytest.mark.kiwi_id(2250)
async def test_list_products_pagination_and_sort(client: AsyncClient) -> None:
    """分页生效（size / 末页）；排序白名单（命中排序、非法字段忽略回落 id 升序）；页码限深 10001。"""
    expected = _expected_keys()
    first = await client.get("/api/v1/products", params={"page": 1, "size": 2})
    assert [item["product_key"] for item in first.json()["data"]["list"]] == expected[:2]
    assert first.json()["data"]["total"] == len(expected)

    last_page = -(-len(expected) // 2)  # 末页页码（向上取整）
    last = await client.get("/api/v1/products", params={"page": last_page, "size": 2})
    assert [item["product_key"] for item in last.json()["data"]["list"]] == expected[(last_page - 1) * 2 :]

    sorted_by_id = await client.get("/api/v1/products", params={"order_by": "id", "order": "desc"})
    assert sorted_by_id.json()["data"]["list"][0]["product_key"] == expected[-1]

    ignored = await client.get("/api/v1/products", params={"order_by": "product_key"})
    assert ignored.json()["data"]["list"][0]["product_key"] == expected[0]

    too_deep = await client.get("/api/v1/products", params={"page": 101})
    assert too_deep.status_code == 200
    assert too_deep.json()["code"] == 10001


@pytest.mark.kiwi_id(2250)
async def test_get_product_detail_and_not_found(client: AsyncClient) -> None:
    """明细：命中返回登记字段（含产品清单装载的 `mdm`）；未登记 404 + 10002 + 统一响应体。"""
    expected = _expected()
    detail = await client.get(f"/api/v1/products/{expected[0].product_key}")
    assert detail.status_code == 200
    data = detail.json()["data"]
    assert data["product_key"] == expected[0].product_key
    assert data["name"] == expected[0].name
    assert data["status"] == expected[0].status
    assert data["frontend_package_source"] == expected[0].frontend_package_source

    loaded = next((record for record in expected if record.product_key == "mdm"), None)
    if loaded is not None:
        mdm = await client.get("/api/v1/products/mdm")
        assert mdm.status_code == 200
        assert mdm.json()["data"]["status"] == loaded.status
        assert mdm.json()["data"]["frontend_package_source"] == loaded.frontend_package_source

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
