"""字典跨服务读出口补齐用例（`02_09` 改指补齐）：参数透传、宽松解析与缓存复用路径。

补齐 `bms_core/dict/http.py` 既有用例未覆盖的路径：

- `by_type` 的 `parent_id` / `ids` 查询参数透传；
- `_as_int` 宽松取整（布尔 / 整数 / 负数字符串 / 非法）与 `_to_item` 的 `parent_id<=0` 归一；
- `batch` 的 `items` 非映射 / 值既非空也非映射；
- `HttpDictTranslator` 注入缓存后的「命中复用 + 回填」与「平台返回版本一致（`items=None`）跳过」；
- `_chunks` 非法批大小与空序列。
"""

from __future__ import annotations

from typing import Any, cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.context import get_current_tenant
from bms_core.core.serialization import stable_json_dumps
from bms_core.dict.base import DictBatchQuery, DictQuery, DictTranslateQuery
from bms_core.dict.cache import MemoryDictCacheRegion
from bms_core.dict.http import (
    HttpDataSource,
    HttpDictTranslator,
    _as_int,  # pyright: ignore[reportPrivateUsage]
    _chunks,  # pyright: ignore[reportPrivateUsage]
    _to_item,  # pyright: ignore[reportPrivateUsage]
)
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse


class _Client(BaseServiceClient):
    """伪客户端：按编排负载依次回统一响应（用尽后复用最后一个）。"""

    def __init__(self, payloads: ConcurrentStableList[object] | None = None) -> None:
        """初始化。

        Args:
            payloads: 依次返回的 `data` 负载。
        """
        self.requests: ConcurrentStableList[ServiceRequest] = ConcurrentStableList()
        self._payloads = ConcurrentStableList(payloads or ())

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """记录请求并回响应。

        Args:
            request: 调用请求。

        Returns:
            ServiceResponse: 统一响应。
        """
        self.requests.add(request)
        payload: object = self._payloads[min(len(self.requests) - 1, len(self._payloads) - 1)] if self._payloads else {}
        return ServiceResponse(
            status_code=200, content=stable_json_dumps({"code": 0, "message": "ok", "data": payload}).encode()
        )


def test_as_int_and_to_item_loose_parsing() -> None:
    """`_as_int` 宽松取整与 `_to_item` 的上级 / 颜色归一。"""
    assert _as_int(True) == 0
    assert _as_int(7) == 7
    assert _as_int("-5") == -5
    assert _as_int("nope") == 0

    item = _to_item(ConcurrentStableDict({"id": "3", "value": "a", "label": "甲", "parent_id": 0, "color": 5}))
    assert item.id == 3
    assert item.parent_id is None
    assert item.color == "5"

    child = _to_item(ConcurrentStableDict({"value": "b", "parent_id": "2"}))
    assert child.parent_id == 2
    assert child.color is None


async def test_by_type_passes_parent_id_and_ids() -> None:
    """取数查询参数：`parent_id` 与条目 id 子集（逗号拼接）均透传。"""
    client = _Client(ConcurrentStableList([{"version": 1, "items": [], "total": 0}]))
    source = HttpDataSource(client=client)

    await source.by_type(DictQuery(data_source_key="status", parent_id=0, ids=ConcurrentStableList((1, 2))))
    assert client.requests[0].query == {"parent_id": "0", "ids": "1,2"}


async def test_batch_tolerates_missing_items_mapping() -> None:
    """批量：`items` 缺省或值形态非法时，逐类型回落空结果。"""
    client = _Client(
        ConcurrentStableList(
            [
                {
                    "version": 4,
                    "items": {"status": "not-a-mapping", "level": None},
                }
            ]
        )
    )
    result = await HttpDataSource(client=client).batch(
        DictBatchQuery(types=ConcurrentStableList(("status", "level", "missing")))
    )

    assert result.version == 4
    inner_status = result.items.get("status")
    assert inner_status is not None and inner_status.items == ()
    assert result.items.get("level") is None
    assert result.items.get("missing") is not None

    no_items = _Client(ConcurrentStableList([{"version": 1}]))
    empty = await HttpDataSource(client=no_items).batch(DictBatchQuery(types=ConcurrentStableList(("status",))))
    assert empty.items.get("status") is not None


