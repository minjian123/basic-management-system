"""配额只读回显（07D 需求 02-3）：声明校验、四态判定与只读装载。

覆盖详细设计 §4.5 用例 1~8、14（端点面另见 `services/platform/tests/api/test_tenant_quotas.py`）：
- `kind = quota` 的声明校验（路径 / 维度 / 单位 / 周期 / 软硬限 / 来源 / 取数实现归属）；
- 四态 `ok` / `default` / `unavailable` / `exceeded`；
- 产品不可达 / 非 2xx / 结构非法 → 整源 `unavailable` 且 `usage is None`；
- 未知维度忽略；平台侧无写入（不落库、不建表）。
"""

from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.datasource.registry import (
    QUOTA_PERIODS,
    QUOTA_UNITS,
    DataSourceKind,
    DataSourceRecord,
    DataSourceRegistry,
)
from bms_core.quota import QuotaProjectionReader, QuotaProjectionState, judge_quota_state
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse

pytestmark = pytest.mark.kiwi_id(2450)


def _record(
    *,
    key: str = "demo_tenant_usage",
    path: str | None = "/api/v1/demo/tenant-usage",
    dimensions: ConcurrentStableFrozenList[str] | None = None,
    unit: str | None = "count",
    period: str | None = "day",
    soft: int | None = 80,
    hard: int | None = 100,
    origin: str = "product",
    data_source: str = "demo.demo.tenant_usage",
) -> DataSourceRecord:
    """构造配额投影声明。

    Args:
        key: 数据源键。
        path: 取数路径。
        dimensions: 维度键。
        unit: 单位。
        period: 周期。
        soft: 软限。
        hard: 硬限。
        origin: 来源。
        data_source: 取数实现标识。

    Returns:
        DataSourceRecord: 声明记录。
    """
    return DataSourceRecord(
        data_source_key=key,
        name="演示用量",
        data_source=data_source,
        kind=DataSourceKind.QUOTA.value,
        origin=origin,
        product_key="demo",
        path=path,
        quota_dimensions=(
            ConcurrentStableFrozenList(("topic_count", "storage_bytes")) if dimensions is None else dimensions
        ),
        quota_unit=unit,
        quota_period=period,
        quota_soft_limit=soft,
        quota_hard_limit=hard,
    )


def _issues(*records: DataSourceRecord) -> ConcurrentStableList[str]:
    """跑数据源清单校验。

    Args:
        *records: 声明记录。

    Returns:
        ConcurrentStableList[str]: 问题列表。
    """
    return DataSourceRegistry(ConcurrentStableList(records)).validate()


def test_valid_quota_declaration_passes() -> None:
    """合法声明零问题。"""
    assert list(_issues(_record())) == []


def test_path_must_be_internal_public_api() -> None:
    """取数路径须为内部公开契约完整路径。"""
    issues = _issues(_record(path="/tenant-usage"))
    assert any("内部公开契约完整路径" in item for item in issues)


def test_dimensions_required_and_unique() -> None:
    """维度须非空且不重复、形态合法。"""
    assert any("配额维度缺失" in item for item in _issues(_record(dimensions=ConcurrentStableFrozenList())))
    assert any("配额维度键重复" in item for item in _issues(_record(dimensions=ConcurrentStableFrozenList(("a", "a")))))
    assert any(
        "配额维度键格式非法" in item
        for item in _issues(_record(dimensions=ConcurrentStableFrozenList(("Topic Count",))))
    )


def test_unit_and_period_must_be_known() -> None:
    """单位 / 周期取值须在集合内。"""
    assert any("配额单位取值非法" in item for item in _issues(_record(unit="kg")))
    assert any("配额周期取值非法" in item for item in _issues(_record(period="week")))
    assert "count" in QUOTA_UNITS and "day" in QUOTA_PERIODS


def test_soft_limit_must_not_exceed_hard() -> None:
    """软限不得大于硬限。"""
    assert any("软限不得大于硬限" in item for item in _issues(_record(soft=200, hard=100)))
    assert any("软限不得为负" in item for item in _issues(_record(soft=-1)))


def test_platform_origin_rejected() -> None:
    """平台不得给自己登记产品配额投影。"""
    assert any("配额投影须由产品声明" in item for item in _issues(_record(origin="platform")))


def test_data_source_prefix_must_be_product() -> None:
    """取数实现首段须为声明方产品键。"""
    assert any("首段须为声明方产品键" in item for item in _issues(_record(data_source="other.domain.table")))


