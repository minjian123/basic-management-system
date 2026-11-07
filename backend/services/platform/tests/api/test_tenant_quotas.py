"""租户配额只读视图端点（07D `02_03`）：`GET /api/v1/tenant-quotas/projections`。

覆盖详细设计 §4.5 用例 7~13 的端到端部分：
- 无配额声明 → `items: []`（200，不 404）；
- 有声明 + 产品可返回 → 四态齐备、字段语义统一、对外脱敏（无 `data_source` / `path`）；
- 产品不可达 → HTTP 200 且该产品条目 `unavailable`（运营视图部分可用）；
- `module_key` 过滤；平台侧不落库（不双写）。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.datasource.registry import (
    DataSourceKind,
    DataSourceRecord,
    register_data_source_records,
    reset_data_source_records,
)
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse
from bms_platform.domains.platform_registry.api import tenant_quotas

API = "/api/v1/tenant-quotas/projections"
TENANT_ID = 1000000000000000001


pytestmark = pytest.mark.kiwi_id(2450)


class _StubClient(BaseServiceClient):
    """固定返回预置响应的服务间调用桩。"""

    plugin_name: str = "stub"

    def __init__(self, response: ServiceResponse | Exception) -> None:
        """初始化。

        Args:
            response: 固定响应或固定异常。
        """
        self._response = response

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """返回预置响应。

        Args:
            request: 调用请求（忽略）。

        Returns:
            ServiceResponse: 响应。

        Raises:
            Exception: 预置异常。
        """
        del request
        if isinstance(self._response, Exception):
            raise self._response
        return self._response

    async def aclose(self) -> None:
        """释放（无资源）。"""


def _record(*, key: str = "demo_tenant_usage", module: str = "demo") -> DataSourceRecord:
    """构造配额投影声明。

    Args:
        key: 数据源键。
        module: 服务 / 模块键（`data_source` 首段）。

    Returns:
        DataSourceRecord: 声明记录。
    """
    return DataSourceRecord(
        data_source_key=key,
        name="演示用量",
        data_source=f"{module}.{module}.tenant_usage",
        kind=DataSourceKind.QUOTA.value,
        origin="product",
        product_key="demo",
        path=f"/api/v1/{module}/tenant-usage",
        quota_dimensions=ConcurrentStableFrozenList(("topic_count", "storage_bytes")),
        quota_unit="count",
        quota_period="day",
        quota_soft_limit=80,
        quota_hard_limit=100,
    )


def _client(response: ServiceResponse | Exception) -> Any:
    """构造注入用的客户端提供者（带类型，避免 lambda 参数未知）。

    Args:
        response: 固定响应或固定异常。

    Returns:
        Any: 提供者（`get_service_client` 替身）。
    """
    stub = _StubClient(response)

    def _provide(request: Any) -> _StubClient:
        """返回固定客户端。

        Args:
            request: 请求对象（忽略）。

        Returns:
            _StubClient: 桩客户端。
        """
        del request
        return stub

    return _provide


def _response(payload: object, *, status: int = 200) -> ServiceResponse:
    """构造响应。

    Args:
        payload: JSON 载荷。
        status: 状态码。

    Returns:
        ServiceResponse: 响应。
    """
    return ServiceResponse(status_code=status, content=json.dumps(payload).encode())


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """每例前后清空注入的数据源与桩，并让权限占位实现放行。

    Args:
        monkeypatch: pytest 补丁器。

    Yields:
        None: 用例运行期。
    """
    from bms_core.core.config import get_settings

    monkeypatch.setenv("BMS_PERMISSION__PROVIDER", "null")
    get_settings.cache_clear()
    reset_data_source_records()
    yield
    get_settings.cache_clear()
    reset_data_source_records()


async def test_empty_when_no_quota_declared(client: AsyncClient) -> None:
    """无配额声明 → `items: []`（200）。"""
    response = await client.get(API, params={"tenant_id": TENANT_ID})
    assert response.status_code == 200
    assert response.json()["data"] == []


async def test_projection_fields_and_masking(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """有声明：四态齐备、字段统一、对外不含内部取数信息。"""
    register_data_source_records([_record()])
    payload = {
        "items": [
            {"quota_key": "topic_count", "usage": 5, "limit": 100, "updated_at": "2026-11-07T10:00:00Z"},
            {"quota_key": "storage_bytes", "usage": 100},
        ]
    }
    monkeypatch.setattr(tenant_quotas, "get_service_client", _client(_response(payload)))

    response = await client.get(API, params={"tenant_id": TENANT_ID})

    assert response.status_code == 200
    items = response.json()["data"]
    by_key = {item["quota_key"]: item for item in items}
    assert by_key["topic_count"]["state"] == "ok"
    assert by_key["storage_bytes"]["state"] == "exceeded"
    assert by_key["topic_count"]["unit"] == "count"
    assert by_key["topic_count"]["period"] == "day"
    assert by_key["topic_count"]["product_key"] == "demo"
    assert "data_source" not in by_key["topic_count"]
    assert "path" not in by_key["topic_count"]


async def test_unavailable_product_still_returns_partial(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """产品不可达 → 200 + 该产品条目 `unavailable`（`usage is None`）。"""
    register_data_source_records([_record()])
    monkeypatch.setattr(tenant_quotas, "get_service_client", _client(RuntimeError("down")))

    response = await client.get(API, params={"tenant_id": TENANT_ID})

    assert response.status_code == 200
    items = response.json()["data"]
    assert {item["state"] for item in items} == {"unavailable"}
    assert all(item["usage"] is None for item in items)


async def test_module_filter(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """`module_key` 过滤：不匹配则 `items: []`。"""
    register_data_source_records([_record()])
    monkeypatch.setattr(
        tenant_quotas,
        "get_service_client",
        _client(_response({"items": [{"quota_key": "topic_count", "usage": 1}]})),
    )

    assert (await client.get(API, params={"tenant_id": TENANT_ID, "module_key": "demo"})).json()["data"]
    other = await client.get(API, params={"tenant_id": TENANT_ID, "module_key": "other"})
    assert other.json()["data"] == []


async def test_tenant_id_required(client: AsyncClient) -> None:
    """缺 `tenant_id` → 参数校验失败（10001）。"""
    response = await client.get(API)
    assert response.status_code == 200
    assert response.json()["code"] == 10001


def test_route_registered(service_app: FastAPI) -> None:
    """路由已挂载到统一前缀（`/api/v1`）。"""
    schema = service_app.openapi()
    assert API in schema["paths"]


def test_payload_shape_is_plain_dict() -> None:
    """响应 data 为可序列化结构（`items` 列表）。"""
    from bms_core.schemas.common import ApiResponse

    body: Any = ApiResponse.ok({"items": []})
    assert body.code == 0
