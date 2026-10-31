"""任务变更信号：Redis pub/sub 唤醒通道（**只做唤醒，不承担正确性**）。

设计取舍（《详细设计 · 任务调度》§4.3 关键点 5）：

- pub/sub **不持久**：订阅断线期间消息全丢。因此它只用来「让 beat 立刻醒一次」，
  正确性由 `[task_scheduler].poll_interval_seconds` 的周期轮询兜底——丢了最多晚一个周期生效；
- 发布失败（Redis 抖动）**不抛错**：任务定义已在库里落定，通知只是加速，失败记 warn 即可，
  绝不能因为「通知没发出去」而回滚业务写入；
- 订阅失败（Redis 不可用）同样不抛错：`wake_loop` 直接返回，调度器照常按周期轮询。
"""

from __future__ import annotations

import asyncio

from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import RedisError

from bms_core.core.exceptions import RedisUnavailableError
from bms_core.core.logging import get_logger
from bms_core.core.roots import BaseFrameworkObject
from bms_core.redis.base import shared_async_client

__all__ = ["DEFAULT_CHANGE_CHANNEL", "TaskChangeSignal", "close_pubsub"]

_LOGGER = get_logger("bms")

DEFAULT_CHANGE_CHANNEL = "bms:global:task:changed"
"""缺省变更信道（`[task_scheduler].change_channel` 可覆盖）。"""

_SIGNAL_BODY = "1"
"""信号体：内容无语义，仅表示「任务集合变了」。"""

_MESSAGE_TYPE = "message"
"""pub/sub 消息类型（订阅确认等其他类型忽略）。"""


class TaskChangeSignal(BaseFrameworkObject):
    """任务变更信号（发布 + 订阅唤醒）。"""

    def __init__(self, *, client: AsyncRedis | None = None, channel: str = DEFAULT_CHANGE_CHANNEL) -> None:
        """初始化。

        Args:
            client: 异步客户端（测试注入 `fakeredis`；缺省取进程共享客户端）。
            channel: 信道名。
        """
        self._client = client
        self._channel = channel

    @property
    def channel(self) -> str:
        """信道名。

        Returns:
            str: 信道名。
        """
        return self._channel

    def _redis(self) -> AsyncRedis:
        """取异步客户端（显式注入优先）。

        Returns:
            AsyncRedis: 客户端实例。
        """
        return self._client if self._client is not None else shared_async_client()

    async def publish(self) -> bool:
        """发布一次变更信号。

        Returns:
            bool: 发出 True；Redis 不可用 / 发布失败 False（只记 warn，不抛错）。
        """
        try:
            await self._redis().publish(self._channel, _SIGNAL_BODY)
        except (RedisUnavailableError, RedisError) as exc:
            _LOGGER.warning("任务变更信号发布失败（不影响写库，调度退化为周期轮询）", error=str(exc))
            return False
        return True

    async def wake_loop(self, event: asyncio.Event) -> None:
        """订阅变更信号，收到即 `event.set()` 唤醒调度器一轮。

        取消（任务被 cancel）或 Redis 异常时退出，**不抛错**——调度器照常按周期轮询。

        Args:
            event: 唤醒事件（由调度器持有）。

        Returns:
            None: 无返回值。
        """
        pubsub = None
        try:
            pubsub = self._redis().pubsub()
            await pubsub.subscribe(self._channel)
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message is not None and message.get("type") == _MESSAGE_TYPE:
                    event.set()
        except asyncio.CancelledError:
            raise
        except (RedisUnavailableError, RedisError) as exc:
            _LOGGER.warning("任务变更信号订阅中断（调度退化为周期轮询）", error=str(exc))
        finally:
            if pubsub is not None:
                await close_pubsub(pubsub)


async def close_pubsub(pubsub: object) -> None:
    """关闭订阅（尽力而为，失败只记 debug）。

    Args:
        pubsub: pub/sub 对象（`redis.asyncio.client.PubSub`）。

    Returns:
        None: 无返回值。
    """
    closer = getattr(pubsub, "aclose", None)
    if closer is None:
        return
    try:
        result = closer()
        if asyncio.iscoroutine(result):  # pragma: no branch - 同步关闭实现仅兼容保留
            await result
    except (RedisUnavailableError, RedisError) as exc:  # pragma: no cover - 关闭失败无补救动作
        _LOGGER.debug("任务变更信号订阅关闭失败", error=str(exc))
