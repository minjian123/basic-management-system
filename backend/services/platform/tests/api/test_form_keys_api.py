"""表单标识清单接口契约测试（Kiwi 2292）：字段与契约一致 / kind 过滤 / 鉴权 / 契约组件（02-13-1）。"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.registry.forms import FORM_CATALOG, FormKind, FormRecord, FormRegistry, merge_form_records
from bms_core.schemas.form import FormKeyListResponse, FormKeyResponse

# 响应字段集 = 声明字段 ∪ 计算字段（`is_dict` 为派生字段，不入 `model_fields`）。
_ITEM_FIELDS = set(FormKeyResponse.model_fields) | set(FormKeyResponse.model_computed_fields)


@pytest.mark.kiwi_id(2292)
async def test_form_keys_contract(client: AsyncClient) -> None:
    """GET /api/v1/form-keys：登录即可；data.items 字段集 = 声明字段 ∪ 计算字段；枚举取值；映射闭合。

    取数口径是**应用级视图**（构建期清单 + 各产品注入记录）：`form_design` 等用例为自建业务码
    追加注入项（`app.state.form_registry`），故不对总条数做全等断言——只校验「构建期清单逐条在列、
    映射闭合、派生字段与 kind 同源」，注入项由各自的用例负责。
    """
    resp = await client.get("/api/v1/form-keys")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert set(body["data"]) == set(FormKeyListResponse.model_fields)
    items = body["data"]["items"]
    by_key = {item["form_key"]: item for item in items}
    catalog = {record.form_key: record for record in FORM_CATALOG}
    assert set(catalog) <= set(by_key), "构建期清单必须全部在列"
    first = items[0]
    assert set(first) == _ITEM_FIELDS
    assert first["kind"] in {"dict", "form"}
    assert first["status"] in {"enabled", "disabled"}
    # form_key → data_source_key 闭合：构建期清单逐条与登记记录一致。
    for form_key, record in catalog.items():
        item = by_key[form_key]
        assert item["data_source_key"] is not None
        assert item["data_source_key"] == record.data_source_key
        assert item["kind"] == record.kind
    # 派生字段 is_dict：与 kind 同源（构建期清单均为字典表），且非字典项为 False。
    catalog_items = [by_key[form_key] for form_key in catalog]
    assert all(item["is_dict"] == (item["kind"] == "dict") for item in catalog_items)
    assert all(item["is_dict"] is True for item in catalog_items)
    form_record = FormRecord(
        form_key="purchase_order",
        table="biz_purchase_order",
        name="采购申请",
        kind=FormKind.FORM.value,
        data_source_key="purchase_order",
    )
    assert FormKeyResponse.model_validate(form_record).is_dict is False


@pytest.mark.kiwi_id(2292)
async def test_form_keys_kind_filter(client: AsyncClient) -> None:
    """?kind 过滤生效；非法 kind → 200 / 10001（ParamError 统一响应口径）。"""
    all_items = (await client.get("/api/v1/form-keys")).json()["data"]["items"]
    dict_items = (await client.get("/api/v1/form-keys", params={"kind": "dict"})).json()["data"]["items"]
    form_items = (await client.get("/api/v1/form-keys", params={"kind": "form"})).json()["data"]["items"]
    assert len(all_items) > 0
    assert all(item["kind"] == "dict" for item in dict_items)
    assert all(item["kind"] == "form" for item in form_items)
    assert len(dict_items) + len(form_items) == len(all_items)

    invalid = await client.get("/api/v1/form-keys", params={"kind": "ghost"})
    assert invalid.status_code == 200
    assert invalid.json()["code"] == 10001
    assert invalid.json()["data"] is None


@pytest.mark.kiwi_id(2292)
async def test_form_keys_reads_application_view(
    client: AsyncClient, service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """端点取**应用级视图**：替换 `app.state.form_registry` 后清单含注入的产品登记项（`form_records()` 通道）。

    替换用 `monkeypatch.setattr`：装配常驻后 `app.state` 跨用例复用，直接赋值会把注入项留给后继用例。
    """
    injected: ConcurrentStableList[FormRecord] = ConcurrentStableList(
        (FormRecord(form_key="mdm_dept", table="mdm_dept", name="部门", data_source_key="mdm_dept"),)
    )
    monkeypatch.setattr(service_app.state, "form_registry", FormRegistry(merge_form_records(injected=injected)))
    items = (await client.get("/api/v1/form-keys")).json()["data"]["items"]
    assert len(items) == len(FORM_CATALOG) + 1
    assert items[-1]["form_key"] == "mdm_dept"
    assert items[-1]["data_source_key"] == "mdm_dept"


@pytest.mark.kiwi_id(2292)
async def test_form_keys_requires_auth(service_app: FastAPI) -> None:
    """鉴权：无有效凭证 → 401 / 20001。"""
    async with AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as anonymous:
        resp = await anonymous.get("/api/v1/form-keys")
    assert resp.status_code == 401
    assert resp.json()["code"] == 20001


@pytest.mark.kiwi_id(2292)
async def test_form_keys_contract_schema(service_app: FastAPI) -> None:
    """契约正式化：该端点 200 响应引用 ApiResponse_FormKeyListResponse_ 具名组件，且组件非空。"""
    schema = service_app.openapi()
    path = schema["paths"]["/api/v1/form-keys"]["get"]
    ref = path["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ref == "#/components/schemas/ApiResponse_FormKeyListResponse_"
    components = schema["components"]["schemas"]
    assert set(components["FormKeyResponse"]["properties"]) == _ITEM_FIELDS
    assert components["FormKeyResponse"]["properties"]["is_dict"]["type"] == "boolean"
    assert set(components["FormKind"]["enum"]) == {"dict", "form"}
