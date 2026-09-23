"""字典跨服务读出口测试（Kiwi 1078）：契约路径与参数 / 响应解析 / 降级回退 / 按值子集分批。"""

import json
from collections.abc import Sequence

import pytest

from bms_core.core.context import reset_current_tenant, set_current_tenant
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.dict.base import DictBatchQuery, DictQuery, DictTranslateQuery
from bms_core.dict.http import (
    ACCEPT_LANGUAGE_HEADER,
    DICT_BATCH_PATH,
    TRANSLATE_VALUES_CHUNK,
    HttpDictSource,
    HttpDictTranslator,
)
from bms_core.edge.headers import TENANT_ID_HEADER
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse


class _FakeClient(BaseServiceClient):
    """伪服务间调用客户端：记录请求，按给定负载返回统一响应（可编排为不可达）。"""

    def __init__(self, payloads: Sequence[object] | None = None, *, unavailable: bool = False) -> None:
        """初始化。

        Args:
            payloads: 依次返回的 `data` 负载（用尽后复用最后一个）。
            unavailable: 是否模拟下游不可达（抛 `ServiceUnavailableError`）。
        """
        self.requests: list[ServiceRequest] = []
        self._payloads = list(payloads or [])
        self._unavailable = unavailable

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """记录请求并返回响应（或抛不可达）。

        Args:
            request: 调用请求。

        Returns:
            ServiceResponse: 统一响应。

        Raises:
            ServiceUnavailableError: `unavailable` 为真时抛出。
        """
        self.requests.append(request)
        if self._unavailable:
            raise ServiceUnavailableError("下游不可达")
        payload: object = self._payloads[min(len(self.requests) - 1, len(self._payloads) - 1)] if self._payloads else {}
        body = json.dumps({"code": 0, "message": "ok", "data": payload}).encode()
        return ServiceResponse(status_code=200, content=body)


def _item_payload(value: str, label: str) -> dict[str, object]:
    """构造条目负载。

    Args:
        value: 条目值。
        label: 条目标签。

    Returns:
        dict[str, object]: 条目负载。
    """
    return {"value": value, "label": label, "code": value, "parent_id": None, "sort": 1, "status": "enabled"}


@pytest.mark.kiwi_id(1078)
async def test_by_type_maps_query_and_parses_response() -> None:
    """单类型取数：路径 / 查询参数 / 语言与租户头透传，响应解析为 `DictTypeResult`。"""
    client = _FakeClient([{"version": 7, "items": [_item_payload("enabled", "启用")], "has_more": False, "total": 1}])
    source = HttpDictSource(client=client)
    token = set_current_tenant("demo")
    try:
        result = await source.by_type(
            DictQuery(dict_type="status", version=6, keyword="启", parent_id=None, values=None, limit=10)
        )
    finally:
        reset_current_tenant(token)

    request = client.requests[0]
    headers = request.headers or {}
    assert request.service == "platform"
    assert request.method == "GET"
    assert request.path == "/api/v1/dicts/status"
    assert request.query == {"version": "6", "keyword": "启", "limit": "10"}
    assert headers[ACCEPT_LANGUAGE_HEADER] == "zh-CN"
    assert headers[TENANT_ID_HEADER] == "demo"
    assert result.version == 7
    assert result.total == 1
    assert result.items is not None and result.items[0].label == "启用"


@pytest.mark.kiwi_id(1078)
async def test_by_type_version_current_and_values_subset() -> None:
    """版本一致（平台侧返回 `items=null`）→ `items=None`；按值子集经逗号拼接传参。"""
    client = _FakeClient([{"version": 7, "items": None, "has_more": False, "total": 0}])
    source = HttpDictSource(client=client)
    result = await source.by_type(DictQuery(dict_type="status", values=("a", "b")))
    assert result.items is None
    assert client.requests[0].query == {"values": "a,b"}


