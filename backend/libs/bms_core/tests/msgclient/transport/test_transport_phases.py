"""04-6 用例之五（Kiwi 2444）：传输层失败阶段（`phase`）与「可能已执行」判定。"""

from __future__ import annotations

import asyncio
import socket

import pytest
from msgclient_support.h2_server import H2TestServer

from bms_core.msgclient.transport import (
    PHASE_AWAIT_HEADERS,
    PHASE_CONNECT,
    PHASE_READ_BODY,
    PHASE_RESET,
    PHASE_SEND,
    PHASE_UNKNOWN,
    H2Transport,
    RpcHttpRequest,
    RpcTransportClosedError,
)
from bms_core.msgclient.transport.connection import H2ClientConnection
from bms_core.msgclient.transport.stream import CLOSE_CANCELLED, H2Stream

pytestmark = pytest.mark.kiwi_id(2444)


class _FakeConnection:
    """只实现 `abort_stream` 的连接替身。"""

    def abort_stream(self, stream_id: int) -> bool:
        """返回「已发 RST」。

        Args:
            stream_id: 流号（未使用）。

        Returns:
            bool: 恒 True。
        """
        del stream_id
        return True


def _stream() -> H2Stream:
    """构造挂在替身连接上的流。

    Returns:
        H2Stream: 流对象。
    """
    from typing import Any, cast

    return H2Stream(cast("Any", _FakeConnection()), 1)


def _request(origin: str, target: str = "/ok", body: bytes = b"") -> RpcHttpRequest:
    """构造传输层请求。

    Args:
        origin: 实例基址。
        target: 请求路径。
        body: 请求体。

    Returns:
        RpcHttpRequest: 传输层请求。
    """
    return RpcHttpRequest(
        origin=origin,
        target=target,
        headers=(("content-type", "application/x-msg-frame"),),
        body=body,
        timeout_ms=5_000,
    )


def _free_port() -> int:
    """取一个本机空闲端口（连它应被拒绝）。

    Returns:
        int: 端口号。
    """
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_connect_and_send_are_definitely_not_sent() -> None:
    """建连 / 发送失败：确定未执行，允许换实例。"""
    assert RpcTransportClosedError("x", phase=PHASE_CONNECT).may_have_been_sent is False
    assert RpcTransportClosedError("x", phase=PHASE_SEND).may_have_been_sent is False


def test_unknown_default_is_conservative() -> None:
    """未标注阶段默认 `unknown`：按可能已执行处理。"""
    error = RpcTransportClosedError("x")
    assert error.phase == PHASE_UNKNOWN
    assert error.may_have_been_sent is True


async def test_reset_before_headers_is_await_headers_phase() -> None:
    """未收响应头即被 reset：`await_headers`（可能已执行）。"""
    stream = _stream()
    stream.on_reset(0)
    with pytest.raises(RpcTransportClosedError) as caught:
        await stream.wait_response()
    assert caught.value.phase == PHASE_AWAIT_HEADERS
    assert caught.value.may_have_been_sent is True


async def test_reset_after_headers_is_read_body_phase() -> None:
    """已收响应头后中断：`read_body`（可能已执行）。"""
    stream = _stream()
    stream.on_headers(200, ())
    stream.on_reset(0)
    with pytest.raises(RpcTransportClosedError) as caught:
        await stream.read_chunk()
    assert caught.value.phase == PHASE_READ_BODY


async def test_connection_error_phase_depends_on_headers() -> None:
    """连接级故障按是否已收头标注 `await_headers` / `read_body`。"""
    before = _stream()
    before.on_connection_error(RpcTransportClosedError("broken"))
    with pytest.raises(RpcTransportClosedError) as caught_before:
        await before.wait_response()
    assert caught_before.value.phase == PHASE_AWAIT_HEADERS

    after = _stream()
    after.on_headers(200, ())
    after.on_connection_error(RpcTransportClosedError("broken"))
    with pytest.raises(RpcTransportClosedError) as caught_after:
        await after.read_chunk()
    assert caught_after.value.phase == PHASE_READ_BODY


