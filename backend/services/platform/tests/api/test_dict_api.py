"""字典族接口响应契约测试（Kiwi 2290）：响应类型化与形状（02_12）。

用例统一用**不落库的注册键 `module`** 验证响应形状（`role` 走平台实体表，受 02_11 遗留
`sys_role.form_key` 未落测试库影响，属既有失败、非本任务引入）。
"""

from typing import Any, cast

import pytest
from fastapi import Request
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.dict.base import DictBatchResult, DictItem, DictTypeResult
from bms_core.dict.query import (
    DictAdvQueryResult,
    DictAttrInfo,
    DictAttrListResponse,
    DictQueryProviderInfo,
    DictQueryProviderListResponse,
)
from bms_platform.api.dict import (
    _accept_locale,  # pyright: ignore[reportPrivateUsage]
    list_query_providers,
    parse_values,
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


# ------------------------------------------------------------- 02_09 补齐：解析 / 提供者 / 语言


def test_parse_values_splits_and_drops_blanks() -> None:
    """`parse_values`：逗号分隔、去空白、丢空项（空串 → 空元组）。"""
    assert parse_values("") == ()
    assert parse_values(" a , b ,, c ") == ("a", "b", "c")


class _ProviderWithInfo:
    """带 `info()` 声明的查询提供者替身（限定适用字典标识）。"""

    def info(self) -> DictQueryProviderInfo:
        """提供者声明（仅适用 `alpha`）。

        Returns:
            DictQueryProviderInfo: 清单项声明。
        """
        return DictQueryProviderInfo(
            key="alpha",
            name="Alpha",
            target="business",
            data_source_keys=("alpha",),
            param_schema=ConcurrentStableDict(),
        )


class _ProviderPlain:
    """无 `info()` 的提供者替身（按契约降级为 `business` 目标）。"""

    def describe(self) -> str:
        """提供者描述。

        Returns:
            str: 描述文案。
        """
        return "普通提供者"


class _RegistryStub:
    """查询提供者注册表替身：含缺项键与非匹配键。"""

    def keys(self) -> ConcurrentStableList[str]:
        """注册表键清单。

        Returns:
            ConcurrentStableList[str]: 键清单。
        """
        return ConcurrentStableList(["alpha", "missing", "plain"])

    def get(self, key: str) -> object | None:
        """按键取提供者（`missing` 返 None）。

        Args:
            key: 提供者键。

        Returns:
            object | None: 提供者实例；缺项为 None。
        """
        if key == "missing":
            return None
        return _ProviderWithInfo() if key == "alpha" else _ProviderPlain()


async def test_query_providers_skip_missing_and_mismatched() -> None:
    """提供者清单：缺项键跳过、标识不匹配跳过、无 `info()` 按契约降级。"""
    result = await list_query_providers(cast("Any", _RegistryStub()), "beta")
    items = cast("Any", result.data).items
    assert [item.key for item in items] == ["plain"]
    assert items[0].target == "business"


def _request(accept_language: str) -> Request:
    """构造带 `Accept-Language` 的最小请求对象。

    Args:
        accept_language: 请求语言头原文。

    Returns:
        Request: 请求对象。
    """
    return Request(scope={"type": "http", "headers": [(b"accept-language", accept_language.encode())]})


def test_accept_locale_matches_supported_and_prefix() -> None:
    """语言解析：清单内精确命中；区域变体按前缀回落；无匹配回默认语言。"""
    assert _accept_locale(_request("en-US")) == "en-US"
    assert _accept_locale(_request("zh")) == "zh-CN"
    assert _accept_locale(_request("fr")) == "zh-CN"
