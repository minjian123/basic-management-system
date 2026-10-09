"""一致性屏障 Redis 真实实现 `RedisConsistencyBarrier`：版本标记 + 有界轮询等待。

- `applied_version` / `mark_applied`：键 `bms:{租户|global}:consistency:{scope}` 存整数版本；
  `mark_applied` 经 Lua 脚本**单调前推**（`max(旧值, 新值)`），防乱序消费回退。
- `await_applied`：有界轮询至「已应用版本 ≥ 目标版本」；超时抛 `ConsistencyBarrierTimeout`（`10011` / 409）。
- **客户端**：统一取进程共享客户端（`bms_core.redis`；禁止各自 `from_url`）。
- **不可用口径（fail-closed，03_04 / 需求 03-5）**：Redis 不可用（未启用 / 连接 / 命令异常）时
  **抛 `RedisUnavailableError`（`10012` / 503）**，**不再放行（degrade-open 作废）**——
  宁可明确报错可重试，也不静默按旧值 / 半套状态放行。
"""

import asyncio
import time

from redis.asyncio import Redis

from bms_core.consistency.base import (
    DEFAULT_BARRIER_POLL_MS,
    DEFAULT_BARRIER_TIMEOUT_MS,
    BaseConsistencyBarrier,
    build_consistency_key,
)
from bms_core.core.exceptions import ConsistencyBarrierTimeout, RedisUnavailableError
from bms_core.core.logging import get_logger

__all__ = ["RedisConsistencyBarrier"]

_LOGGER = get_logger("bms")

_MARK_APPLIED_SCRIPT = """
local current = tonumber(redis.call('GET', KEYS[1])) or 0
local incoming = tonumber(ARGV[1])
if incoming > current then redis.call('SET', KEYS[1], ARGV[1]) end
return 1
"""
"""单调前推脚本（只前推不回退）。"""


class RedisConsistencyBarrier(BaseConsistencyBarrier):
    """Redis 一致性屏障（插件名 `redis`）：版本标记 + 有界轮询等待。"""

    plugin_name = "redis"

    def __init__(
        self,
        url: str,
        *,
        client: Redis | None = None,
        default_timeout_ms: int = DEFAULT_BARRIER_TIMEOUT_MS,
        default_poll_ms: int = DEFAULT_BARRIER_POLL_MS,
    ) -> None:
        """初始化（惰性建连，不校验连通性）。

        Args:
            url: Redis 连接串。
            client: 注入的 Redis 客户端（测试用）；None 则取进程共享客户端。
            default_timeout_ms: 默认等待超时（毫秒）。
            default_poll_ms: 默认轮询间隔（毫秒）。
        """
        self._client = client
        self._timeout_ms = default_timeout_ms
        self._poll_ms = max(1, default_poll_ms)

    @property
    def client(self) -> Redis:
        """取异步客户端（显式注入优先，否则取进程共享客户端）。

        Returns:
            Redis: 异步客户端实例。

        Raises:
            RedisUnavailableError: Redis 未启用 / 不可用（fail-closed）。
        """
        if self._client is None:
            from bms_core.redis.base import shared_async_client

            self._client = shared_async_client()
        return self._client

    async def _read(self, key: str) -> int:
        """读键值（不可用即报错，不返回「伪 0」）。

        Args:
            key: 一致性屏障键。

        Returns:
            int: 已应用版本；无记录为 0。

        Raises:
            RedisUnavailableError: Redis 不可用（fail-closed）。
        """
        try:
            raw = await self.client.get(key)
        except RedisUnavailableError:
            raise
        except Exception as exc:  # Redis 不可用：fail-closed（不放行）
            _LOGGER.warning("redis_unavailable", op="consistency_barrier_read", error=repr(exc))
            raise RedisUnavailableError("一致性屏障读取失败：Redis 不可用", data={"op": "read"}) from exc
        if raw is None:
            return 0
        try:
            return int(raw)
        except TypeError, ValueError:
            return 0

    async def applied_version(self, *, scope: str, tenant: str | None = None) -> int:
        """读当前已应用版本（存储不可用即报错，不回落伪 0）。

        Args:
            scope: 收敛域键。
            tenant: 租户标识；None 表示全局。

        Returns:
            int: 已应用版本；无记录返回 0。

        Raises:
            RedisUnavailableError: Redis 不可用（fail-closed）。
        """
        return await self._read(build_consistency_key(scope=scope, tenant=tenant))

    async def mark_applied(self, *, scope: str, version: int, tenant: str | None = None) -> None:
        """单调前推已应用版本（存储不可用即报错）。

        Args:
            scope: 收敛域键。
            version: 本次已应用的版本。
            tenant: 租户标识；None 表示全局。

        Raises:
            RedisUnavailableError: Redis 不可用（fail-closed）。
        """
        key = build_consistency_key(scope=scope, tenant=tenant)
        try:
            await self.client.eval(_MARK_APPLIED_SCRIPT, 1, key, str(version))
        except RedisUnavailableError:
            raise
        except Exception as exc:  # Redis 不可用：fail-closed（标记不落库即报错）
            _LOGGER.warning("redis_unavailable", op="consistency_barrier_mark", error=repr(exc))
            raise RedisUnavailableError("一致性屏障版本推进失败：Redis 不可用", data={"op": "mark"}) from exc

    async def await_applied(
        self,
        *,
        scope: str,
        target_version: int,
        tenant: str | None = None,
        timeout_ms: int | None = None,
        poll_ms: int | None = None,
    ) -> None:
        """有界轮询至「已应用版本 ≥ 目标版本」；超时抛 `ConsistencyBarrierTimeout`。

        Args:
            scope: 收敛域键。
            target_version: 目标版本（写方产生）。
            tenant: 租户标识；None 表示全局。
            timeout_ms: 等待超时（毫秒）；None 取配置缺省。
            poll_ms: 轮询间隔（毫秒）；None 取配置缺省。

        Raises:
            ConsistencyBarrierTimeout: 超时仍未收敛（`10011` / 409）。
        """
        key = build_consistency_key(scope=scope, tenant=tenant)
        effective_timeout = self._timeout_ms if timeout_ms is None else timeout_ms
        effective_poll = max(1, self._poll_ms if poll_ms is None else poll_ms)
        deadline = time.monotonic() + effective_timeout / 1000
        while True:
            current = await self._read(key)
            if current >= target_version:
                return
            if time.monotonic() >= deadline:
                raise ConsistencyBarrierTimeout(
                    f"一致性屏障等待超时：scope={scope} 目标版本={target_version} 已应用版本={current}",
                    data={"scope": scope, "target_version": target_version, "applied_version": current},
                )
            await asyncio.sleep(effective_poll / 1000)
