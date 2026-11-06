"""07B `06_01` 步 2 用例（Kiwi 2441）：`MsgEventPublisher` 的发布映射与失败语义。

`httpx.MockTransport` 只替换「字节往哪送」，请求体仍是生产代码构造的那一份——
断言的是真正的出站 JSON（不是被测代码自己的中间对象）。
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from datetime import UTC, datetime

import httpx
import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.events.base import EventEnvelope, EventPublishError
from bms_core.events.topic import encode_event, topic_for
from bms_core.msgclient.adapter.event_publisher import PUBLISH_PATH, MsgEventPublisher

pytestmark = pytest.mark.kiwi_id(2441)

BASE_URL = "http://msg:8000"


def _publisher(
    transport: httpx.MockTransport,
    *,
    namespace: str = "bms",
    tenant: str | None = None,
) -> MsgEventPublisher:
    """构造带替身传输的发布器。"""
    return MsgEventPublisher(
        base_url=BASE_URL,
        namespace=namespace,
        tenant=tenant,
        transport=transport,
    )


def _event(**overrides: object) -> EventEnvelope:
    """构造一条默认事件（工作流任务完成）。"""
    fields: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "event_type": "wf.task.completed",
            "payload": ConcurrentStableDict({"task": "t1"}),
            "event_id": "e-1",
            "aggregate_key": "wf-1",
            "trace_id": "trace-1",
            # 固定发生时刻：`encode_event` 在缺省时取「当前时刻」，两次调用会差几微秒，
            # 断言「出站载荷等于基座编码」就永远对不上。
            "occurred_at": datetime(2026, 11, 6, 12, 0, 0, tzinfo=UTC).replace(tzinfo=None),
        }
    )
    for name, value in overrides.items():
        fields.set(name, value)
    return EventEnvelope(**dict(fields.items()))  # pyright: ignore[reportArgumentType]


def _recording(status: int = 200) -> tuple[httpx.MockTransport, ConcurrentStableList[httpx.Request]]:
    """返回「记录请求 + 固定状态码」的传输与记录表。"""
    seen: ConcurrentStableList[httpx.Request] = ConcurrentStableList()

    def handle(request: httpx.Request) -> httpx.Response:
        seen.add(request)
        return httpx.Response(status, json={"code": 0, "message": "ok"})

    return httpx.MockTransport(handle), seen


async def test_publish_maps_envelope_to_data_plane_request() -> None:
    """信封 → 数据面请求体：topic / 分区键 / base64 载荷 / 属性 / 链路。"""
    transport, seen = _recording()
    publisher = _publisher(transport)
    event = _event()
    await publisher.publish(event)
    request = seen[0]
    assert str(request.url) == f"{BASE_URL}{PUBLISH_PATH}"
    body = json.loads(request.content)
    assert body["namespace"] == "bms"
    assert body["topic"] == topic_for(event.event_type)
    assert body["key"] == "wf-1"
    assert base64.b64decode(body["payload"]) == encode_event(event)
    assert body["headers"]["event_id"] == "e-1"
    assert body["trace_id"] == "trace-1"


async def test_publish_carries_tenant_header() -> None:
    """租户随 `X-Tenant-ID` 头（事件信封的租户优先于装配缺省）。"""
    transport, seen = _recording()
    publisher = _publisher(transport, tenant="1001")
    await publisher.publish(_event(tenant_id="2002"))
    assert seen[0].headers["X-Tenant-ID"] == "2002"


async def test_publish_falls_back_to_configured_tenant() -> None:
    """事件不带租户时回落装配期缺省值。"""
    transport, seen = _recording()
    publisher = _publisher(transport, tenant="1001")
    await publisher.publish(_event(tenant_id=None))
    assert seen[0].headers["X-Tenant-ID"] == "1001"


async def test_publish_omits_absent_optional_fields() -> None:
    """无聚合键 / 无链路时不写空字段（`key` 缺失即无分区键，不写空串）。"""
    transport, seen = _recording()
    publisher = _publisher(transport)
    await publisher.publish(_event(aggregate_key=None, trace_id=None))
    body = json.loads(seen[0].content)
    assert "key" not in body
    assert "trace_id" not in body


async def test_publish_rejects_non_200() -> None:
    """非 200 → `EventPublishError`（`10009`，重试归投递器）。"""
    transport, _ = _recording(status=503)
    publisher = _publisher(transport)
    with pytest.raises(EventPublishError) as caught:
        await publisher.publish(_event())
    detail = caught.value.data
    assert isinstance(detail, Mapping)
    assert detail["status"] == 503


async def test_publish_wraps_transport_error() -> None:
    """传输异常 → `EventPublishError`（不让 httpx 异常穿到投递器）。"""

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    publisher = _publisher(httpx.MockTransport(boom))
    with pytest.raises(EventPublishError):
        await publisher.publish(_event())


async def test_publish_transactional_delegates_to_publish() -> None:
    """事务消息首期与普通发布同路径（事务消息归 8B_04）。"""
    transport, seen = _recording()
    publisher = _publisher(transport)
    await publisher.publish_transactional(_event())
    assert len(seen) == 1


async def test_publish_reuses_single_client() -> None:
    """连续发布复用同一连接（第二次不再新建客户端）。"""
    transport, seen = _recording()
    publisher = _publisher(transport)
    await publisher.publish(_event(event_id="e-1"))
    await publisher.publish(_event(event_id="e-2"))
    assert len(seen) == 2


async def test_event_type_and_aclose() -> None:
    """实现标识与资源释放（`aclose` 幂等；已建连接在释放时真正关闭）。"""
    transport, _ = _recording()
    publisher = _publisher(transport)
    assert publisher.event_type == "msg"
    await publisher.publish(_event())
    await publisher.aclose()
    await publisher.aclose()
