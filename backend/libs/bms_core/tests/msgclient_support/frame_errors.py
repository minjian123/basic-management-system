from __future__ import annotations

from typing import Any

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.msgclient.errors import ErrorCategory
from bms_core.msgclient.frame import (
    PROTOCOL_VERSION,
    FrameFlags,
    FrameType,
    encode_frame,
)
from bms_core.msgclient.values import RpcReply

__all__ = ["classify", "error_frame", "optional_budget", "optional_text", "rpc_stream_frame"]

_RETRYABLE_BUSINESS = frozenset({350005, 350015, 350020, 350021})
"""业务层里「等一会儿再试有意义」的码：限流 / 背压、延迟区已满、连接数 / 单连接流数超限。

`350004`（RPC 预算耗尽）**故意不在其中**：超时是「结果未知」，不得直接重试（需求 04-2 §3.5）；
是否重试由 04-4 按幂等键判定。
"""

_RETRYABLE_SYSTEM = frozenset({10006, 10007, 350022})
"""系统层里可退避重试的码：数据库繁忙、下游服务不可用、**存储水位拒绝**（清理 / 扩容后即可恢复）。"""

_BUSINESS_CODES = frozenset(
    {
        350001,
        350002,
        350003,
        350004,
        350005,
        350006,
        350007,
        350008,
        350009,
        350010,
        350011,
        350012,
        350013,
        350014,
        350015,
        350016,
        350017,
        350020,
        350021,
        350023,
        350024,
    }
)
"""business 层的产品码（其余产品码兜底进 system，宁可少重试也不放大故障）。

`350024`（RPC 流空闲超时）由 04-3-1 加入：它是「这条流没进展」的业务判定，不是传输故障，
故同时不在 `_RETRYABLE_BUSINESS` 里（重开流才有意义，原地重试只会再空等一个阈值）。
"""


def classify(code: int) -> tuple[ErrorCategory, str, bool]:
    """按码判定类别 / 层 / 可重试性（错误帧的 `category` / `layer` / `retryable` 唯一出处）。

    **04-4**：`layer` 与 `retryable` 的既有判定值一字不变，只新增 `category` 一维——已交付的
    03-2 / 04-2 语义不回退。类别与层正交：同一 `transient` 既可能是 business（`350005`），
    也可能是 system（`350022`）。

    Args:
        code: 产品码 / 平台码。

    Returns:
        tuple[ErrorCategory, str, bool]: `(category, layer, retryable)`。
    """
    if code == 350018 or code == 10001:  # 帧格式非法（协议层） / 契约层参数非法
        return ErrorCategory.PARAM_ERROR, "protocol", False
    if code == 350019 or code == 350006:  # 版本不支持 / 帧或消息体超限：连接不可继续按本协议使用
        return ErrorCategory.PARAM_ERROR, "transport", False
    if code == 350004:  # 预算耗尽：结果未知，不是失败
        return ErrorCategory.UNKNOWN, "business", False
    if code in _BUSINESS_CODES:
        layer, retryable = "business", code in _RETRYABLE_BUSINESS
    else:
        layer, retryable = "system", code in _RETRYABLE_SYSTEM
    if retryable:
        return ErrorCategory.TRANSIENT, layer, True
    if layer == "business":
        return ErrorCategory.BUSINESS_REJECT, layer, False
    return ErrorCategory.SERVER_BUG, layer, False


def _result_header(request_id: str | None) -> ConcurrentStableDict[str, Any]:
    """响应帧的公共头（`request_id` 回显 + 版本可见）。

    Args:
        request_id: 请求标识（可空：解码前失败时无此值）。

    Returns:
        ConcurrentStableDict[str, Any]: 头（含公共字段）。
    """
    header: ConcurrentStableDict[str, Any] = ConcurrentStableDict()
    header.set("request_id", request_id)
    header.set("protocol_version", PROTOCOL_VERSION)
    return header


def error_frame(
    *,
    code: int,
    message: str,
    request_id: str | None = None,
    detail: object | None = None,
    retry_after_ms: int | None = None,
) -> bytes:
    """编码错误帧（`type=error` + response 位，payload 为空）。

    Args:
        code: 产品码 / 平台码。
        message: 可读提示。
        request_id: 请求标识（可空）。
        detail: 随附数据（对应 JSON 的 `data`）。
        retry_after_ms: 建议重试间隔（毫秒）。

    Returns:
        bytes: 完整错误帧。
    """
    category, layer, retryable = classify(code)
    header = _result_header(request_id)
    header.set("code", code)
    header.set("message", message)
    header.set("retryable", retryable)
    header.set("layer", layer)
    header.set("category", str(category))
    header.set("detail", detail)
    header.set("retry_after_ms", retry_after_ms)
    return encode_frame(
        frame_type=int(FrameType.ERROR),
        flags=FrameFlags.RESPONSE,
        header=header,
    )


def optional_budget(header: object, key: str) -> int | None:
    """测试替身：从帧头读可选预算（用例只用于构造请求帧，不做服务端校验）。"""
    value = dict(getattr(header, "items", lambda: [])()).get(key)  # type: ignore[attr-defined]
    return int(value) if isinstance(value, int) else None


def optional_text(header: object, key: str) -> str | None:
    """测试替身：从帧头读可选文本。"""
    value = dict(getattr(header, "items", lambda: [])()).get(key)  # type: ignore[attr-defined]
    return str(value) if isinstance(value, str) else None


def rpc_stream_frame(
    *,
    request_id: str,
    service: str,
    method: str,
    reply: RpcReply,
    seq: int,
    used_ms: int,
    remaining_ms: int,
    end_of_stream: bool = False,
) -> bytes:
    """编码流式结果帧（`type=rpc` + response 位；末帧另置 `end_of_stream`）。

    **序号进帧头而不是 payload 前缀**：payload 必须保持「结果原始字节」——04-1 的契约、handler 的
    返回值、压缩与校验的将来接入都依赖这一点；放进 body 前 4 字节等于给 payload 加一层私有头，
    每个消费方都要记住偏移（04-3-1 决策 3）。

    Args:
        request_id: 请求标识（逐帧回显；客户端据此对齐多路流）。
        service: 服务标识（回显）。
        method: 方法名（回显）。
        reply: 本帧结果。
        seq: 帧序号（0 起逐帧 +1）。
        used_ms: 该帧产出时刻的已用毫秒（整条流的预算视图）。
        remaining_ms: 该帧产出时刻的剩余毫秒（夹取到 0）。
        end_of_stream: 是否为该流的末帧（正常结束的唯一标记）。

    Returns:
        bytes: 完整帧字节（header 带 `seq` / `length`）。
    """
    header: ConcurrentStableDict[str, Any] = ConcurrentStableDict()
    header.set("request_id", request_id)
    header.set("protocol_version", PROTOCOL_VERSION)
    header.set("service", service)
    header.set("method", method)
    header.set("seq", seq)
    header.set("length", len(reply.payload))
    header.set("used_ms", used_ms)
    header.set("remaining_ms", remaining_ms)
    header.set("headers", dict(reply.headers.items()))
    flags = FrameFlags.RESPONSE | FrameFlags.END_OF_STREAM if end_of_stream else FrameFlags.RESPONSE
    return encode_frame(
        frame_type=int(FrameType.RPC),
        flags=flags,
        header=header,
        payload=reply.payload,
    )
