"""03-6 / 03-6-1 用例：传输层公共语义（Kiwi 2510；两条通道参数化各跑一遍）。

覆盖要点：请求头三段来源（租户 / 自定义 / 鉴权，后者覆盖前者）；三类传输异常的分工
（未发出 → 可重试、已发出无结果 → 结果未知、其余 → 结果未知兜底）；建议重试间隔的两个来源之一
（HTTP `Retry-After`，两通道都认）；关闭幂等；结果对象的空缺省。

**通道专属细节分开写**：JSON 的请求体 / `data.retry_after_ms` 回落见 `test_transport_json.py`；
帧的编解码 / 切片 / 兜底见 `test_transport_frame.py`。
"""

from __future__ import annotations

import httpx
import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict
from bms_core.msgclient.errors import ErrorCategory
from bms_core.msgclient.frame import FrameType
from bms_core.msgclient.messaging import (
    ApiOutcome,
    ApiRequest,
    ClientAction,
    MessagingConfig,
    MsgClientError,
    TransportChannel,
)
from bms_core.msgclient.messaging.transport import MessagingTransport
from bms_core.msgclient.retry import Clock

from ._support import DEFAULT_ENDPOINT, ScriptedServer, build_config, build_transport
from ._support import channel as channel  # 夹具出口（用例按名字注入）

pytestmark = pytest.mark.kiwi_id(2510)


def _config(channel: TransportChannel, *, clock: Clock | None = None, **overrides: object) -> MessagingConfig:
    """构造指定通道的配置。

    Args:
        channel: 通道。
        clock: 注入时钟（缺省用 fake）。
        overrides: 覆盖字段。

    Returns:
        MessagingConfig: 配置。
    """
    return build_config(channel=channel, clock=clock, **overrides)


def _request(path: str = "/msg/publish", *, payload: bytes = b"hi") -> ApiRequest:
    """构造一条最小发布请求（两通道都能发）。

    Args:
        path: 端点路径。
        payload: 消息体。

    Returns:
        ApiRequest: 请求。
    """
    return ApiRequest(
        frame_type=1,
        path=path,
        fields=ConcurrentStableFrozenDict({"namespace": "ns", "topic": "orders"}),
        payload=payload,
    )


def test_headers_tenant_only(channel: TransportChannel) -> None:
    """无自定义头、无鉴权：只带租户头。"""
    transport = build_transport(_config(channel), ScriptedServer())
    headers = transport.headers()
    assert headers.get("X-Tenant-ID") == "t1"
    assert headers.get("Authorization") is None


def test_headers_merge_and_auth_wins(channel: TransportChannel) -> None:
    """自定义头与鉴权都注入；同名键以鉴权为准（避免自定义头把令牌覆盖成脏值）。"""
    config = _config(
        channel,
        headers_provider=lambda: ConcurrentStableDict({"X-Trace": "abc", "Authorization": "custom"}),
        auth_provider=lambda: "Bearer t",
    )
    headers = build_transport(config, ScriptedServer()).headers()
    assert headers.get("X-Trace") == "abc"
    assert headers.get("Authorization") == "Bearer t"


@pytest.mark.asyncio
async def test_post_reads_retry_after_header(channel: TransportChannel) -> None:
    """`Retry-After`（秒）转毫秒：两通道都认这个 HTTP 头（网关限流时是唯一的提示来源）。"""
    server = ScriptedServer()
    server.push(
        "/msg/publish",
        code=350005,
        headers=ConcurrentStableFrozenDict({"Retry-After": "2"}),
    )
    outcome = await build_transport(_config(channel), server).post(DEFAULT_ENDPOINT, _request())
    assert outcome.code == 350005
    assert outcome.retry_after_ms == 2_000
    assert server.requests[0].headers["X-Tenant-ID"] == "t1"


@pytest.mark.asyncio
async def test_post_has_no_retry_hint(channel: TransportChannel) -> None:
    """两个来源都没有：`retry_after_ms` 为 None。"""
    server = ScriptedServer()
    server.push("/msg/publish", data={"message_id": "m1"})
    outcome = await build_transport(_config(channel), server).post(DEFAULT_ENDPOINT, _request())
    assert outcome.code == 0
    assert outcome.retry_after_ms is None


@pytest.mark.asyncio
async def test_connect_failure_is_retryable_and_not_sent(channel: TransportChannel) -> None:
    """建连失败：请求未发出 → `transient` / 可重试，且不标结果未知。"""
    server = ScriptedServer()
    server.push("/msg/publish", error=httpx.ConnectError("拒绝连接"))
    transport = build_transport(_config(channel), server)
    with pytest.raises(MsgClientError) as captured:
        await transport.post(DEFAULT_ENDPOINT, _request())
    error = captured.value
    assert error.code == 0
    assert error.category is ErrorCategory.TRANSIENT
    assert error.action is ClientAction.RETRY
    assert error.outcome_unknown is False


@pytest.mark.asyncio
async def test_read_timeout_is_unknown(channel: TransportChannel) -> None:
    """读超时：已发出但没拿到结果 → 标结果未知（重试可能重复）。"""
    server = ScriptedServer()
    server.push("/msg/publish", error=httpx.ReadTimeout("超时"))
    transport = build_transport(_config(channel), server)
    with pytest.raises(MsgClientError) as captured:
        await transport.post(DEFAULT_ENDPOINT, _request())
    assert captured.value.category is ErrorCategory.UNKNOWN
    assert captured.value.outcome_unknown is True


@pytest.mark.asyncio
async def test_other_transport_error_is_unknown_and_fatal(channel: TransportChannel) -> None:
    """其余传输异常：无法判定是否已发出 → 按结果未知兜底，且不自动重试。"""
    server = ScriptedServer()
    server.push("/msg/publish", error=httpx.DecodingError("坏响应"))
    transport = build_transport(_config(channel), server)
    with pytest.raises(MsgClientError) as captured:
        await transport.post(DEFAULT_ENDPOINT, _request())
    assert captured.value.action is ClientAction.FATAL
    assert captured.value.outcome_unknown is True


@pytest.mark.asyncio
async def test_close_is_idempotent(channel: TransportChannel) -> None:
    """关闭可重复调用（进程退出路径不该因为重复关而抛）。"""
    transport: MessagingTransport = build_transport(_config(channel), ScriptedServer())
    await transport.close()
    await transport.close()


def test_api_outcome_defaults() -> None:
    """传输结果对象不传 `data` 时是空映射、不传切片时是空列表（调用方不必判 None）。"""
    outcome = ApiOutcome(code=0)
    assert outcome.data == ConcurrentStableFrozenDict[str, object]()
    assert outcome.message == ""
    assert outcome.retry_after_ms is None
    assert len(outcome.payload_segments) == 0


def test_api_request_defaults() -> None:
    """请求对象不传业务字段时是空映射、消息体为空字节。"""
    request = ApiRequest(frame_type=int(FrameType.JOIN), path="/msg/join")
    assert request.fields == ConcurrentStableFrozenDict[str, object]()
    assert request.payload == b""
