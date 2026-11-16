"""消息数据面传输契约（msg 03-6-1 详细设计 §3 / §4）：值对象、通道契约与 HTTP 公共件。

**为什么要有契约这一层**：03-6 首发只有一种承载（JSON），生产端与消费端直接依赖具体类。换帧后承载变成
两选一（帧 / JSON），调用方必须只依赖「发一次请求、拿一个结果」这一层——否则每加一种承载都要改生产端
与消费端。契约落在 `MessagingTransport`（`Protocol`，与基座 `msgclient/transport/base.py::RpcTransport`
同形态），实现分别落在 `transport_json.py` / `transport_frame.py`。

**本模块唯一的职责**：把「HTTP 异常」翻译成「消息层可判定的错误」——特别是区分
「请求没发出去」（可安全重试）与「发出去了没结果」（结果未知，重试可能重复），以及定义两个通道共用的
值对象。承载细节（JSON 请求体 / 帧编码）一概不在本模块。

**序列化边界只在这里收一次**：`fields` 里可以有并发稳定集合（配置、消息头都是），但 `json.dumps` 与
`msgpack.packb` 都只认内置结构，所以 `to_wire()` 统一把稳定集合摊成内置 `dict` / `list`。
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, cast

import httpx

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
)
from bms_core.core.roots import BaseFrameworkObject, BaseValueObject
from bms_core.msgclient.errors import ErrorCategory
from bms_core.msgclient.messaging.config import MessagingConfig
from bms_core.msgclient.messaging.errors import CLIENT_ERROR_CODE, ClientAction, MsgClientError
from bms_core.msgclient.retry import parse_retry_after

__all__ = [
    "ApiOutcome",
    "ApiRequest",
    "HttpxChannel",
    "MessagingTransport",
    "encode_payload",
    "freeze_data",
    "to_wire",
]

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


def _empty_fields() -> ConcurrentStableFrozenDict[str, object]:
    """新建空的业务字段表。

    Returns:
        ConcurrentStableFrozenDict[str, object]: 空映射。
    """
    return ConcurrentStableFrozenDict()


def _empty_data() -> ConcurrentStableFrozenDict[str, object]:
    """新建空的响应 `data` 映射。

    Returns:
        ConcurrentStableFrozenDict[str, object]: 空映射。
    """
    return ConcurrentStableFrozenDict()


def _empty_segments() -> ConcurrentStableFrozenList[bytes]:
    """新建空的载荷切片表。

    Returns:
        ConcurrentStableFrozenList[bytes]: 空列表。
    """
    return ConcurrentStableFrozenList()


@dataclass(frozen=True)
class ApiRequest(BaseValueObject):
    """一次业务请求的通道无关表达（同一份 `fields`，两种承载各自落位）。

    Attributes:
        frame_type: 帧类型编号（`PUBLISH` / `CONSUME` / `ACK` / `NACK` / `JOIN` / `LEAVE` /
            `MEMBER_HEARTBEAT`）。**必填**：03-6-2 起同一路径恒有帧形态，不存在「只能走 JSON」的端点。
        path: 端点路径（如 `/msg/publish`），两通道一致。
        fields: 业务字段（**不含 `payload`**；幂等键在 `fields["headers"]` 里）。
        payload: 消息体原始字节（仅发布非空；确认 / 拉取必须为空）。
    """

    frame_type: int
    path: str
    fields: ConcurrentStableFrozenDict[str, object] = field(default_factory=_empty_fields)
    payload: bytes = b""


@dataclass(frozen=True)
class ApiOutcome(BaseValueObject):
    """一次解析成功的响应（HTTP 层成功；业务是否成功看 `code`）。

    Attributes:
        code: 产品码（`0` = 成功）。
        message: 服务端提示。
        data: 服务端业务数据（不可变映射；错误时是异常随附数据）。
        retry_after_ms: 建议重试间隔（毫秒）。
        payload_segments: 拉取到的各条消息体原始字节，与 `data["messages"]` 按下标一一对应
            （帧通道有值、JSON 通道恒为空列表——JSON 的消息体在 `data["messages"][i]["payload"]` 的 base64 里）。
    """

    code: int
    message: str = ""
    data: ConcurrentStableFrozenDict[str, object] = field(default_factory=_empty_data)
    retry_after_ms: int | None = None
    payload_segments: ConcurrentStableFrozenList[bytes] = field(default_factory=_empty_segments)


class MessagingTransport(Protocol):
    """数据面通道契约（两个实现：`transport_frame.FrameTransport` / `transport_json.JsonTransport`）。"""

    def headers(self) -> ConcurrentStableDict[str, str]:
        """组装本次请求头（每请求现取，便于令牌轮换）。"""
        ...

    async def post(self, endpoint: str, request: ApiRequest) -> ApiOutcome:
        """发一次请求并解析响应。"""
        ...

    async def close(self) -> None:
        """关闭底层客户端（幂等）。"""
        ...


def to_wire(value: object) -> object:
    """把并发稳定集合摊成内置结构（`json.dumps` / `msgpack.packb` 的序列化边界）。

    Args:
        value: 任意值（映射 / 序列 / 标量，可嵌套）。

    Returns:
        object: 内置结构（映射 → `dict`，序列 → `list`，其余原样）。
    """
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return {str(key): to_wire(item) for key, item in mapping.items()}
    if isinstance(value, (list, tuple)):
        sequence = cast("list[object] | tuple[object, ...]", value)
        return [to_wire(item) for item in sequence]
    return value


def freeze_data(data: object) -> ConcurrentStableFrozenDict[str, object]:
    """把响应 `data` 转成不可变映射（非对象返回空映射）。

    Args:
        data: 响应里的 `data`（JSON 通道）或帧头 `detail`（帧通道）。

    Returns:
        ConcurrentStableFrozenDict[str, object]: 不可变映射。
    """
    if not isinstance(data, Mapping):
        return ConcurrentStableFrozenDict[str, object]()
    mapping = cast("Mapping[object, object]", data)
    return ConcurrentStableFrozenDict({str(key): item for key, item in mapping.items()})


def _translate(exc: httpx.HTTPError) -> MsgClientError:
    """把 httpx 异常翻成消息层错误（「未发出」可重试 / 「已发出无结果」结果未知）。

    Args:
        exc: httpx 抛出的异常。

    Returns:
        MsgClientError: 已分类的错误。
    """
    if isinstance(exc, _UNSENT_ERRORS):
        return MsgClientError(
            code=CLIENT_ERROR_CODE,
            category=ErrorCategory.TRANSIENT,
            action=ClientAction.RETRY,
            message=f"请求未发出（{type(exc).__name__}）：{exc}",
        )
    if isinstance(exc, _AMBIGUOUS_ERRORS):
        return MsgClientError(
            code=CLIENT_ERROR_CODE,
            category=ErrorCategory.UNKNOWN,
            action=ClientAction.FATAL,
            message=f"请求已发出但未取得结果（{type(exc).__name__}）：{exc}",
            outcome_unknown=True,
        )
    return MsgClientError(
        code=CLIENT_ERROR_CODE,
        category=ErrorCategory.UNKNOWN,
        action=ClientAction.FATAL,
        message=f"传输异常且无法判定是否已发出（{type(exc).__name__}）：{exc}",
        outcome_unknown=True,
    )


class HttpxChannel(BaseFrameworkObject):
    """两个 httpx 承载实现的公共父件（超时、请求头、关闭与异常翻译只写一份）。

    **为什么不各写一份**：「未发出 / 结果未知」的判断一旦分叉，就会出现「同一个网络错误在帧通道可重试、
    在 JSON 通道不可重试」这种最难查的不对称。

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

    async def close(self) -> None:
        """关闭底层客户端（幂等）。"""
        await self.client.aclose()

    async def _post_json(
        self,
        url: str,
        body: dict[str, object],  # bare-collections:allow（httpx 的 json= 只接受内置结构）
        headers: ConcurrentStableDict[str, str],
    ) -> httpx.Response:
        """发一次 JSON POST（异常统一翻译）。

        Args:
            url: 完整地址。
            body: 请求体（内置结构）。
            headers: 请求头。

        Returns:
            httpx.Response: 响应。

        Raises:
            MsgClientError: 传输失败（已分类）。
        """
        try:
            return await self.client.post(url, json=body, headers=_flat_headers(headers))
        except httpx.HTTPError as exc:
            raise _translate(exc) from exc

    async def _post_bytes(
        self,
        url: str,
        content: bytes,
        headers: ConcurrentStableDict[str, str],
    ) -> httpx.Response:
        """发一次二进制 POST（异常统一翻译）。

        Args:
            url: 完整地址。
            content: 请求体字节。
            headers: 请求头（含媒体类型）。

        Returns:
            httpx.Response: 响应。

        Raises:
            MsgClientError: 传输失败（已分类）。
        """
        try:
            return await self.client.post(url, content=content, headers=_flat_headers(headers))
        except httpx.HTTPError as exc:
            raise _translate(exc) from exc

    @staticmethod
    def _parse_json(response: httpx.Response, *, hint: str) -> ApiOutcome:
        """解析统一响应体为 `ApiOutcome`。

        Args:
            response: HTTP 响应。
            hint: 解析失败时的提示（两通道措辞不同：JSON 通道说「不是合法 JSON」，
                帧通道说「既不是帧也不是统一响应体」）。

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
                message=f"{hint}（HTTP {response.status_code}）",
            ) from exc
        if not isinstance(body, Mapping):
            raise MsgClientError(
                code=CLIENT_ERROR_CODE,
                category=ErrorCategory.SERVER_BUG,
                action=ClientAction.FATAL,
                message=f"{hint}：响应体不是对象",
            )
        mapping = cast("Mapping[str, object]", body)
        code = mapping.get("code")
        if not isinstance(code, int):
            raise MsgClientError(
                code=CLIENT_ERROR_CODE,
                category=ErrorCategory.SERVER_BUG,
                action=ClientAction.FATAL,
                message=f"{hint}：响应缺少整型 code",
            )
        message = mapping.get("message")
        data = mapping.get("data")
        return ApiOutcome(
            code=code,
            message="" if message is None else str(message),
            data=freeze_data(data),
            retry_after_ms=_retry_after_ms(response, data),
        )


def _flat_headers(headers: ConcurrentStableDict[str, str]) -> dict[str, str]:  # bare-collections:allow（httpx 入参）
    """把并发稳定头摊成内置 `dict`（httpx 的序列化边界）。

    Args:
        headers: 请求头。

    Returns:
        dict[str, str]: 内置字典。
    """
    return {key: value for key, value in headers.items()}


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
    if isinstance(data, Mapping):
        raw = cast("Mapping[str, object]", data).get("retry_after_ms")
        if isinstance(raw, int):
            return raw
    return None


def encode_payload(payload: bytes) -> str:
    """把消息体编成 base64 文本（JSON 通道的请求体字段）。

    Args:
        payload: 原始字节。

    Returns:
        str: base64 文本。
    """
    return base64.b64encode(payload).decode("ascii")
