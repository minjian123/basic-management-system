"""实时推送能力域：Socket.IO 推送契约（真实 python-socketio + Redis 跨实例广播随实时推送阶段回补）。

- `REALTIME_EVENTS`：事件清单（`approval.todo` / `notification.new` / `session.revoked`，架构 17「事件路由」节）。
- `RealtimeEvent`：推送事件数据契约（frozen）——事件名 + 载荷 + 目标（用户 / 会话 / 房间）。
- `BaseRealtimePublisher`：能力域中间层契约（`key = "realtime_publisher"`）——异步 `emit` / `join` / `leave`。
- `get_realtime_publisher`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：原生 WebSocket 不采用（统一 Socket.IO，架构 17）；握手鉴权、连接注册（Redis `user_id → [{session_id, sid}]`）、
RedisManager 跨实例广播、事件路由消费与断线恢复归实时推送阶段上层；本契约只落推送原语（事件发送 + 房间加入 / 离开）。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from bms_core.core.base import BaseObject
from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin

__all__ = [
    "REALTIME_EVENTS",
    "BaseRealtimePublisher",
    "RealtimeEvent",
    "get_realtime_publisher",
]

REALTIME_EVENTS: tuple[str, ...] = ("approval.todo", "notification.new", "session.revoked")
"""事件清单（架构 17「事件路由」节）；占位期仅登记不校验。"""


@dataclass(frozen=True)
class RealtimeEvent(BaseObject):
    """推送事件（目标三选一：用户 / 会话 / 房间）。"""

    event: str
    """事件名（建议取 `REALTIME_EVENTS` 之一）。"""

    data: Mapping[str, object]
    """事件载荷。"""

    user_id: str | None = None
    """目标用户（推送其全部连接）。"""

    session_id: str | None = None
    """目标会话（推送该会话全部连接）。"""

    room: str | None = None
    """目标房间。"""


class BaseRealtimePublisher(BasePluggable, ABC):
    """实时推送契约：事件发送 + 房间加入 / 离开。"""

    key: str = "realtime_publisher"
    plugin_key: str = "realtime_publisher"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def emit(self, event: RealtimeEvent) -> None:
        """发送事件到目标（用户 / 会话 / 房间，按事件字段选择）。

        Args:
            event: 推送事件。
        """

    @abstractmethod
    async def join(self, session_id: str, room: str) -> None:
        """连接加入房间（Socket.IO 服务端 `join`）。

        Args:
            session_id: 连接所在会话。
            room: 房间名。
        """

    @abstractmethod
    async def leave(self, session_id: str, room: str) -> None:
        """连接离开房间（Socket.IO 服务端 `leave`）。

        Args:
            session_id: 连接所在会话。
            room: 房间名。
        """


def get_realtime_publisher(request: Request) -> BaseRealtimePublisher:
    """取应用级实时推送器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseRealtimePublisher: 应用装配的推送器实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseRealtimePublisher",
        resolve_plugin(
            "realtime_publisher",
            settings.realtime_publisher.provider,
            expected_version=BaseRealtimePublisher.contract_version,
        ),
    )
