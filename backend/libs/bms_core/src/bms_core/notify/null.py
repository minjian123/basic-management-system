"""notify 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 bms_core.notify.base.py 迁入）。"""

from bms_core.core.capability import BaseNullObject
from bms_core.notify.base import NULL_MESSAGE_ID, BaseNotifier, NotificationMessage, SendResult

__all__ = [
    "NullNotifier",
]


class NullNotifier(BaseNotifier, BaseNullObject):
    """占位通知器：固定返回成功（不真实发送，未接入真实渠道时使用）。"""

    async def send(self, message: NotificationMessage) -> SendResult:
        """恒定发送成功。

        Args:
            message: 通知消息（占位忽略）。

        Returns:
            SendResult: 成功结果（`delivered=True`、`message_id=NULL_MESSAGE_ID`）。
        """
        return SendResult(delivered=True, message_id=NULL_MESSAGE_ID)