@pytest.mark.parametrize(
    ("provided", "usage", "hard", "expected"),
    [
        (True, 10, 100, QuotaProjectionState.OK),
        (False, None, 100, QuotaProjectionState.DEFAULT),
        (True, None, 100, QuotaProjectionState.UNAVAILABLE),
        (True, 100, 100, QuotaProjectionState.EXCEEDED),
        (True, 100, None, QuotaProjectionState.OK),
    ],
)
def test_judge_state(
    provided: bool,
    usage: int | None,
    hard: int | None,
    expected: QuotaProjectionState,
) -> None:
    """四态判定（含「无硬限永不超限」与「无用量值即不可用」）。"""
    assert judge_quota_state(provided=provided, usage=usage, hard_limit=hard) == expected


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


def _response(payload: object, *, status: int = 200) -> ServiceResponse:
    """构造响应。

    Args:
        payload: JSON 载荷。
        status: 状态码。

    Returns:
        ServiceResponse: 响应。
    """
    return ServiceResponse(status_code=status, content=json.dumps(payload).encode())


async def test_reader_maps_ok_and_default() -> None:
    """有值维度 `ok`、缺失维度 `default`（`usage is None`，不用 0 冒充）。"""
    payload = {
        "items": [
            {"quota_key": "topic_count", "usage": 3, "limit": 10, "updated_at": "2026-11-07T10:00:00Z"},
        ]
    }
    reader = QuotaProjectionReader(lambda: _StubClient(_response(payload)))
    items = await reader.read(ConcurrentStableList((_record(),)), tenant_id=1)
    by_key = {item.quota_key: item for item in items}
    assert by_key["topic_count"].state == QuotaProjectionState.OK
    assert by_key["topic_count"].usage == 3
    assert by_key["storage_bytes"].state == QuotaProjectionState.DEFAULT
    assert by_key["storage_bytes"].usage is None


async def test_reader_takes_soft_and_hard_limit_from_product() -> None:
    """产品给出软 / 硬限：以产品值为准，不回落声明值。"""
    payload = {"items": [{"quota_key": "topic_count", "usage": 2, "soft_limit": 5, "hard_limit": 8}]}
    reader = QuotaProjectionReader(lambda: _StubClient(_response(payload)))
    items = await reader.read(ConcurrentStableList((_record(),)), tenant_id=1)
    by_key = {item.quota_key: item for item in items}
    assert (by_key["topic_count"].soft_limit, by_key["topic_count"].hard_limit) == (5, 8)


async def test_reader_marks_exceeded() -> None:
    """用量达到硬限 → `exceeded`。"""
    payload = {"items": [{"quota_key": "topic_count", "usage": 100}]}
    reader = QuotaProjectionReader(lambda: _StubClient(_response(payload)))
    items = await reader.read(ConcurrentStableList((_record(),)), tenant_id=1)
    assert items[0].state == QuotaProjectionState.EXCEEDED


async def test_reader_unavailable_on_call_failure() -> None:
    """下游不可达 → 整源 `unavailable`（不抛出、不返回旧值）。"""
    reader = QuotaProjectionReader(lambda: _StubClient(RuntimeError("boom")))
    items = await reader.read(ConcurrentStableList((_record(),)), tenant_id=1)
    assert [item.state for item in items] == [QuotaProjectionState.UNAVAILABLE] * 2
    assert all(item.usage is None for item in items)


async def test_reader_unavailable_on_bad_status() -> None:
    """非 2xx → 整源 `unavailable`。"""
    reader = QuotaProjectionReader(lambda: _StubClient(_response({"items": []}, status=503)))
    items = await reader.read(ConcurrentStableList((_record(),)), tenant_id=1)
    assert all(item.state == QuotaProjectionState.UNAVAILABLE for item in items)


async def test_reader_unavailable_on_invalid_payload() -> None:
    """结构非法 → 整源 `unavailable`（不猜、不部分采信）。"""
    reader = QuotaProjectionReader(lambda: _StubClient(_response({"items": "not-a-list"})))
    items = await reader.read(ConcurrentStableList((_record(),)), tenant_id=1)
    assert all(item.state == QuotaProjectionState.UNAVAILABLE for item in items)


