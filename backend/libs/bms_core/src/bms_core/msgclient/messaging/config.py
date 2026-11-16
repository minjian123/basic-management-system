"""消息收发客户端配置（msg 03-6）：地址池、租户、超时与重试预算。

**为什么重试不自己定义参数**：基座 `msgclient/retry.py` 的 `RetryPolicy` 已经是 04-4 定稿的单一事实源
（次数 / 基数 / 倍数 / 封顶 / 抖动），RPC 客户端就在用它。这里再写 `max_attempts` / `base_ms` / `cap_ms`
三个数字，等于给同一件事造第二套语义，日后必然漂。

**为什么配置不可变**：一份配置会被生产端与消费端共享，运行期改它会让「同一条消息两次尝试用不同预算」
成为可能。要换就换一个新配置对象。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlparse

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
)
from bms_core.core.exceptions import ParamError
from bms_core.core.roots import BaseValueObject
from bms_core.msgclient.retry import Clock, JitterSource, RetryPolicy, SystemClock, SystemJitter

__all__ = ["MessagingConfig", "TransportChannel"]


class TransportChannel(StrEnum):
    """数据面的承载形态（03-6-1：换帧后默认走帧，JSON 保留为可选中实现）。

    两条通道对外语义等价（同一份业务字段、同一份回执、同一套错误分类），差别只在承载：
    帧形态把业务字段放帧头、消息体走 payload 段；JSON 形态把两者都放请求体。
    """

    FRAME = "frame"
    """帧形态（`application/x-msg-frame`）：默认值。"""

    JSON = "json"
    """JSON 形态（`application/json`）：回退与对拍用，服务端同样支持。"""


def _empty_endpoints() -> ConcurrentStableFrozenList[str]:
    """新建空地址池（显式构造值，不在默认参数里写字面量容器）。

    Returns:
        ConcurrentStableFrozenList[str]: 空列表。
    """
    return ConcurrentStableFrozenList()


def _empty_node_addresses() -> ConcurrentStableFrozenDict[str, str]:
    """新建空节点地址表。

    Returns:
        ConcurrentStableFrozenDict[str, str]: 空映射。
    """
    return ConcurrentStableFrozenDict()


def _channel_of(value: object) -> TransportChannel:
    """把配置里的通道值规整成枚举（允许写字符串，便于配置化）。

    Args:
        value: 通道值（枚举或 `frame` / `json` 字符串）。

    Returns:
        TransportChannel: 通道枚举。

    Raises:
        ParamError: 取值不在枚举内。
    """
    if isinstance(value, TransportChannel):
        return value
    try:
        return TransportChannel(value)
    except ValueError as exc:
        raise ParamError(f"channel 只能是 frame 或 json（当前 {value!r}）") from exc


@dataclass(frozen=True)
class MessagingConfig(BaseValueObject):
    """消息收发客户端配置。

    Attributes:
        endpoints: 地址池（至少一个，形如 `http://msg:8000`；不得带路径）。
        tenant: 租户标识（写入 `X-Tenant-ID`；生产走网关时该头会被边缘中间件剥除并改由网关注入）。
        auth_provider: 返回 `Authorization` 头值的无参函数（None = 不带）。
        headers_provider: 返回自定义头的无参函数（与 `auth_provider` 合并，同名以 `auth_provider` 为准）。
        node_addresses: 节点标识 → 地址（直连部署时把 `350033` 的 `data.leader` 解析成地址）。
        connect_timeout_ms: 建连超时（毫秒）。
        request_timeout_ms: 单次请求预算（毫秒；不含重试，重试由 `retry` 的次数预算控制）。
        retry: 重试策略（复用基座 `RetryPolicy`）。
        refresh_min_interval_ms: 同分区两次改投的最小间隔（毫秒）。
        max_redirects: 单条消息改投次数上限。
        retry_ambiguous: 结果未知（提交超时 / 读超时）是否自动重试（缺省否）。
        idempotency_ttl_ms: 本地幂等表条目存活时长（毫秒）。
        idempotency_capacity: 本地幂等表条数上限（超出按插入序淘汰）。
        publish_concurrency: 批量发布的并发窗口。
        channel: 承载形态（缺省帧；见 `TransportChannel`）。
        clock: 可注入时钟（缺省 `SystemClock`；用例注入 fake 以确定性断言退避与过期）。
        jitter: 可注入抖动源（缺省 `SystemJitter`）。
    """

    endpoints: ConcurrentStableFrozenList[str] = field(default_factory=_empty_endpoints)
    tenant: str = ""
    auth_provider: Callable[[], str] | None = None
    headers_provider: Callable[[], ConcurrentStableDict[str, str]] | None = None
    node_addresses: ConcurrentStableFrozenDict[str, str] = field(default_factory=_empty_node_addresses)
    connect_timeout_ms: int = 3_000
    request_timeout_ms: int = 10_000
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    refresh_min_interval_ms: int = 200
    max_redirects: int = 3
    retry_ambiguous: bool = False
    idempotency_ttl_ms: int = 300_000
    idempotency_capacity: int = 1_024
    publish_concurrency: int = 8
    channel: TransportChannel = TransportChannel.FRAME
    clock: Clock = field(default_factory=SystemClock)
    jitter: JitterSource = field(default_factory=SystemJitter)

    def __post_init__(self) -> None:
        """校验配置（构造期即失败，避免把错配带到第一次发布）。

        Raises:
            ParamError: 地址池为空 / 地址非法 / 租户为空 / 取值为非正数 / 通道取值非法。
        """
        if not self.endpoints:
            raise ParamError("endpoints 不能为空：至少给一个服务地址")
        for endpoint in self.endpoints:
            self._check_endpoint(endpoint)
        if not self.tenant.strip():
            raise ParamError("tenant 不能为空：租户标识用于 X-Tenant-ID")
        object.__setattr__(self, "channel", _channel_of(self.channel))
        for name, value in (
            ("connect_timeout_ms", self.connect_timeout_ms),
            ("request_timeout_ms", self.request_timeout_ms),
            ("refresh_min_interval_ms", self.refresh_min_interval_ms),
            ("max_redirects", self.max_redirects),
            ("idempotency_ttl_ms", self.idempotency_ttl_ms),
            ("idempotency_capacity", self.idempotency_capacity),
            ("publish_concurrency", self.publish_concurrency),
        ):
            if value <= 0:
                raise ParamError(f"{name} 必须为正整数（当前 {value}）")

    @staticmethod
    def _check_endpoint(endpoint: str) -> None:
        """校验单个地址：协议 http/https、必须有主机、不得带路径。

        Args:
            endpoint: 地址。

        Raises:
            ParamError: 形态非法（带路径的地址会让拼出的 URL 变成 `/msg/msg/publish`）。
        """
        parsed = urlparse(endpoint)
        if parsed.scheme not in ("http", "https"):
            raise ParamError(f"地址协议必须是 http 或 https：{endpoint}")
        if not parsed.hostname:
            raise ParamError(f"地址缺少主机：{endpoint}")
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ParamError(f"地址不得带路径 / 查询串：{endpoint}")