async def test_translate_reuses_cache_and_backfills_fresh() -> None:
    """翻译：命中缓存复用（不再请求该 id）+ 新 id 回填缓存。"""
    tenant = get_current_tenant()
    cache = MemoryDictCacheRegion()
    seeded: ConcurrentStableDict[int, str] = ConcurrentStableDict()
    seeded.set(1, "甲")
    await cache.aset_id_subset(tenant, "zh-CN", "status", seeded)

    client = _Client(
        ConcurrentStableList(
            [{"version": 1, "items": [{"id": 2, "value": "b", "label": "乙", "code": "b", "sort": 0}]}]
        )
    )
    translator = HttpDictTranslator(client=client, cache=cache)
    mapping = await translator.translate(DictTranslateQuery(data_source_key="status", ids=ConcurrentStableList((1, 2))))

    assert mapping.get(1) == "甲"
    assert mapping.get(2) == "乙"
    assert client.requests[0].query == {"ids": "2"}

    backfilled = await cache.aid_subset(tenant, "zh-CN", "status", ConcurrentStableList([2]))
    assert backfilled.get(2) == "乙"


async def test_translate_skips_version_current_and_keeps_original() -> None:
    """翻译：平台返回版本一致（`items=None`）时跳过该批，未命中项回退字符串化 id。"""
    client = _Client(ConcurrentStableList([{"version": 1, "items": None, "total": 0}]))
    translator = HttpDictTranslator(client=client)
    mapping = await translator.translate(DictTranslateQuery(data_source_key="status", ids=ConcurrentStableList((7, 8))))
    assert dict(mapping) == {7: "7", 8: "8"}


async def test_non_mapping_response_body_degrades() -> None:
    """响应体非 JSON 对象（如数组）→ 视为非法，降级为空结果。"""

    class _ListBodyClient(BaseServiceClient):
        """伪客户端：固定回 JSON 数组响应体。"""

        async def call(self, request: ServiceRequest) -> ServiceResponse:
            """回数组响应体。

            Args:
                request: 调用请求（忽略）。

            Returns:
                ServiceResponse: 200 + JSON 数组体。
            """
            return ServiceResponse(status_code=200, content=b"[]")

    result = await HttpDataSource(client=cast("Any", _ListBodyClient())).by_type(DictQuery(data_source_key="status"))
    assert result.items == ()
    assert result.version == 0


async def test_translate_with_empty_cache_ignores_unrequested_items() -> None:
    """翻译：缓存存在但未命中（不回跳），且平台返回的未请求 id 被忽略。"""
    cache = MemoryDictCacheRegion()
    client = _Client(
        ConcurrentStableList(
            [
                {
                    "version": 1,
                    "items": [
                        {"id": 1, "value": "x", "label": "X", "code": "x", "sort": 0},
                        {"id": 99, "value": "extra", "label": "多余", "code": "extra", "sort": 1},
                    ],
                    "total": 2,
                }
            ]
        )
    )
    translator = HttpDictTranslator(client=client, cache=cache)
    mapping = await translator.translate(DictTranslateQuery(data_source_key="status", ids=ConcurrentStableList((1,))))

    assert dict(mapping) == {1: "X"}
    assert 99 not in mapping


def test_chunks_edge_cases() -> None:
    """`_chunks`：非法批大小与空序列返回空清单；正常按批切分。"""
    assert _chunks(ConcurrentStableList(), 2) == []
    assert _chunks(ConcurrentStableList([1]), 0) == []

    chunks = _chunks(ConcurrentStableList([1, 2, 3]), 2)
    assert [list(chunk) for chunk in chunks] == [[1, 2], [3]]
    assert cast("Any", chunks) is not None
