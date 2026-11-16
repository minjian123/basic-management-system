"""通知请求事件：`notification.requested` 的负载、信封与发件箱助手。

口径：

- 业务方**不直写通知表**，只发请求事件；通知组消费后落库并推送。
- 正文由生产方按收件人语言渲染后传入（与 `BaseNotifier`「接收已渲染内容」一致）。
- 生产者必须与业务写**同事务**调用 `enqueue_notification_request`，保证「业务成功才有通知请求」。
- 租户位显式传入或取当前上下文；无租户的请求直接拒绝（通知按租户库隔离）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.context import get_current_tenant_id
from bms_core.core.exceptions import ParamError
from bms_core.core.objects import BaseValueObject
from bms_core.db.session import DbSession
from bms_core.events.base import EventEnvelope
from bms_core.notification.types import (
    NOTIFICATION_TYPE_ALERT,
    NOTIFICATION_TYPE_APPROVAL,
    NOTIFICATION_TYPE_IMPORT,
    NOTIFICATION_TYPE_SYSTEM,
    NOTIFICATION_TYPES,
)
from bms_core.outbox.base import BaseOutboxStore
from bms_core.outbox.store import SqlOutboxStore

__all__ = [
    "NOTIFICATION_REQUESTED_EVENT",
    "NOTIFICATION_TYPES",
    "NOTIFICATION_TYPE_ALERT",
    "NOTIFICATION_TYPE_APPROVAL",
    "NOTIFICATION_TYPE_IMPORT",
    "NOTIFICATION_TYPE_SYSTEM",
    "NotificationRequest",
    "build_requested_envelope",
    "enqueue_notification_request",
]

NOTIFICATION_REQUESTED_EVENT = "notification.requested"
"""业务方请求发送一条通知（通知组消费落库）。"""


@dataclass(frozen=True)
class NotificationRequest(BaseValueObject):
    """一条通知请求（业务方 → 通知组）。"""

    user_id: int
    """收件用户主键。"""

    title: str
    """标题。"""

    type: str = NOTIFICATION_TYPE_SYSTEM
    """通知类型（`NOTIFICATION_TYPES` 之一）。"""

    content: str = ""
    """正文（已按收件人语言渲染）。"""

    biz_type: str | None = None
    """业务类型（如 `approval` / `export`）。"""

    biz_id: str | None = None
    """业务标识（供跳转）。"""

    email: str | None = None
    """收件邮箱（可选；邮件渠道开启且提供时交 `BaseNotifier`）。"""

    phone: str | None = None
    """收件手机号（可选；短信渠道开启且提供时交 `BaseNotifier`）。"""

    def to_payload(self) -> ConcurrentStableDict[str, object]:
        """转事件负载（只写非空可选字段）。

        Returns:
            ConcurrentStableDict[str, object]: 事件负载。
        """
        payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {"user_id": str(self.user_id), "title": self.title, "type": self.type}
        )
        if self.content:
            payload.set("content", self.content)
        optional = (
            ("biz_type", self.biz_type),
            ("biz_id", self.biz_id),
            ("email", self.email),
            ("phone", self.phone),
        )
        for key, value in optional:
            if value:
                payload.set(key, value)
        return payload


def build_requested_envelope(request: NotificationRequest, *, tenant_id: str | None) -> EventEnvelope:
    """构造 `notification.requested` 事件信封。

    Args:
        request: 通知请求。
        tenant_id: 租户主键（十进制字符串；None 取当前上下文）。

    Returns:
        EventEnvelope: 事件信封（聚合键按收件用户保序）。

    Raises:
        ParamError: 类型非法、标题为空或租户位缺失（`10001`）。
    """
    if request.type not in NOTIFICATION_TYPES:
        raise ParamError(f"通知类型非法：{request.type}")
    title = request.title.strip()
    if not title:
        raise ParamError("通知标题不得为空")
    resolved_tenant = tenant_id or get_current_tenant_id()
    if not resolved_tenant:
        raise ParamError("通知请求缺少租户位")
    return EventEnvelope(
        event_type=NOTIFICATION_REQUESTED_EVENT,
        payload=request.to_payload(),
        tenant_id=resolved_tenant,
        aggregate_key=f"notification:{request.user_id}",
        event_version="1.0.0",
    )


async def enqueue_notification_request(
    session: DbSession,
    request: NotificationRequest,
    *,
    tenant_id: str | None = None,
    outbox: BaseOutboxStore | None = None,
) -> str:
    """在业务事务内写通知请求事件到发件箱。

    Args:
        session: 业务事务会话。
        request: 通知请求。
        tenant_id: 租户主键（None 取当前上下文）。
        outbox: 发件箱存储（None 使用 SQL 实现，按 `[event].contract_mode` 校验）。

    Returns:
        str: 事件 ID。

    Raises:
        ParamError: 类型非法、标题为空或租户位缺失（`10001`）。
    """
    envelope = build_requested_envelope(request, tenant_id=tenant_id)
    store = outbox if outbox is not None else _default_outbox()
    return await store.enqueue(session, envelope)


def _default_outbox() -> BaseOutboxStore:
    """构造缺省发件箱（按配置的契约校验模式）。

    Returns:
        BaseOutboxStore: SQL 发件箱。
    """
    from bms_core.core.config import get_settings

    return cast("BaseOutboxStore", SqlOutboxStore(contract_mode=get_settings().event.contract_mode))
