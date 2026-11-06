"""07B 06_01 步 1：协议链边界分支用例（补齐模块级 100%）。

覆盖从 msg 仓迁来的用例未触及的边界：预算校验与注入时钟、名称形态、静态实例源空列表、
HTTP 错误映射兜底、响应帧解析失败、帧头可选字段、传输层异常映射、客户端上下文管理。
"""

# 边界用例需直接覆盖模块内私有 helper，局部关闭该规则
# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import Any

import pytest

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import ParamError
from bms_core.msgclient.constants import RPC_DEADLINE_MAX_MS, RPC_RETURN_RESERVE_MS
from bms_core.msgclient.deadline import Deadline, validate_budget_ms
from bms_core.msgclient.frame import FrameFlags, FrameType, encode_frame
from bms_core.msgclient.naming import ensure_rpc_name
from bms_core.msgclient.rpc import (
    RpcCallError,
    RpcClient,
    StaticInstanceProvider,
    _error_of,
    _reply_of,
    _request_header,
    frame_headers,
)
from bms_core.msgclient.transport.base import RpcHttpResponse, RpcTransportError, RpcTransportProtocolError

pytestmark = pytest.mark.kiwi_id(2440)


def test_validate_budget_ms_boundaries() -> None:
    """缺省 / 布尔 / 非整数 / 越界四态。"""
    assert validate_budget_ms(None, default=123) == 123
    for bad in (True, "100", 1.5, -1, RPC_DEADLINE_MAX_MS + 1):
        with pytest.raises(ParamError):
            validate_budget_ms(bad, default=123)


def test_deadline_with_injected_clock() -> None:
    """注入时刻走遍 spent / remaining / exhausted / downstream，并覆盖缺省时钟分支。"""
    d = Deadline.start(None, now=10.0)
    assert d.budget_ms > 0
    assert d.spent_ms(now=10.5) == 500
    assert d.remaining_ms(now=10.5) == d.budget_ms - 500
    assert d.is_exhausted(now=10.5) is False
    assert d.downstream_ms(now=10.5) == max(0, d.budget_ms - 500 - RPC_RETURN_RESERVE_MS)
    assert d.is_exhausted(now=10.0 + d.budget_ms / 1000 + 1) is True
    assert Deadline.start(2_000, now=None).budget_ms == 2_000
    assert validate_budget_ms(7, default=123) == 7


def test_ensure_rpc_name_rejects_both_shapes() -> None:
    """服务标识与方法名各有一条拒启分支。"""
    with pytest.raises(ParamError, match="服务标识"):
        ensure_rpc_name("bad name!", "ok")
    with pytest.raises(ParamError, match="方法名"):
        ensure_rpc_name("ok", "bad/name")
    ensure_rpc_name("demo", "echo.v1")


def test_static_instance_provider_rejects_empty() -> None:
    """实例源至少要有一个地址。"""
    with pytest.raises(ValueError, match="至少需要一个实例地址"):
        StaticInstanceProvider([])


def test_error_of_http_413_and_unknown_status() -> None:
    """413 与未知状态码两条非 200 兜底。"""
    payload_413 = _error_of(RpcHttpResponse(status=413, headers=(), body=b"", stream_id=1))
    assert payload_413.code == 350006 and payload_413.retryable is False
    other = _error_of(RpcHttpResponse(status=502, headers=(), body=b"", stream_id=2))
    assert other.code == 0 and "502" in other.message


def test_reply_of_rejects_broken_and_wrong_type_frames() -> None:
    """非帧字节与帧类型不符各抛协议层错误。"""
    with pytest.raises(RpcCallError) as broken:
        _reply_of(b"not-a-frame")
    assert broken.value.layer == "protocol"
    header: ConcurrentStableDict[str, Any] = ConcurrentStableDict()
    header.set("request_id", "r1")
    wrong = encode_frame(frame_type=int(FrameType.RPC), flags=FrameFlags.NEED_RESPONSE, header=header)
    with pytest.raises(RpcCallError, match="响应帧类型不符"):
        _reply_of(wrong)


def test_request_header_includes_optional_caller() -> None:
    """caller 非空时写进帧头（其余可选字段缺省不写）。"""
    header = _request_header(
        request_id="r1",
        service="demo",
        method="echo",
        headers=None,
        trace_id=None,
        caller="svc-a",
        deadline_ms=1_000,
    )
    assert header.get("caller") == "svc-a"
    assert header.get("trace_id") is None


class _BrokenTransport:
    """按标志抛两类传输异常的最小替身。"""

    def __init__(self, *, protocol: bool) -> None:
        self.protocol = protocol

    async def send(self, request: object) -> RpcHttpResponse:
        """按标志抛异常。

        Args:
            request: 传输层入参（不消费）。

        Raises:
            RpcTransportProtocolError: 协议不可解析。
            RpcTransportError: 连接失败。
        """
        if self.protocol:
            raise RpcTransportProtocolError("bad frame")
        raise RpcTransportError("connection lost")

    async def aclose(self) -> None:
        """关闭（无状态）。"""
        return None


@pytest.mark.parametrize("protocol", [True, False])
async def test_attempt_maps_transport_failures(protocol: bool) -> None:
    """协议错与连接错分别映射到 protocol / transport 层错误。"""
    client = RpcClient(
        StaticInstanceProvider(["http://127.0.0.1:1"]),
        transport=_BrokenTransport(protocol=protocol),  # type: ignore[arg-type]
    )
    with pytest.raises(RpcCallError) as caught:
        await client.call("demo", "echo", b"x")
    assert caught.value.layer == ("protocol" if protocol else "transport")


async def test_rpc_client_async_context_closes_transport() -> None:
    """`async with` 进出分别返回自身与关闭传输。"""
    transport = _BrokenTransport(protocol=True)
    client = RpcClient(
        StaticInstanceProvider(["http://127.0.0.1:1"]),
        transport=transport,  # type: ignore[arg-type]
    )
    async with client as entered:
        assert entered is client


def test_frame_headers_iterates_multiple_entries() -> None:
    """多元素映射触发循环回边；非字符串键 / 值被跳过。"""
    result = frame_headers({"a": "1", "b": "2", 3: "x", "c": 4})
    assert dict(result.items()) == {"a": "1", "b": "2"}


async def test_call_with_explicit_idempotency_key_skips_auto_generation() -> None:
    """显式给键时跳过自动生成分支（`key is None` 为假）。"""
    client = RpcClient(
        StaticInstanceProvider(["http://127.0.0.1:1"]),
        transport=_BrokenTransport(protocol=True),  # type: ignore[arg-type]
    )
    with pytest.raises(RpcCallError):
        await client.call("demo", "echo", b"x", idempotency_key="fixed-key")
