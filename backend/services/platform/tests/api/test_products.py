"""产品档案只读接口（Kiwi 2250）：清单分页 / 筛选 / 明细 / 404 / 字段护栏 / 空库 / 路由只读。

期望值一律**派生自登记视图** `product_catalog_view()`（平台种子 + 已装载产品清单），不写死产品行：
本地工作区装载产品仓清单、CI 未装载，两种环境断言同源成立。

重写口径（13_11）：全部复用会话级装配实例（`client` / `service_app`），不再自建应用壳。
"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.schemas.product import ProductResponse
from bms_core.services.module_registry import PRODUCT_CATALOG, ProductRecord
from bms_core.testing.namespace import Namespace

API = "/api/v1/products"


def _expected() -> ConcurrentStableList[ProductRecord]:
    """静态声明清单的产品档案（`PRODUCT_CATALOG` 常量，插入序）。

    共享库叠加下运行时产品视图会含别的 worker 登记的测试产品，**不能**当「期望全量」；
    接口契约只承诺「静态声明的产品全部在册」。

    Returns:
        ConcurrentStableList[ProductRecord]: 产品档案记录。
    """
    return ConcurrentStableList(PRODUCT_CATALOG)


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
async def test_list_products_contract(client: AsyncClient) -> None:
    """分页结构（种子清单为前缀）；status 筛选；POST/PUT/DELETE 405。"""
    resp = await client.get(API)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    expected = _expected()
    assert (data["page"], data["size"]) == (1, 20)
    # 共享库叠加：并发用例会改写产品档案（复位重播种），总数只判非空
    assert data["total"] >= 1

    full = await client.get(API, params={"size": 200})
    listed = [item["product_key"] for item in full.json()["data"]["list"]]
    assert {record.product_key for record in expected} <= set(listed)
    # 前端包来源：产品前端工程标识（已接入产品回填、未接入留空）
    sources = {item["product_key"]: item["frontend_package_source"] for item in full.json()["data"]["list"]}
    assert {record.product_key: sources[record.product_key] for record in expected} == {
        record.product_key: record.frontend_package_source for record in expected
    }

    planned = await client.get(API, params={"status": "planned"})
    planned_rows = planned.json()["data"]["list"]
    planned_known = _keys_with_status("planned")
    assert all(item["status"] == "planned" for item in planned_rows)
    assert [item["product_key"] for item in planned_rows if item["product_key"] in planned_known] == planned_known

    enabled = await client.get(API, params={"status": "enabled"})
    enabled_rows = enabled.json()["data"]["list"]
    enabled_known = _keys_with_status("enabled")
    assert all(item["status"] == "enabled" for item in enabled_rows)
    assert [item["product_key"] for item in enabled_rows if item["product_key"] in enabled_known] == enabled_known

    retired = await client.get(API, params={"status": "retired"})
    retired_known = _keys_with_status("retired")
    retired_rows = retired.json()["data"]["list"]
    assert all(item["status"] == "retired" for item in retired_rows)
    # 叠加口径：别的 worker 可能登记测试产品（含 retired 态），只判「声明清单全部在册」。
    assert set(retired_known) <= {item["product_key"] for item in retired_rows}
    assert retired.json()["data"]["total"] >= len(retired_known)

    for method in ("POST", "PUT", "DELETE"):
        resp = await client.request(method, API, json={"product_key": "ghost"})
        assert resp.status_code == 405, method


@pytest.mark.kiwi_id(2250)
async def test_list_products_pagination_and_sort(client: AsyncClient) -> None:
    """分页生效（size / 末页）；排序白名单；页码限深 10001。"""
    expected = _expected_keys()
    first = await client.get(API, params={"page": 1, "size": 2})
    first_data = first.json()["data"]
    total = first_data["total"]
    page_keys = [item["product_key"] for item in first_data["list"]]
    assert len(page_keys) == len(set(page_keys))
    assert total >= len(expected)

    last_page = -(-total // 2)
    last_data = (await client.get(API, params={"page": last_page, "size": 2})).json()["data"]
    assert len(last_data["list"]) == min(2, last_data["total"] - (last_page - 1) * 2)

    full = await client.get(API, params={"size": 200})
    keys = [item["product_key"] for item in full.json()["data"]["list"]]
    assert set(expected) <= set(keys)

    # 排序白名单：非法字段被忽略 ⇒ 与缺省首条一致（不比较跨请求全表位置，叠加场景不稳）。
    default_first = [item["product_key"] for item in (await client.get(API, params={"size": 1})).json()["data"]["list"]]
    ignored_first = [
        item["product_key"]
        for item in (await client.get(API, params={"order_by": "ghost", "size": 1})).json()["data"]["list"]
    ]
    assert ignored_first == default_first

    too_deep = await client.get(API, params={"page": 101})
    assert too_deep.status_code == 200
    assert too_deep.json()["code"] == 10001


@pytest.mark.kiwi_id(2250)
async def test_get_product_detail_and_not_found(client: AsyncClient) -> None:
    """明细：命中返回登记字段；未登记 404 + 10002 + 统一响应体。"""
    expected = _expected()
    detail = await client.get(f"{API}/{expected[0].product_key}")
    assert detail.status_code == 200
    data = detail.json()["data"]
    assert data["product_key"] == expected[0].product_key
    assert data["name"] == expected[0].name
    assert data["status"] == expected[0].status
    assert data["frontend_package_source"] == expected[0].frontend_package_source

    loaded = next((record for record in expected if record.product_key == "mdm"), None)
    if loaded is not None:
        mdm = await client.get(f"{API}/mdm")
        assert mdm.status_code == 200
        assert mdm.json()["data"]["status"] == loaded.status
        assert mdm.json()["data"]["frontend_package_source"] == loaded.frontend_package_source

    missing = await client.get(f"{API}/ghost")
    assert missing.status_code == 404
    body = missing.json()
    assert body["code"] == 10002
    assert body["data"] is None
    assert "产品未登记" in body["message"]


@pytest.mark.kiwi_id(2250)
async def test_products_response_fields_whitelist(client: AsyncClient) -> None:
    """响应字段集严格等于 `ProductResponse`（不含密钥 / 敏感项）。"""
    expected = set(ProductResponse.model_fields)
    listed = await client.get(API)
    assert set(listed.json()["data"]["list"][0]) == expected
    detail = await client.get(f"{API}/biz")
    assert set(detail.json()["data"]) == expected
    assert not expected & {"client_secret", "secret", "password", "token", "config"}


@pytest.mark.kiwi_id(2250)
async def test_list_products_empty_catalog(client: AsyncClient, ns: Namespace) -> None:
    """按本用例唯一产品键过滤：分页 `total=0`。"""
    missing_key = ns.code("no-such-product")
    response = await client.get(API, params={"product_key": missing_key})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 0  # premise: own-data 过滤键带本用例命名空间前缀，他人不可能同键
    assert data["list"] == []  # premise: own-data 同上，空列表只说明该唯一键无行


@pytest.mark.kiwi_id(2250)
async def test_products_routes_get_only(service_app: FastAPI) -> None:
    """只读边界：产品档案路由仅 GET（以 OpenAPI 契约为准）。"""
    operations: ConcurrentStableSet[str] = ConcurrentStableSet()
    for path, item in service_app.openapi()["paths"].items():
        if path.startswith(API):
            operations.update(set(item))
    assert operations == {"get"}
