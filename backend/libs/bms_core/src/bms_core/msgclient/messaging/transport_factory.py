"""通道工厂（03-6-1 详细设计 §3.4）：按配置造实现，调用方只依赖契约。

**为什么单独一个模块**：契约（`transport.py`）不 import 任何实现，两个实现 import 契约；工厂要同时 import
两者，放在契约模块里就会成环。

**为什么不做运行期切换**：`channel` 只决定构造时用哪个实现。运行期切换会让「同一批消息一半帧一半 JSON」，
排障时无法判定承载，收益又只是省一次重建客户端——不做。
"""

from __future__ import annotations

import httpx

from bms_core.msgclient.messaging.config import MessagingConfig, TransportChannel
from bms_core.msgclient.messaging.transport import MessagingTransport
from bms_core.msgclient.messaging.transport_frame import FrameTransport
from bms_core.msgclient.messaging.transport_json import JsonTransport

__all__ = ["build_transport"]


def build_transport(config: MessagingConfig, *, client: httpx.AsyncClient | None = None) -> MessagingTransport:
    """按 `config.channel` 构造传输实现。

    Args:
        config: 客户端配置（`channel` 已在构造期校验过取值）。
        client: 外部注入的 httpx 客户端（用例注入 `MockTransport`；None = 由实现自行新建）。

    Returns:
        MessagingTransport: 帧或 JSON 实现。
    """
    if config.channel is TransportChannel.JSON:
        return JsonTransport(config, client=client)
    return FrameTransport(config, client=client)
