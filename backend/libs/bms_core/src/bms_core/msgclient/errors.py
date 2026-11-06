"""RPC 协议错误语义（07B 06_01 步 1 上移）：类别 / 结果语义 / 协议异常。

**切割判据**：只上移不含产品业务语义的部分；25 个业务异常与产品错误码覆盖器
（`MsgErrorMapper`）留在产品仓。协议异常的码值由 `constants.py` 的通用协议码常量提供。
"""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

from bms_core.core.exceptions import BizError
from bms_core.msgclient.constants import (
    FRAME_INVALID_CODE,
    PAYLOAD_TOO_LARGE_CODE,
    VERSION_UNSUPPORTED_CODE,
)

__all__ = [
    "ErrorCategory",
    "MsgError",
    "MsgFrameInvalidError",
    "MsgPayloadTooLargeError",
    "MsgVersionUnsupportedError",
    "Outcome",
]


class ErrorCategory(StrEnum):
    """错误类别（04-4）：`classify()` 三元组的第一维，客户端据此推导动作。

    与 `layer` **正交**：`layer` 回答「错在哪一层」，`category` 回答「调用方该怎么办」。
    同一类别可跨层（如 `transient` 既有 business 的 `350005`，也有 system 的 `350022`）。
    """

    PARAM_ERROR = "param_error"
    """参数错误：改参后放弃，不重试。"""

    BUSINESS_REJECT = "business_reject"
    """业务拒绝：上抛调用方，不重试。"""

    TRANSIENT = "transient"
    """瞬时故障：指数退避 + 抖动重试。"""

    UNKNOWN = "unknown"
    """超时 / 结果未知：`retryable=false`，仅在带幂等键时谨慎重试。"""

    SERVER_BUG = "server_bug"
    """服务端 bug：上抛 + 告警，不自动重试。"""


class Outcome(StrEnum):
    """调用结果语义（04-2 遗留闭合）：`ok` / `unknown` / `failed`。

    StrEnum 的值就是字符串，04-2 既有的 `detail.outcome == "unknown"` 断言零破坏。
    """

    OK = "ok"
    """确定成功。"""

    UNKNOWN = "unknown"
    """结果未知（超时 / 取消：可能已生效，也可能没跑）。"""

    FAILED = "failed"
    """确定失败（未产生副作用）。"""


class MsgError(BizError):
    """msg 业务异常基类（段位基；子类预置码位与 HTTP 状态）。"""

    code_: ClassVar[int]
    """错误码（子类预置）。"""

    http_status_: ClassVar[int] = 400
    """HTTP 状态（子类预置；业务失败缺省 400）。"""

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        """初始化 msg 业务异常。

        Args:
            message: 提示信息（缺省由前端按 `msg.error.*` 映射）。
            data: 随附数据（可选）。
        """
        super().__init__(type(self).code_, message, http_status=type(self).http_status_, data=data)


class MsgPayloadTooLargeError(MsgError):
    """帧或消息体超限（350006 / 413）：上限 1 MiB（header 另限 64 KiB；口径见 03-2 详细设计 §4.6）。"""

    code_: ClassVar[int] = PAYLOAD_TOO_LARGE_CODE
    http_status_: ClassVar[int] = 413


class MsgFrameInvalidError(MsgError):
    """帧格式非法（350018 / 400）：结构、必填头、类型与路径匹配度等协议层判定。"""

    code_: ClassVar[int] = FRAME_INVALID_CODE
    http_status_: ClassVar[int] = 400


class MsgVersionUnsupportedError(MsgError):
    """协议主版本不支持（350019 / 400）：返回后结束该 stream，由客户端断开连接（GOAWAY 归 03-4）。"""

    code_: ClassVar[int] = VERSION_UNSUPPORTED_CODE
    http_status_: ClassVar[int] = 400