@pytest.mark.kiwi_id(1078)
async def test_batch_posts_body_and_parses_items() -> None:
    """批量取数：POST 契约路径 + JSON 体（types / version / locale），逐类型解析（版本一致为 None）。"""
    client = _FakeClient(
        [
            {
                "version": 9,
                "items": {
                    "status": {"version": 9, "items": [_item_payload("enabled", "启用")], "total": 1},
                    "level": None,
                },
            }
        ]
    )
    source = HttpDictSource(client=client)
    result = await source.batch(DictBatchQuery(types=("status", "level"), version=8))

    request = client.requests[0]
    assert request.method == "POST"
    assert request.path == DICT_BATCH_PATH
    assert request.json_body == {"types": ["status", "level"], "version": 8, "locale": "zh-CN"}
    assert result.version == 9
    status = result.items["status"]
    assert status is not None and status.items is not None and status.items[0].value == "enabled"
    assert result.items["level"] is None


@pytest.mark.kiwi_id(1078)
async def test_translate_maps_hits_and_keeps_misses() -> None:
    """翻译：命中取 label、未命中回退原值；单批内一次调用。"""
    client = _FakeClient([{"version": 3, "items": [_item_payload("a", "甲")], "total": 1}])
    translator = HttpDictTranslator(client=client)
    mapping = await translator.translate(DictTranslateQuery(dict_type="status", values=("a", "b")))
    assert mapping == {"a": "甲", "b": "b"}
    assert client.requests[0].query == {"values": "a,b"}


@pytest.mark.kiwi_id(1078)
async def test_translate_chunks_large_value_sets() -> None:
    """翻译：value 子集超单批上限时按批拆分调用（避免一次请求过大）。"""
    size = TRANSLATE_VALUES_CHUNK
    values = tuple(f"v{index}" for index in range(size + 1))
    client = _FakeClient([{"version": 1, "items": [_item_payload(values[0], "首")], "total": 1}])
    translator = HttpDictTranslator(client=client)
    mapping = await translator.translate(DictTranslateQuery(dict_type="big", values=values))
    assert len(client.requests) == 2
    assert client.requests[0].query is not None and client.requests[0].query["values"].count(",") == size - 1
    assert mapping[values[0]] == "首"


@pytest.mark.kiwi_id(1078)
async def test_degrade_when_platform_unavailable() -> None:
    """降级：平台侧不可达 → 取数返回空结果、批量逐类型空结果、翻译回退原值（不抛业务错）。"""
    source = HttpDictSource(client=_FakeClient(unavailable=True))
    single = await source.by_type(DictQuery(dict_type="status"))
    assert single.items == () and single.version == 0
    batch = await source.batch(DictBatchQuery(types=("status", "level")))
    assert set(batch.items) == {"status", "level"}
    assert all(item is not None and item.items == () for item in batch.items.values())

    translator = HttpDictTranslator(client=_FakeClient(unavailable=True))
    assert await translator.translate(DictTranslateQuery(dict_type="status", values=("x",))) == {"x": "x"}


@pytest.mark.kiwi_id(1078)
async def test_degrade_on_non_2xx_and_malformed_payload() -> None:
    """降级：非 2xx 与响应体非法（缺 data）同样返回空结果。"""

    class _BadClient(BaseServiceClient):
        """伪客户端：固定返回非 2xx / 非法体。"""

        def __init__(self, response: ServiceResponse) -> None:
            self._response = response

        async def call(self, request: ServiceRequest) -> ServiceResponse:
            """返回固定响应。

            Args:
                request: 调用请求（忽略）。

            Returns:
                ServiceResponse: 固定响应。
            """
            return self._response

    bad_status = HttpDictSource(client=_BadClient(ServiceResponse(status_code=503, content=b"")))
    assert (await bad_status.by_type(DictQuery(dict_type="status"))).items == ()

    malformed = HttpDictSource(client=_BadClient(ServiceResponse(status_code=200, content=b'{"code":0}')))
    assert (await malformed.by_type(DictQuery(dict_type="status"))).items == ()
