"""消息收发客户端错误模型（msg 03-6 详细设计 §5.4）。

**两维而不是一套新枚举**：

- `category` 直接复用基座 `msgclient.errors.ErrorCategory`——它是 04-4 对「码本身性质」的判定
  （`transient` / `unknown` / `business_reject` / `param_error` / `server_bug`），RPC 客户端与 msg 服务端
  的 `classify()` 已经在用；再定义一套同名枚举会让「同一个 350005 在两处类别不同」变成可能。
- `action` 是本层特有的一维：消息发布多了「换地址重发（改投）」这个动作，而 `transient` 既可能是
  「原地退避」（限流）也可能是「换节点」（写错 leader）——基座枚举刻意不含这层，故另加。

`action` 只由 `codes.py` 的码表给出，不在别处二次判定。
"""

from __future__ import annotations

from enum import StrEnum

from bms_core.core.concurrent import ConcurrentStableFrozenDict
from bms_core.core.exceptions import BizError
from bms_core.msgclient.errors import ErrorCategory

__all__ = ["CLIENT_ERROR_CODE", "ClientAction", "MsgClientError"]


class ClientAction(StrEnum):
    """本层动作（调用方按它决定「重发 / 重建客户端 / 改参」）。"""

    RETRY = "retry"
    """原地退避后重发（瞬时故障：限流、容量、系统繁忙、建连失败）。"""

    REFRESH = "refresh"
    """换地址重发（视图过期：写错 leader / 过期任期 / 切换中 / 租约过期）。"""

    FATAL = "fatal"
    """不重发（改参或人工介入；含「结果未知」——见 `outcome_unknown`）。"""


CLIENT_ERROR_CODE = 0
"""客户端自造错误的码位：**不占用产品码段（35）**。

产品码由服务端给；客户端只在「请求没到服务端」或「响应不可解析」时自己产生错误，
用 0 表示「无产品码」，不伪装成产品码（否则调用方按 35 段查文档会查不到）。
"""


class MsgClientError(BizError):
    """消息客户端统一错误。

    Attributes:
        code: 产品码；`0` 表示客户端自造（传输失败 / 响应不可解析）。
        category: 基座错误类别（码本身的性质）。
        action: 本层动作（该不该再发、怎么发）。
        message: 可读提示（服务端提示原样带回）。
        data: 服务端 `data` 原样（含 `leader` / `epoch` / `reason`），缺省空映射。
        outcome_unknown: 结果未知（可能已写入）；为真时调用方重试需自带去重。
        retry_after_ms: 服务端建议的重试间隔（毫秒），可空。
    """

    def __init__(
        self,
        *,
        code: int,
        category: ErrorCategory,
        action: ClientAction,
        message: str,
        data: ConcurrentStableFrozenDict[str, object] | None = None,
        outcome_unknown: bool = False,
        retry_after_ms: int | None = None,
    ) -> None:
        """初始化。

        Args:
            code: 产品码；`0` 表示客户端自造。
            category: 基座错误类别。
            action: 本层动作。
            message: 可读提示。
            data: 服务端 `data`（None = 空）。
            outcome_unknown: 结果是否未知。
            retry_after_ms: 建议重试间隔（毫秒）。
        """
        normalized: ConcurrentStableFrozenDict[str, object] = (
            data if data is not None else ConcurrentStableFrozenDict[str, object]()
        )
        # 客户端传输层错误不属业务失败：`http_status=500` 保持「未预期故障」语义
        super().__init__(code, message, http_status=500, data=normalized)
        self.category = category
        self.action = action
        self.outcome_unknown = outcome_unknown
        self.retry_after_ms = retry_after_ms

    def __str__(self) -> str:
        """可读串（`码 / 类别 / 动作 / 提示`，排障时不必再翻码表）。

        Returns:
            str: 例如 `350033 transient refresh: 非 leader`。
        """
        return f"{self.code} {self.category.value} {self.action.value}: {self.message}"
