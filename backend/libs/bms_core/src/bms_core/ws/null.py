"""ws 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 bms_core.ws.base.py 迁入）。"""

from bms_core.core.capability import BaseNullObject
from bms_core.ws.base import BaseRealtimePublisher, RealtimeEvent

__all__ = [
    "NullRealtimePublisher",
]


class NullRealtimePublisher(BaseRealtimePublisher, BaseNullObject):
    """占位推送器：三方法空操作（不连 Socket.IO / Redis，未接入真实实现时使用）。"""

    async def emit(self, event: RealtimeEvent) -> None:
        """空操作（占位不推送）。

        Args:
            event: 推送事件（占位忽略）。
        """

    async def join(self, session_id: str, room: str) -> None:
        """空操作（占位不加入房间）。

        Args:
            session_id: 连接所在会话（占位忽略）。
            room: 房间名（占位忽略）。
        """

    async def leave(self, session_id: str, room: str) -> None:
        """空操作（占位不离开房间）。

        Args:
            session_id: 连接所在会话（占位忽略）。
            room: 房间名（占位忽略）。
        """
