"""成员端点帧形态（03-6-2；Kiwi 2514）：客户端侧请求形态与结果还原。

覆盖：加入 / 成员心跳 / 离开的请求帧类型与路径、payload 段为空、结果九键还原、
错误码在两通道得到同一分类（帧 / JSON 判定等价）。
"""

from __future__ import annotations

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict
from bms_core.msgclient.errors import ErrorCategory
from bms_core.msgclient.frame import FRAME_CONTENT_TYPE, FrameType, decode_frames
from bms_core.msgclient.messaging import ClientAction, MsgClientError, TransportChannel
from bms_core.msgclient.messaging.codes import rule_for_consume
from bms_core.msgclient.messaging.transport import ApiRequest

from ._support import DEFAULT_ENDPOINT, ScriptedServer, build_config, build_consumer, build_transport
from ._support import channel as channel  # 夹具出口（用例按名字注入）

pytestmark = pytest.mark.kiwi_id(2514)

_ASSIGNMENT = {
    "group": "g1",
    "topic": "orders",
    "consumer_id": "c1",
    "generation": 3,
    "state": "stable",
    "partitions": [0, 2],
    "member_count": 1,
    "heartbeat_interval_ms": 10_000,
    "session_timeout_ms": 30_000,
}
"""加入 / 心跳的脚本化分配（与服务端帧头九键同名）。"""

_LEAVE = {"group": "g1", "topic": "orders", "consumer_id": "c1", "generation": 4, "state": "empty"}
"""离开的脚本化结果（五项）。"""


def _request_frame(server: ScriptedServer, index: int) -> tuple[int, ConcurrentStableDict[str, object]]:
    """取第 `index` 个请求的帧类型与帧头。

    Args:
        server: 假服务端。
        index: 请求序号。

    Returns:
        tuple[int, ConcurrentStableDict[str, object]]: （帧类型，帧头）。
    """
    frame = decode_frames(server.requests[index].content).frames[0]
    return frame.frame_type, ConcurrentStableDict(frame.header)


@pytest.mark.asyncio
async def test_join_requests_use_join_frame_type() -> None:
    """加入：帧类型 7、路径 `/msg/join`、payload 段为空、帧头带 request_id 与成员四字段。"""
    server = ScriptedServer()
    server.push("/msg/join", data=_ASSIGNMENT)
    server.push("/msg/leave", data=_LEAVE)
    consumer, _ = build_consumer(build_config(), server)

    await consumer.join()
    request = server.requests[0]
    frame_type, header = _request_frame(server, 0)
    assert request.headers["content-type"].startswith(FRAME_CONTENT_TYPE)
    assert request.url.path == "/msg/join"
    assert frame_type == int(FrameType.JOIN)
    assert isinstance(header["request_id"], str) and header["request_id"]
    assert header["consumer_id"] == "c1"
    assert decode_frames(request.content).frames[0].payload == b""
    await consumer.close()


@pytest.mark.asyncio
async def test_join_restores_assignment_fields() -> None:
    """加入结果：帧头九键还原成 `Assignment`（含分区列表与心跳间隔）。"""
    server = ScriptedServer()
    server.push("/msg/join", data=_ASSIGNMENT)
    server.push("/msg/leave", data=_LEAVE)
    consumer, _ = build_consumer(build_config(), server)

    assignment = await consumer.join()
    assert assignment.group == "g1"
    assert assignment.consumer_id == "c1"
    assert assignment.generation == 3
    assert assignment.state == "stable"
    assert list(assignment.partitions) == [0, 2]
    assert assignment.member_count == 1
    assert assignment.heartbeat_interval_ms == 10_000
    await consumer.close()


@pytest.mark.asyncio
async def test_heartbeat_uses_member_heartbeat_frame_type() -> None:
    """成员心跳：帧类型 9（**不是**连接心跳 17），路径 `/msg/heartbeat`。"""
    server = ScriptedServer()
    server.push("/msg/join", data=_ASSIGNMENT)
    server.push("/msg/heartbeat", data=_ASSIGNMENT)
    server.push("/msg/leave", data=_LEAVE)
    consumer, stats = build_consumer(build_config(), server)

    await consumer.join()
    assignment = await consumer.heartbeat()
    frame_type, _ = _request_frame(server, 1)
    assert server.requests[1].url.path == "/msg/heartbeat"
    assert frame_type == int(FrameType.MEMBER_HEARTBEAT)
    assert assignment.generation == 3
    assert stats.snapshot()["heartbeat_total"] == 1
    await consumer.close()


@pytest.mark.asyncio
async def test_leave_uses_leave_frame_type() -> None:
    """离开：帧类型 8，路径 `/msg/leave`；客户端不读离开结果（进程退出路径不因组已不存在而抛错）。"""
    server = ScriptedServer()
    server.push("/msg/join", data=_ASSIGNMENT)
    server.push("/msg/leave", data=_LEAVE)
    consumer, _ = build_consumer(build_config(), server)

    await consumer.join()
    await consumer.close()
    frame_type, header = _request_frame(server, 1)
    assert server.requests[1].url.path == "/msg/leave"
    assert frame_type == int(FrameType.LEAVE)
    assert header["consumer_id"] == "c1"


@pytest.mark.asyncio
async def test_member_error_code_maps_identically_in_both_channels(channel: TransportChannel) -> None:
    """成员失效 350014：两条通道都拿到同一码，分类与动作一律由本地码表给（不读帧里的 category）。"""
    server = ScriptedServer()
    server.push("/msg/heartbeat", code=350014, message="成员已失效")
    transport = build_transport(build_config(channel=channel), server)
    request = ApiRequest(
        frame_type=int(FrameType.MEMBER_HEARTBEAT),
        path="/msg/heartbeat",
        fields=ConcurrentStableFrozenDict({"group": "g1", "namespace": "ns", "topic": "orders", "consumer_id": "c1"}),
    )
    outcome = await transport.post(DEFAULT_ENDPOINT, request)
    assert outcome.code == 350014
    assert outcome.message == "成员已失效"
    rule = rule_for_consume(outcome.code)
    assert rule.category is ErrorCategory.BUSINESS_REJECT
    assert rule.action is ClientAction.REFRESH


@pytest.mark.asyncio
async def test_consumer_heartbeat_raises_refresh_action() -> None:
    """消费端心跳收到 350014：抛 `MsgClientError`，动作是「刷新分配」（与 JSON 通道同一判定）。"""
    server = ScriptedServer()
    server.push("/msg/heartbeat", code=350014, message="成员已失效")
    consumer, _ = build_consumer(build_config(), server)

    with pytest.raises(MsgClientError) as raised:
        await consumer.heartbeat()
    assert raised.value.code == 350014
    assert raised.value.action is ClientAction.REFRESH
    await consumer.transport.close()
