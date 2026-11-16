"""消息数据面 HTTP 传输（msg 03-6 详细设计 §3.1 / §7.3）：JSON 通道。

**为什么不复用 `msgclient/transport/`**：那套是 HTTP/2 **帧**传输，为 RPC 的「精确取消（`RST_STREAM`）」
而生。消息发布 / 拉取走 JSON（错误体才带 `data.leader`，见 03-6 设计 §3.1），复用帧传输会把帧协议与
base64 一起拖进来。形态上对齐 `msgclient/adapter/event_publisher.py`（httpx + 可注入 `AsyncBaseTransport`）。

**本模块唯一的职责**：把「HTTP 异常」翻译成「消息层可判定的错误」——特别是区分
「请求没发出去」（可安全重试）与「发出去了没结果」（结果未知，重试可能重复）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

import httpx

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict
from bms_core.core.roots import BaseFrameworkObject, BaseValueObject
from bms_core.msgclient.errors import ErrorCategory
from bms_core.msgclient.messaging.config import MessagingConfig
from bms_core.msgclient.messaging.errors import CLIENT_ERROR_CODE, ClientAction, MsgClientError
from bms_core.msgclient.retry import parse_retry_after

__all__ = ["ApiOutcome", "MessagingTransport"]

_UNSENT_ERRORS: tuple[type[httpx.HTTPError], ...] = (  # bare-collections:allow（except 子句只接受内置 tuple）
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)
"""「请求未发出」类异常：建连失败 / 建连超时 / 连接池拿不到连接（重试安全）。"""

_AMBIGUOUS_ERRORS: tuple[type[httpx.HTTPError], ...] = (  # bare-collections:allow（同上）
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.ReadError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
)
"""「已发出但没拿到完整响应」类异常：结果未知（可能已写入）。"""


def _empty_data() -> ConcurrentStableFrozenDict[str, object]:
    """新建空的 `data` 映射。

    Returns:
        ConcurrentStableFrozenDict[str, object]: 空映射。
    """
    return ConcurrentStableFrozenDict()


@dataclass(frozen=True)
class ApiOutcome(BaseValueObject):
    """一次解析成功的响应（HTTP 层成功；业务是否成功看 `code`）。

    Attributes:
        code: 产品码（`0` = 成功）。
        message: 服务端提示。
        data: 服务端 `data`（不可变映射）。
        retry_after_ms: 建议重试间隔（毫秒；`Retry-After` 优先，其次 `data.retry_after_ms`）。
    """

    code: int
    message: str = ""
    data: ConcurrentStableFrozenDict[str, object] = field(default_factory=_empty_data)
    retry_after_ms: int | None = None


class MessagingTransport(BaseFrameworkObject):
    """消息收发共用的 JSON 传输（单实例可被生产端与消费端共享）。

    Attributes:
        config: 客户端配置（读地址、超时与请求头来源）。
        client: httpx 异步客户端（用例注入 `MockTransport`）。
    """

    def __init__(self, config: MessagingConfig, *, client: httpx.AsyncClient | None = None) -> None:
        """初始化。

        Args:
            config: 客户端配置。
            client: 外部注入的 httpx 客户端（None = 按配置新建）。
        """
        self.config = config
        timeout = httpx.Timeout(
            connect=config.connect_timeout_ms / 1_000,
            read=config.request_timeout_ms / 1_000,
            write=config.request_timeout_ms / 1_000,
            pool=config.connect_timeout_ms / 1_000,
        )
        self.client = client if client is not None else httpx.AsyncClient(timeout=timeout)

    def headers(self) -> ConcurrentStableDict[str, str]:
        """按配置组装本次请求头（每请求现取，便于令牌轮换）。

        Returns:
            ConcurrentStableDict[str, str]: 请求头（租户 → 自定义头 → 鉴权，后者覆盖前者）。
        """
        headers: ConcurrentStableDict[str, str] = ConcurrentStableDict({"X-Tenant-ID": self.config.tenant})
        if self.config.headers_provider is not None:
            for key, value in self.config.headers_provider().items():
                headers.set(key, value)
        if self.config.auth_provider is not None:
            headers.set("Authorization", self.config.auth_provider())
        return headers

    async def post(self, endpoint: str, path: str, body: object) -> ApiOutcome:
        """发一次 POST 并解析响应。

        Args:
            endpoint: 服务地址（`scheme://host:port`，不带路径）。
            path: 端点路径（如 `/msg/publish`）。
            body: 请求体（内置 dict 组装的 JSON 结构）。

        Returns:
            ApiOutcome: 解析后的响应。

        Raises:
            MsgClientError: 传输失败或响应不可解析。
        """
        url = f"{endpoint}{path}"
        try:
            response = await self.client.post(
                url,
                json=body,
                headers={key: value for key, value in self.headers().items()},
            )
        except _UNSENT_ERRORS as exc:
            raise MsgClientError(
                code=CLIENT_ERROR_CODE,
                category=ErrorCategory.TRANSIENT,
                action=ClientAction.RETRY,
                message=f"请求未发出（{type(exc).__name__}）：{exc}",
            ) from exc
        except _AMBIGUOUS_ERRORS as exc:
            raise MsgClientError(
                code=CLIENT_ERROR_CODE,
                category=ErrorCategory.UNKNOWN,
                action=ClientAction.FATAL,
                message=f"请求已发出但未取得结果（{type(exc).__name__}）：{exc}",
                outcome_unknown=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise MsgClientError(
                code=CLIENT_ERROR_CODE,
                category=ErrorCategory.UNKNOWN,
                action=ClientAction.FATAL,
                message=f"传输异常且无法判定是否已发出（{type(exc).__name__}）：{exc}",
                outcome_unknown=True,
            ) from exc
        return self._parse(response)

    async def close(self) -> None:
        """关闭底层客户端（幂等）。"""
        await self.client.aclose()

    @staticmethod
    def _parse(response: httpx.Response) -> ApiOutcome:
        """解析响应体为 `ApiOutcome`（不合法即不可重试错误）。

        Args:
            response: HTTP 响应。

        Returns:
            ApiOutcome: 解析结果。

        Raises:
            MsgClientError: 响应不是统一响应体（对端不是本服务 / 被网关改写）。
        """
        try:
            body: object = response.json()
        except ValueError as exc:
            raise MsgClientError(
                code=CLIENT_ERROR_CODE,
                category=ErrorCategory.SERVER_BUG,
                action=ClientAction.FATAL,
                message=f"响应不是合法 JSON（HTTP {response.status_code}）",
            ) from exc
        if not isinstance(body, dict):
            raise MsgClientError(
                code=CLIENT_ERROR_CODE,
                category=ErrorCategory.SERVER_BUG,
                action=ClientAction.FATAL,
                message="响应体不是对象（预期统一响应体）",
            )
        mapping = cast("dict[str, object]", body)
        code = mapping.get("code")
        if not isinstance(code, int):
            raise MsgClientError(
                code=CLIENT_ERROR_CODE,
                category=ErrorCategory.SERVER_BUG,
                action=ClientAction.FATAL,
                message="响应缺少整型 code（预期统一响应体）",
            )
        message = mapping.get("message")
        data = mapping.get("data")
        return ApiOutcome(
            code=code,
            message="" if message is None else str(message),
            data=_freeze_data(data),
            retry_after_ms=_retry_after_ms(response, data),
        )


def _freeze_data(data: object) -> ConcurrentStableFrozenDict[str, object]:
    """把响应 `data` 转成不可变映射（非对象返回空映射）。

    Args:
        data: 响应里的 `data`。

    Returns:
        ConcurrentStableFrozenDict[str, object]: 不可变映射。
    """
    if not isinstance(data, dict):
        return ConcurrentStableFrozenDict[str, object]()
    mapping = cast("dict[str, object]", data)
    return ConcurrentStableFrozenDict({str(key): value for key, value in mapping.items()})


def _retry_after_ms(response: httpx.Response, data: object) -> int | None:
    """取建议重试间隔：`Retry-After`（秒）优先，其次 `data.retry_after_ms`。

    Args:
        response: HTTP 响应。
        data: 响应里的 `data`。

    Returns:
        int | None: 毫秒；都没有则 None。
    """
    from_header = parse_retry_after(tuple(response.headers.items()))
    if from_header is not None:
        return from_header
    if isinstance(data, dict):
        raw = cast("dict[str, object]", data).get("retry_after_ms")
        if isinstance(raw, int):
            return raw
    return None
