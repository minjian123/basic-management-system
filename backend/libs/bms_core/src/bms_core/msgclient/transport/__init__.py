"""RPC 客户端传输层（任务 04-7-1 / 04-3-2）：协议、值对象、异常、h2 实现与流式出口。

出口只有本模块：`client/rpc.py` 只 import 这里，不认识 `h2`，也不认识 socket。
"""

from __future__ import annotations

from bms_core.msgclient.transport.base import (
    PHASE_AWAIT_HEADERS,
    PHASE_CONNECT,
    PHASE_READ_BODY,
    PHASE_RESET,
    PHASE_SEND,
    PHASE_UNKNOWN,
    RpcHttpRequest,
    RpcHttpResponse,
    RpcRequestTrace,
    RpcTransport,
    RpcTransportClosedError,
    RpcTransportError,
    RpcTransportProtocolError,
    RpcTransportTimeoutError,
    RpcTransportUnsupportedError,
    TransportStats,
    TransportStream,
)
from bms_core.msgclient.transport.pool import H2Transport

__all__ = [
    "PHASE_AWAIT_HEADERS",
    "PHASE_CONNECT",
    "PHASE_READ_BODY",
    "PHASE_RESET",
    "PHASE_SEND",
    "PHASE_UNKNOWN",
    "H2Transport",
    "RpcHttpRequest",
    "RpcHttpResponse",
    "RpcRequestTrace",
    "RpcTransport",
    "RpcTransportClosedError",
    "RpcTransportError",
    "RpcTransportProtocolError",
    "RpcTransportTimeoutError",
    "RpcTransportUnsupportedError",
    "TransportStats",
    "TransportStream",
]