async def test_reader_ignores_unknown_dimension() -> None:
    """未声明维度忽略（白名单制）。"""
    payload = {"items": [{"quota_key": "unknown_dim", "usage": 1}, {"quota_key": "topic_count", "usage": 2}]}
    reader = QuotaProjectionReader(lambda: _StubClient(_response(payload)))
    items = await reader.read(ConcurrentStableList((_record(),)), tenant_id=1)
    assert {item.quota_key for item in items} == {"topic_count", "storage_bytes"}


async def test_reader_does_not_write_platform_tables() -> None:
    """不双写：取数后平台侧不产生任何记录（只读装载，用完即丢）。"""
    payload = {"items": [{"quota_key": "topic_count", "usage": 1}]}
    reader = QuotaProjectionReader(lambda: _StubClient(_response(payload)))
    items = await reader.read(ConcurrentStableList((_record(),)), tenant_id=1)
    assert isinstance(items[0].model_dump(), Mapping)


def test_hard_limit_must_not_be_negative() -> None:
    """硬限为负即拒。"""
    assert any("配额硬限不得为负" in item for item in _issues(_record(hard=-1, soft=None)))


async def test_reader_rejects_non_mapping_payload() -> None:
    """响应体不是对象 → 整源 `unavailable`。"""
    reader = QuotaProjectionReader(lambda: _StubClient(_response("oops")))
    items = await reader.read(ConcurrentStableList((_record(),)), tenant_id=1)
    assert all(item.state == QuotaProjectionState.UNAVAILABLE for item in items)


async def test_reader_rejects_non_mapping_item() -> None:
    """条目不是对象 → 整源 `unavailable`（不部分采信）。"""
    reader = QuotaProjectionReader(lambda: _StubClient(_response({"items": ["oops"]})))
    items = await reader.read(ConcurrentStableList((_record(),)), tenant_id=1)
    assert all(item.state == QuotaProjectionState.UNAVAILABLE for item in items)


async def test_reader_coerces_numeric_strings_and_floats() -> None:
    """用量接受数字字符串与浮点（宽松取整），布尔视为缺失。"""
    payload = {
        "items": [
            {"quota_key": "topic_count", "usage": "7", "limit": 10.0},
            {"quota_key": "storage_bytes", "usage": 12.9},
        ]
    }
    reader = QuotaProjectionReader(lambda: _StubClient(_response(payload)))
    items = await reader.read(ConcurrentStableList((_record(),)), tenant_id=1)
    by_key = {item.quota_key: item for item in items}
    assert by_key["topic_count"].usage == 7
    assert by_key["topic_count"].limit == 10
    assert by_key["storage_bytes"].usage == 12


async def test_reader_tolerates_bad_and_datetime_updated_at() -> None:
    """`updated_at` 非法字符串 ⇒ `None`；`datetime` 实例原样保留。"""
    from datetime import UTC, datetime

    from bms_core.quota import reader as reader_module

    assert reader_module._as_datetime("not-a-date") is None  # pyright: ignore[reportPrivateUsage]
    moment = datetime(2026, 11, 7, tzinfo=UTC)
    assert reader_module._as_datetime(moment) is moment  # pyright: ignore[reportPrivateUsage]
    payload = {"items": [{"quota_key": "topic_count", "usage": 1, "updated_at": "bad"}]}
    reader = QuotaProjectionReader(lambda: _StubClient(_response(payload)))
    items = await reader.read(ConcurrentStableList((_record(),)), tenant_id=1)
    assert items[0].updated_at is None


async def test_reader_empty_resource_key_becomes_none() -> None:
    """资源标识空串归一为 `None`（不落空串）。"""
    payload = {"items": [{"quota_key": "topic_count", "usage": 1, "resource_key": ""}]}
    reader = QuotaProjectionReader(lambda: _StubClient(_response(payload)))
    items = await reader.read(ConcurrentStableList((_record(),)), tenant_id=1)
    assert items[0].resource_key is None


async def test_reader_non_numeric_usage_is_unavailable() -> None:
    """用量为非数值（对象 / 布尔）⇒ 视为无值 → `unavailable`。"""
    payload = {"items": [{"quota_key": "topic_count", "usage": {"bad": 1}}]}
    reader = QuotaProjectionReader(lambda: _StubClient(_response(payload)))
    items = await reader.read(ConcurrentStableList((_record(),)), tenant_id=1)
    assert items[0].state == QuotaProjectionState.UNAVAILABLE
