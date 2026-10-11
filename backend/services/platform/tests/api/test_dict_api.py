"""字典族接口响应契约测试（Kiwi 2290）：响应类型化与形状（02_12）。

用例统一用**不落库的注册键 `module`** 验证响应形状（`role` 走平台实体表，受 02_11 遗留
`sys_role.form_key` 未落测试库影响，属既有失败、非本任务引入）。
"""

import pytest
from httpx import AsyncClient

from bms_core.dict.base import DictBatchResult, DictItem, DictTypeResult
from bms_core.dict.query import (
    DictAdvQueryResult,
    DictAttrInfo,
    DictAttrListResponse,
    DictQueryProviderInfo,
    DictQueryProviderListResponse,
)
from bms_platform.main import ApplicationFactory

_REF_PATHS = {
    "/api/v1/dicts/{data_source_key}": "ApiResponse_DictTypeResult_",
    "/api/v1/dicts/batch": "ApiResponse_DictBatchResult_",
    "/api/v1/dicts/{data_source_key}/advanced-query": "ApiResponse_DictAdvQueryResult_",
    "/api/v1/dicts/{data_source_key}/attrs": "ApiResponse_DictAttrListResponse_",
    "/api/v1/dicts/query-providers": "ApiResponse_DictQueryProviderListResponse_",
}


@pytest.mark.kiwi_id(2290)
async def test_dict_type_result_contract(client: AsyncClient) -> None:
    """GET /dicts/{data_source_key} → DictTypeResult 形状；条目字段与 DictItem 一致。"""
    resp = await client.get("/api/v1/dicts/module")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data) == set(DictTypeResult.model_fields)
    assert isinstance(data["version"], int)
    if data["items"] is None:
        return
    for item in data["items"]:
        assert set(item) == set(DictItem.model_fields)


@pytest.mark.kiwi_id(2290)
async def test_dict_batch_contract(client: AsyncClient) -> None:
    """POST /dicts/batch → DictBatchResult 形状（items 按标识键控）。"""
    resp = await client.post("/api/v1/dicts/batch", json={"types": ["module"], "locale": "zh-CN"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data) == set(DictBatchResult.model_fields)
    assert set(data["items"]) == {"module"}
    inner = data["items"]["module"]
    if inner is not None:
        assert set(inner) == set(DictTypeResult.model_fields)


@pytest.mark.kiwi_id(2290)
async def test_dict_query_providers_contract(client: AsyncClient) -> None:
    """GET /dicts/query-providers → {items:[DictQueryProviderInfo]}。"""
    resp = await client.get("/api/v1/dicts/query-providers")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data) == set(DictQueryProviderListResponse.model_fields)
    assert len(data["items"]) >= 1
    assert set(data["items"][0]) == set(DictQueryProviderInfo.model_fields)

    filtered = await client.get("/api/v1/dicts/query-providers", params={"data_source_key": "module"})
    assert filtered.status_code == 200
    assert "items" in filtered.json()["data"]


@pytest.mark.kiwi_id(2290)
async def test_dict_attrs_contract(client: AsyncClient) -> None:
    """GET /dicts/{data_source_key}/attrs → {items:[DictAttrInfo]}。"""
    resp = await client.get("/api/v1/dicts/module/attrs")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data) == set(DictAttrListResponse.model_fields)
    assert len(data["items"]) >= 1
    assert set(data["items"][0]) == set(DictAttrInfo.model_fields)


@pytest.mark.kiwi_id(2290)
async def test_dict_advanced_query_contract(client: AsyncClient) -> None:
    """POST /dicts/{data_source_key}/advanced-query → DictAdvQueryResult 形状。"""
    resp = await client.post("/api/v1/dicts/module/advanced-query", json={"target": "items", "page": 1, "size": 20})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data) == set(DictAdvQueryResult.model_fields)


@pytest.mark.kiwi_id(2290)
async def test_dict_family_contract_schema() -> None:
    """契约正式化：字典族端点 200 响应引用具名 ApiResponse_* 组件。"""
    app = ApplicationFactory().create(None)
    paths = app.openapi()["paths"]
    for path, component in _REF_PATHS.items():
        methods = [item for item in paths[path] if item in {"get", "post"}]
        assert len(methods) == 1
        ref = paths[path][methods[0]]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        assert ref == f"#/components/schemas/{component}"
