"""数据源登记清单接口契约测试（Kiwi 2290）：字段与契约一致 / kind 过滤 / 鉴权 / 契约组件（02_12）。"""

import pytest
from httpx import ASGITransport, AsyncClient

from bms_core.application import service_lifespan as lifespan
from bms_core.datasource.registry import DataSourceKind, DataSourceRecord
from bms_core.schemas.datasource import DataSourceListResponse, DataSourceResponse
from bms_platform.main import ApplicationFactory

# 响应字段集 = 声明字段 ∪ 计算字段（`is_dict` 为派生字段，不入 `model_fields`）。
_ITEM_FIELDS = set(DataSourceResponse.model_fields) | set(DataSourceResponse.model_computed_fields)


@pytest.mark.kiwi_id(2290)
async def test_data_sources_contract(client: AsyncClient) -> None:
    """GET /api/v1/data-sources：登录即可；data.items 字段集 = 声明字段 ∪ 计算字段；枚举取值。"""
    resp = await client.get("/api/v1/data-sources")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert set(body["data"]) == set(DataSourceListResponse.model_fields)
    items = body["data"]["items"]
    assert len(items) >= 12
    first = items[0]
    assert set(first) == _ITEM_FIELDS
    assert first["kind"] in {"dict", "form"}
    assert first["origin"] in {"platform", "product"}
    assert first["status"] in {"enabled", "disabled"}
    assert isinstance(first["strategies"], list)
    assert len(first["strategies"]) > 0
    assert set(first["strategies"]) <= {"select", "region", "match", "extension"}
    assert isinstance(first["allowlist"], list)
    # 派生字段 is_dict：与 kind 同源（本清单均为字典表），且非字典项为 False。
    assert all(item["is_dict"] == (item["kind"] == "dict") for item in items)
    form_record = DataSourceRecord(
        data_source_key="purchase_order",
        name="采购申请",
        data_source="biz.purchase_order",
        kind=DataSourceKind.FORM.value,
        origin="product",
        product_key="biz",
    )
    assert DataSourceResponse.model_validate(form_record).is_dict is False


@pytest.mark.kiwi_id(2290)
async def test_data_sources_kind_filter(client: AsyncClient) -> None:
    """?kind 过滤生效；非法 kind → 200 / 10001（ParamError 统一响应口径）。"""
    all_items = (await client.get("/api/v1/data-sources")).json()["data"]["items"]
    dict_items = (await client.get("/api/v1/data-sources", params={"kind": "dict"})).json()["data"]["items"]
    form_items = (await client.get("/api/v1/data-sources", params={"kind": "form"})).json()["data"]["items"]
    assert len(all_items) > 0
    assert all(item["kind"] == "dict" for item in dict_items)
    assert all(item["kind"] == "form" for item in form_items)
    assert len(dict_items) + len(form_items) == len(all_items)

    invalid = await client.get("/api/v1/data-sources", params={"kind": "ghost"})
    assert invalid.status_code == 200
    assert invalid.json()["code"] == 10001
    assert invalid.json()["data"] is None


@pytest.mark.kiwi_id(2290)
async def test_data_sources_requires_auth() -> None:
    """鉴权：无有效凭证 → 401 / 20001。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        resp = await anonymous.get("/api/v1/data-sources")
    assert resp.status_code == 401
    assert resp.json()["code"] == 20001


@pytest.mark.kiwi_id(2290)
async def test_data_sources_contract_schema() -> None:
    """契约正式化：该端点 200 响应引用 ApiResponse_DataSourceListResponse_ 具名组件，且组件非空。"""
    app = ApplicationFactory().create(None)
    schema = app.openapi()
    path = schema["paths"]["/api/v1/data-sources"]["get"]
    ref = path["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ref == "#/components/schemas/ApiResponse_DataSourceListResponse_"
    components = schema["components"]["schemas"]
    assert set(components["DataSourceResponse"]["properties"]) == _ITEM_FIELDS
    assert components["DataSourceResponse"]["properties"]["is_dict"]["type"] == "boolean"
    assert components["DataSourceKind"]["enum"] == ["dict", "form"]
