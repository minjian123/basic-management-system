"""03-6 用例公共件：脚本化响应的假服务端、配置构造与端到端装配。

设计取舍：

- **不用真实网络**：`httpx.MockTransport` 接管，请求仍走真实 `MessagingTransport`（含请求头组装、
  响应解析、异常翻译），只把「对端」换掉；
- **时钟与抖动复用既有替身**：`msgclient_support.rpc_retry` 的 `FakeClock` / `FixedJitter` 已实现
  基座 `Clock` / `JitterSource` 协议，退避与幂等过期都能精确断言，不真等。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import httpx
from msgclient_support.rpc_retry import FakeClock, FixedJitter

from bms_core.core.concurrent import (
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.msgclient.messaging import (
    ClientStats,
    MessagingConfig,
    MessagingTransport,
    MsgConsumer,
    MsgProducer,
)
from bms_core.msgclient.retry import Clock, JitterMode, RetryPolicy

__all__ = [
    "Reply",
    "ScriptedServer",
    "build_config",
    "build_consumer",
    "build_producer",
    "build_transport",
    "ok_body",
]

DEFAULT_ENDPOINT = "http://msg-1:8000"
"""用例缺省地址。"""


def _empty_headers() -> ConcurrentStableFrozenDict[str, str]:
    """新建空响应头。

    Returns:
        ConcurrentStableFrozenDict[str, str]: 空映射。
    """
    return ConcurrentStableFrozenDict()


@dataclass
class Reply:
    """一条脚本化响应（或一次脚本化异常）。

    Attributes:
        path: 命中路径（`/msg/publish` 等）。
        body: 响应体（`None` 表示空对象）。
        status: HTTP 状态码。
        headers: 响应头。
        error: 若给出则直接抛出（模拟传输层异常）。
    """

    path: str
    body: object | None = None
    status: int = 200
    headers: ConcurrentStableFrozenDict[str, str] = field(default_factory=_empty_headers)
    error: Exception | None = None


def ok_body(code: int = 0, *, message: str = "", data: object | None = None) -> object:
    """构造统一响应体（`code` / `message` / `data`）。

    **返回内置 dict**：`httpx` 的 `json=` 只接受可被 `json.dumps` 序列化的结构，并发稳定集合不是
    原生可序列化类型；这一层是测试替身的序列化边界，故用内置 dict（与生产代码里同样的边界处理）。

    Args:
        code: 产品码（0 = 成功）。
        message: 提示。
        data: 业务数据。

    Returns:
        object: 响应体（内置 dict）。
    """
    return {"code": code, "message": message, "data": data}


class ScriptedServer:
    """按路径排队响应的假服务端（记录收到的请求，便于断言请求体与头）。

    Attributes:
        replies: 待消费的脚本响应。
        requests: 收到的请求（按到达顺序）。
    """

    def __init__(self) -> None:
        """初始化空脚本。"""
        self.replies: ConcurrentStableList[Reply] = ConcurrentStableList()
        self.requests: ConcurrentStableList[httpx.Request] = ConcurrentStableList()

    def push(
        self,
        path: str,
        *,
        body: object | None = None,
        status: int = 200,
        headers: ConcurrentStableFrozenDict[str, str] | None = None,
        error: Exception | None = None,
    ) -> None:
        """排一条响应（按加入顺序消费）。

        Args:
            path: 命中路径。
            body: 响应体。
            status: HTTP 状态码。
            headers: 响应头。
            error: 要抛出的异常。
        """
        self.replies.add(
            Reply(
                path=path,
                body=body,
                status=status,
                headers=headers if headers is not None else _empty_headers(),
                error=error,
            )
        )

    def handler(self, request: httpx.Request) -> httpx.Response:
        """httpx.MockTransport 的处理函数：按路径取第一条匹配脚本。

        Args:
            request: 请求。

        Returns:
            httpx.Response: 脚本化响应。

        Raises:
            Exception: 脚本指定的异常（原样抛出）。
        """
        self.requests.add(request)
        for index in range(len(self.replies)):
            reply = self.replies[index]
            if reply.path != request.url.path:
                continue
            self.replies.pop(index)
            if reply.error is not None:
                raise reply.error
            headers = {k: v for k, v in reply.headers.items()}
            if isinstance(reply.body, str):
                # 文本体用于覆盖「响应不是 JSON」分支（`json=` 会把字符串序列化成合法 JSON）
                return httpx.Response(reply.status, text=reply.body, headers=headers)
            payload = reply.body if reply.body is not None else ok_body()
            return httpx.Response(reply.status, json=payload, headers=headers)
        return httpx.Response(404, json={"code": 404, "message": "未脚本化", "data": None})


def build_config(*, clock: Clock | None = None, **overrides: object) -> MessagingConfig:
    """构造一个可用配置（缺省单地址、单租户、两次重试、无抖动）。

    Args:
        clock: 注入的时钟（缺省新建）。
        overrides: 覆盖字段（用例只改少量字段）。

    Returns:
        MessagingConfig: 配置。
    """
    base = MessagingConfig(
        endpoints=ConcurrentStableFrozenList([DEFAULT_ENDPOINT]),
        tenant="t1",
        retry=RetryPolicy(max_retries=2, base_ms=100, multiplier=2, cap_ms=2_000, jitter=JitterMode.NONE),
        clock=clock if clock is not None else FakeClock(),
        jitter=FixedJitter([1]),
    )
    if not overrides:
        return base
    return replace(base, **overrides)


def build_transport(config: MessagingConfig, server: ScriptedServer) -> MessagingTransport:
    """构造接在假服务端上的传输层。

    Args:
        config: 配置。
        server: 假服务端。

    Returns:
        MessagingTransport: 传输层。
    """
    client = httpx.AsyncClient(transport=httpx.MockTransport(server.handler))
    return MessagingTransport(config, client=client)


def build_producer(config: MessagingConfig, server: ScriptedServer) -> tuple[MsgProducer, ClientStats]:
    """构造生产端与它的计数器。

    Args:
        config: 配置。
        server: 假服务端。

    Returns:
        tuple[object, ClientStats]: （生产端，计数器）。
    """
    stats = ClientStats()
    return MsgProducer(config, build_transport(config, server), stats), stats


def build_consumer(config: MessagingConfig, server: ScriptedServer) -> tuple[MsgConsumer, ClientStats]:
    """构造消费端与它的计数器。

    Args:
        config: 配置。
        server: 假服务端。

    Returns:
        tuple[object, ClientStats]: （消费端，计数器）。
    """
    stats = ClientStats()
    consumer = MsgConsumer(
        config,
        build_transport(config, server),
        stats,
        group="g1",
        namespace="ns",
        topic="orders",
        consumer_id="c1",
    )
    return consumer, stats
