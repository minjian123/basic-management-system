"""通知生成服务：把一条通知请求落库，并在同事务发布 `notification.sent`。"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import get_settings
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.events.base import EventEnvelope
from bms_core.notification.request import NotificationRequest
from bms_core.outbox.base import BaseOutboxStore
from bms_core.outbox.store import SqlOutboxStore
from bms_notification.domains.notification.models.notification import SysNotification

__all__ = ["NOTIFICATION_SENT_EVENT", "NotificationGenerationService"]

NOTIFICATION_SENT_EVENT = "notification.sent"
"""站内信落库后发布（供内部联动 / 审计；Webhook 不订阅）。"""


class NotificationGenerationService(BaseFrameworkObject):
    """通知生成（消费侧专用；事务归调用方）。"""

    def __init__(self, session: DbSession, *, outbox: BaseOutboxStore | None = None) -> None:
        """初始化。

        Args:
            session: 租户库会话。
            outbox: 发件箱存储（None 使用 SQL 实现）。
        """
        self._session = session
        self._outbox = (
            outbox
            if outbox is not None
            else SqlOutboxStore(contract_mode=get_settings().event.contract_mode)
        )

    async def create(self, request: NotificationRequest, *, tenant_id: str) -> SysNotification:
        """落库一条站内信并写 `notification.sent`。

        Args:
            request: 通知请求。
            tenant_id: 租户主键（十进制字符串）。

        Returns:
            SysNotification: 已 flush 的通知行。
        """
        row = SysNotification(
            user_id=request.user_id,
            title=request.title,
            content=request.content,
            type=request.type,
            biz_type=request.biz_type,
            biz_id=request.biz_id,
            is_read=False,
        )
        self._session.add(row)
        await self._session.flush()
        payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {"user_id": str(request.user_id), "type": request.type}
        )
        if request.biz_type:
            payload.set("biz_type", request.biz_type)
        await self._outbox.enqueue(
            self._session,
            EventEnvelope(
                event_type=NOTIFICATION_SENT_EVENT,
                payload=payload,
                tenant_id=tenant_id,
                aggregate_key=f"notification:{request.user_id}",
            ),
        )
        return row
