"""消费幂等 L1：Redis 短窗口「只读预判 + 成功后标记」。

**关键取舍**：不用处理前 `SETNX` 占位。若处理前占位，首次处理失败回滚时数据库没有
`sys_event_consumed` 记录、Redis 却已占位 → 窗口内的重投被跳过，**至少一次退化为至多一次，
事件永久丢失**。因此：

- `seen()`：仅读（`EXISTS`），命中就跳过；**不占位**；
- `remember()`：仅在业务成功提交后写（`SET EX ttl`）。

**降级口径**：Redis 不可用时放行（`seen` 返回 False、`remember` 空操作）+ warn 日志——L2
（`sys_event_consumed` 唯一约束，与业务副作用同事务）仍在，语义正确，符合《后端开发规范》§10
「降级后语义仍正确才允许降级」。**不得**改成 fail-closed：那会让 Redis 故障直接停掉整条事件流。
"""

from __future__ import annotations

from redis.asyncio import Redis

from bms_core.core.exceptions import RedisUnavailableError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject

__all__ = ["DEFAULT_DEDUP_TTL_SECONDS", "EVENT_DEDUP_KEY_TEMPLATE", "EventConsumeDedup", "dedup_key"]

_LOGGER = get_logger("bms")

DEFAULT_DEDUP_TTL_SECONDS = 600
"""幂等短窗口 TTL（秒）：覆盖 broker 可见性超时与投递器重试窗口即可，无需长存。"""

EVENT_DEDUP_KEY_TEMPLATE = "bms:global:event:consumed:{group}:{event_id}"
"""幂等键口径（`bms:{租户|global}:{域}:{业务键}`）：消费组 + 事件 ID，跨租户共享。"""


def dedup_key(*, group: str, event_id: str) -> str:
    """构造幂等短窗口键。

    Args:
        group: 消费组名。
        event_id: 事件 ID。

    Returns:
        str: Redis 键。
    """
    return EVENT_DEDUP_KEY_TEMPLATE.format(group=group, event_id=event_id)


class EventConsumeDedup(BaseFrameworkObject):
    """消费幂等短窗口（Redis；不可用时降级放行）。"""

    def __init__(self, *, ttl: int = DEFAULT_DEDUP_TTL_SECONDS, client: Redis | None = None) -> None:
        """初始化。

        Args:
            ttl: 键有效期（秒）。
            client: 注入的异步客户端（测试用）；None 取进程共享客户端。
        """
        self._ttl = ttl
        self._client = client

    @property
    def client(self) -> Redis:
        """取异步客户端（显式注入优先，否则取进程共享客户端）。

        Returns:
            Redis: 异步客户端。

        Raises:
            RedisUnavailableError: Redis 未启用 / 不可用。
        """
        if self._client is None:
            from bms_core.redis.base import shared_async_client

            self._client = shared_async_client()
        return self._client

    async def seen(self, *, group: str, event_id: str) -> bool:
        """窗口内是否已成功处理过（只读预判，不占位）。

        Args:
            group: 消费组名。
            event_id: 事件 ID。

        Returns:
            bool: 已处理 True；未命中或 Redis 不可用 False（降级放行，由 L2 兜底）。
        """
        try:
            return bool(await self.client.exists(dedup_key(group=group, event_id=event_id)))
        except RedisUnavailableError:
            return False
        except Exception as exc:  # Redis 抖动：降级放行，不阻断事件流
            _LOGGER.warning("event_dedup_degraded", op="seen", group=group, error=repr(exc))
            return False

    async def remember(self, *, group: str, event_id: str) -> None:
        """标记窗口内已处理（仅业务成功后调用）。

        Args:
            group: 消费组名。
            event_id: 事件 ID。
        """
        try:
            await self.client.set(dedup_key(group=group, event_id=event_id), "1", ex=self._ttl)
        except RedisUnavailableError:
            return
        except Exception as exc:  # 标记失败只影响 L1 效率，不影响正确性
            _LOGGER.warning("event_dedup_degraded", op="remember", group=group, error=repr(exc))
