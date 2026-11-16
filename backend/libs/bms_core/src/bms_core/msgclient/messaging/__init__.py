"""消息收发客户端（msg 03-6）：生产端完整 + 消费端最小集。

**与 `msgclient/adapter/event_publisher.py` 的分工**（别混用）：

| | `MsgEventPublisher`（既有） | 本包（`messaging`） |
| --- | --- | --- |
| 语义 | 事件投递：把 bms 事件信封编码后发到 msg | 消息收发：发布 / 拉取 / 确认 / 成员保活 |
| 产品码 | 不看（非 200 一律投递失败） | 按码表分「改投 / 重试 / 人工」|
| 重试 | 不重试（归 outbox 投递器） | 按 `RetryPolicy` 自动重试与改投 |
| 消费 | 无 | `join` / `poll` / `ack` / `nack` / `heartbeat` |
| 幂等 | 无 | 本地幂等表（进程内，跨重启失效） |

**为什么不合并**：合并会让 outbox 的「不重试」语义漏进数据面，或让数据面的「结果未知」语义污染投递器
（投递器重试会与 outbox 的重试相乘，这是 `MsgEventPublisher` 明确写下的设计约束）。
"""

from bms_core.msgclient.messaging.codes import rule_for_consume, rule_for_publish
from bms_core.msgclient.messaging.config import MessagingConfig, TransportChannel
from bms_core.msgclient.messaging.consumer import (
    Assignment,
    CommitResult,
    MsgConsumer,
    PollResult,
    ReceivedMessage,
)
from bms_core.msgclient.messaging.errors import CLIENT_ERROR_CODE, ClientAction, MsgClientError
from bms_core.msgclient.messaging.producer import (
    FailedItem,
    MsgProducer,
    OutgoingMessage,
    PublishAck,
    PublishBatchResult,
    SucceededItem,
)
from bms_core.msgclient.messaging.stats import ClientStats
from bms_core.msgclient.messaging.transport import ApiOutcome, ApiRequest, MessagingTransport
from bms_core.msgclient.messaging.transport_factory import build_transport
from bms_core.msgclient.messaging.transport_frame import FrameTransport
from bms_core.msgclient.messaging.transport_json import JsonTransport

__all__ = [
    "CLIENT_ERROR_CODE",
    "ApiOutcome",
    "ApiRequest",
    "Assignment",
    "ClientAction",
    "ClientStats",
    "CommitResult",
    "FailedItem",
    "FrameTransport",
    "JsonTransport",
    "MessagingConfig",
    "MessagingTransport",
    "MsgClientError",
    "MsgConsumer",
    "MsgProducer",
    "OutgoingMessage",
    "PollResult",
    "PublishAck",
    "PublishBatchResult",
    "ReceivedMessage",
    "SucceededItem",
    "TransportChannel",
    "build_transport",
    "rule_for_consume",
    "rule_for_publish",
]
