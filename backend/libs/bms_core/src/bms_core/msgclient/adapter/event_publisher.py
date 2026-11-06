"""`EventPublisher` 的消息平台实现：`publish(event)` 走数据面 `/api/v1/msg/publish`（07B `06_01` 步 2）。

**为什么不用 `/rpc/...`**：发布是数据面语义（topic / 分区键 / 延迟档位 / 保留清理），RPC 通道只承诺
「`service.method` 分发一段字节」；把发布塞成 RPC 方法要把 topic、分区键、延迟都重新编码进载荷，
还会让 msg 端为一个通用能力维护一个特例方法。

**为什么复用基座纯函数**：topic 派生（`topic_for` = `bms-{域}-{对象}`）、信封编码（`encode_event`，
键排序确定性输出）、消息属性（`event_attributes`）已由 RocketMQ 通道验证并被消费端依赖；
另写一套必然在「消费端按属性读、生产端按 body 写」时对不上。

**不重试**：失败抛 `EventPublishError`（发件箱投递段 `10009`），退避重试与死信归投递器
（`outbox_dispatcher`）——两处都重试会让失败次数相乘。

**outbox 不改**：投递器仍调 `EventPublisher.publish`，切 `provider` 后自动改道；本类不写 outbox、
不参与确认，因此不引入双写窗口。
"""

from __future__ import annotations

import base64

import httpx

from bms_core.core.capability import BaseAsyncResource
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.events.base import EventEnvelope, EventPublisher, EventPublishError
from bms_core.events.topic import current_traceparent, encode_event, event_attributes, topic_for
from bms_core.msgclient.constants import RPC_TENANT_HEADER
from bms_core.tracing.base import current_trace_id

__all__ = ["DEFAULT_PUBLISH_TIMEOUT", "PUBLISH_PATH", "MsgEventPublisher"]

PUBLISH_PATH = "/api/v1/msg/publish"
"""数据面发布路径（既有 HTTP/1.1 基准面，OpenAPI 有声明）。

根路径 `/msg/publish` 是 HTTP/2 帧入口（同一端点实现、两处挂载），首期不走——JSON 形态对
「一条事件一次请求」的开销不明显，而帧形态会把 base64 与帧头耦合进来。
"""

DEFAULT_PUBLISH_TIMEOUT = 5.0
"""单次发布超时（秒）：短超时快速失败，重试交给投递器（不在本层等待）。"""

_STATUS_OK = 200
"""数据面发布成功状态码（其余一律按投递失败处理）。"""


class MsgEventPublisher(EventPublisher, BaseAsyncResource):
    """事件发布实现（消息平台数据面）。

    - 惰性建连：首次发布才创建 `httpx.AsyncClient`，`aclose()` 释放（经 `ResourceManager` 逆序回收）。
    - 命名空间：`[event].options["namespace"]` 或装配期回落值（msg 侧按已启用 `module_key` 校验，
      空串会被判 `350010`——所以拒启判断放在工厂，不放在这里）。
    - 租户：随 `X-Tenant-ID` 头传递（与数据面解析链同一来源口径）。
    """

    plugin_name: str = "msg"

    def __init__(
        self,
        *,
        base_url: str,
        namespace: str,
        tenant: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = DEFAULT_PUBLISH_TIMEOUT,
    ) -> None:
        """初始化。

        Args:
            base_url: 消息平台实例基址（不含尾斜线）。
            namespace: 命名空间（msg 侧按已启用 `module_key` 校验）。
            tenant: 缺省租户编码（逐事件 `event.tenant_id` 优先）。
            transport: httpx 传输（缺省真实网络；用例注入 `MockTransport`）。
            timeout: 单次发布超时（秒）。
        """
        self._base_url = base_url.rstrip("/")
        self._namespace = namespace
        self._tenant = tenant
        self._transport = transport
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def event_type(self) -> str:
        """本实现的事件类型标识（发布侧元信息；topic 仍按事件信封的 `event_type` 派生）。

        Returns:
            str: 实现标识。
        """
        return "msg"

    async def aclose(self) -> None:
        """释放 httpx 连接（幂等）。"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def publish(self, event: EventEnvelope) -> None:
        """发布事件（至少一次投递；失败上抛由投递器重试）。

        Args:
            event: 事件信封。

        Raises:
            EventPublishError: 传输异常或非 200 响应（`10009`）。
        """
        topic = topic_for(event.event_type)
        body = self._request_body(event, topic)
        headers: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        tenant = event.tenant_id or self._tenant
        if tenant:
            headers.set(RPC_TENANT_HEADER, tenant)
        client = self._ensure_client()
        try:
            response = await client.post(
                f"{self._base_url}{PUBLISH_PATH}",
                json=dict(body.items()),
                headers=dict(headers.items()),
            )
        except httpx.HTTPError as exc:
            raise EventPublishError(
                f"事件投递失败：{event.event_type}（{topic}）：{exc!r}",
                data={"event_type": event.event_type, "topic": topic},
            ) from exc
        if response.status_code != _STATUS_OK:
            raise EventPublishError(
                f"事件投递失败：{event.event_type}（{topic}）：HTTP {response.status_code}",
                data={"event_type": event.event_type, "topic": topic, "status": response.status_code},
            )

    async def publish_transactional(self, event: EventEnvelope) -> None:
        """事务消息发布（首期与普通发布同路径：事务消息归 8B_04）。

        Args:
            event: 事件信封。
        """
        await self.publish(event)

    def _request_body(self, event: EventEnvelope, topic: str) -> ConcurrentStableDict[str, object]:
        """构造数据面发布请求体（字段与 `PublishRequest` 一一对应）。

        Args:
            event: 事件信封。
            topic: 目标 topic。

        Returns:
            ConcurrentStableDict[str, object]: 请求体（调用点转内建 `dict` 后交给 `httpx.json=`）。
        """
        body: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        body.set("namespace", self._namespace)
        body.set("topic", topic)
        if event.aggregate_key is not None:
            body.set("key", event.aggregate_key)
        body.set("payload", base64.b64encode(encode_event(event)).decode("ascii"))
        body.set("headers", dict(event_attributes(event, traceparent=current_traceparent()).items()))
        trace_id = event.trace_id or current_trace_id()
        if trace_id is not None:
            body.set("trace_id", trace_id)
        return body

    def _ensure_client(self) -> httpx.AsyncClient:
        """惰性创建 httpx 客户端（复用连接）。

        Returns:
            httpx.AsyncClient: 客户端实例。
        """
        if self._client is None:
            self._client = httpx.AsyncClient(transport=self._transport, timeout=self._timeout)
        return self._client