async def test_local_abort_is_reset_phase() -> None:
    """本地中止（取消 / 超时）：`reset`，结果未知。"""
    stream = _stream()
    stream.on_headers(200, ())
    assert stream.abort(CLOSE_CANCELLED) is True
    with pytest.raises(RpcTransportClosedError) as caught:
        await stream.read_chunk()
    assert caught.value.phase == PHASE_RESET


async def test_connect_refused_is_connect_phase() -> None:
    """连不上实例：`connect`（确定未执行，可换实例）。"""
    transport = H2Transport()
    try:
        with pytest.raises(RpcTransportClosedError) as caught:
            await transport.send(_request(f"http://127.0.0.1:{_free_port()}"))
    finally:
        await transport.aclose()
    assert caught.value.phase == PHASE_CONNECT


async def test_send_body_success_and_peer_close() -> None:
    """带请求体发送走 `send_request` 全路径；对端关连接落到 `read_body`。"""
    async with H2TestServer() as server:
        transport = H2Transport()
        try:
            response = await transport.send(_request(server.url, "/echo", body=b"hello"))
            assert response.status == 200
            with pytest.raises(RpcTransportClosedError) as caught:
                await transport.send(_request(server.url, "/close"))
        finally:
            await transport.aclose()
    assert caught.value.phase in (PHASE_AWAIT_HEADERS, PHASE_READ_BODY)


async def test_stream_endpoint_non_200_is_await_headers_phase() -> None:
    """流端点非 200：打开阶段失败，`await_headers`。"""
    async with H2TestServer() as server:
        transport = H2Transport()
        try:
            with pytest.raises(RpcTransportClosedError) as caught:
                await transport.open_stream(_request(server.url, "/status/404")).__aenter__()
        finally:
            await transport.aclose()
    assert caught.value.phase == PHASE_AWAIT_HEADERS


async def test_closed_transport_rejects_with_connect_phase() -> None:
    """传输层已关闭：一元与流式都在 `connect` 阶段拒绝。"""
    transport = H2Transport()
    await transport.aclose()
    with pytest.raises(RpcTransportClosedError) as caught_send:
        await transport.send(_request("http://127.0.0.1:1"))
    assert caught_send.value.phase == PHASE_CONNECT
    with pytest.raises(RpcTransportClosedError) as caught_stream:
        await transport.open_stream(_request("http://127.0.0.1:1")).__aenter__()
    assert caught_stream.value.phase == PHASE_CONNECT


async def test_closed_connection_send_request_is_connect_phase() -> None:
    """已关闭的连接拒绝新流：`connect`。"""
    async with H2TestServer() as server:
        reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
        connection = H2ClientConnection(
            origin=server.url,
            authority=f"127.0.0.1:{server.port}",
            scheme="http",
            reader=reader,
            writer=writer,
        )
        await connection.aclose()
        with pytest.raises(RpcTransportClosedError) as caught:
            await connection.send_request(_request(server.url), on_open=lambda _stream: None)
    assert caught.value.phase == PHASE_CONNECT


async def test_send_body_oserror_is_send_phase() -> None:
    """请求体写出失败：`send`（帧未完整提交，可换实例）。"""

    class _BrokenWriter:
        """`drain` 必失败的写端替身。"""

        def write(self, data: bytes) -> None:
            """忽略写入。

            Args:
                data: 字节（未使用）。
            """
            del data

        def close(self) -> None:
            """关闭（无操作）。"""

        async def wait_closed(self) -> None:
            """等待关闭（无操作）。"""

        async def drain(self) -> None:
            """模拟断链。

            Raises:
                OSError: 恒抛。
            """
            raise OSError("broken pipe")

    connection = H2ClientConnection(
        origin="http://test",
        authority="test:80",
        scheme="http",
        reader=None,  # type: ignore[arg-type]
        writer=_BrokenWriter(),  # type: ignore[arg-type]
    )
    connection._h2.initiate_connection()  # pyright: ignore[reportPrivateUsage]
    connection._h2.send_headers(  # pyright: ignore[reportPrivateUsage]
        1,
        [(b":method", b"POST"), (b":authority", b"test"), (b":scheme", b"http"), (b":path", b"/ok")],
    )
    with pytest.raises(RpcTransportClosedError) as caught:
        await connection._send_body(1, b"x")  # pyright: ignore[reportPrivateUsage]
    assert caught.value.phase == PHASE_SEND
