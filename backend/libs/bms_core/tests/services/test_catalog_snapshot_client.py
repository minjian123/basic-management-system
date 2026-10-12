"""服务目录快照契约用例（`bms_core/catalog/base.py`）：拉取、响应体校验与缺字段兜底。

补齐远端契约客户端未覆盖路径：非 2xx、`data` 非数组、行非对象、必填字段缺失与成功路径。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from bms_core.catalog.base import CATALOG_SERVICE_KEY, CATALOG_SNAPSHOT_PATH, fetch_catalog_snapshot
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.servicecall.base import ServiceRequest, ServiceResponse

_ROW = json.loads(
    """
{
  "module_key": "sys",
  "name": "平台",
  "table_prefix": "sys_",
  "event_domain": "sys",
  "errcode_segment": null,
  "service_key": "platform",
  "business_code": null,
  "service_group": "foundation",
  "build_batch": 0,
  "service_version": "0.1.0",
  "contract_version": "0.1.0",
  "product_key": null,
  "status": "enabled"
}
"""
)


class _Client:
    """服务间客户端替身（记录请求并回包）。"""

    def __init__(self, response: ServiceResponse) -> None:
        """初始化。

        Args:
            response: 固定回包。
        """
        self.response = response
        self.requests: ConcurrentStableList[ServiceRequest] = ConcurrentStableList()

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """记录请求并返回固定回包。

        Args:
            request: 服务间请求。

        Returns:
            ServiceResponse: 固定回包。
        """
        self.requests.add(request)
        return self.response


def _client(response: ServiceResponse) -> Any:
    """构造客户端替身（以 `Any` 暴露，供契约调用参数位使用）。

    Args:
        response: 固定回包。

    Returns:
        Any: 客户端替身。
    """
    return _Client(response)


def _response(payload: object, status_code: int = 200) -> ServiceResponse:
    """构造统一响应。

    Args:
        payload: 响应体对象。
        status_code: 状态码。

    Returns:
        ServiceResponse: 响应。
    """
    return ServiceResponse(status_code=status_code, content=json.dumps(payload).encode())


async def test_fetch_catalog_snapshot_success() -> None:
    """成功路径：2xx + `data` 行数组 → 记录清单（缺省服务标识与快照路径）。"""
    client = _client(_response({"code": 0, "data": [_ROW]}))
    records = await fetch_catalog_snapshot(client)
    assert [record.module_key for record in records] == ["sys"]
    assert client.requests[0].path == CATALOG_SNAPSHOT_PATH
    assert client.requests[0].service == CATALOG_SERVICE_KEY


async def test_fetch_catalog_snapshot_rejects_bad_response() -> None:
    """非 2xx / `data` 非数组 / 行非对象 → 10007。"""
    with pytest.raises(ServiceUnavailableError):
        await fetch_catalog_snapshot(_client(_response({"code": 0, "data": []}, status_code=503)))
    with pytest.raises(ServiceUnavailableError):
        await fetch_catalog_snapshot(_client(_response({"code": 0})))
    with pytest.raises(ServiceUnavailableError):
        await fetch_catalog_snapshot(_client(_response({"code": 0, "data": ["x"]})))


async def test_fetch_catalog_snapshot_rejects_missing_field() -> None:
    """清单行缺必填字段 → 10007。"""
    partial = dict(_ROW)
    del partial["name"]
    with pytest.raises(ServiceUnavailableError):
        await fetch_catalog_snapshot(_client(_response({"code": 0, "data": [partial]})))
