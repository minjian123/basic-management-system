"""幂等能力域 Redis 真实实现 `RedisIdempotencyStore`：SETNX 前置去重 + 首次结果复用。

- `begin`：`SET key <processing> NX EX ttl` —— 首次为 True（可执行业务）；重复为 False（应取首次结果）。
- `load`：处理中占位返回 None；命中结果时 JSON 解析返回。
- `save`：`SET key <json> EX ttl` —— 写首次结果供重复请求复用。
- 键空间经 `build_idempotency_key` 统一拼接（`bms:{租户|global}:idem:{键}`）；唯一约束兜底由
  各业务表 `idempotency_key` 唯一索引承担（本实现不改 `IdempotencyStore` 契约）。
- **客户端**：统一取进程共享客户端（`bms_core.redis`；禁止各自 `from_url`）。
- **不可用口径（fail-closed，03_04 / 需求 03-5）**：Redis 不可用（未启用 / 连接 / 命令异常）时
  **抛 `RedisUnavailableError`（`10012` / 503）**，不再「放行 + 唯一约束兜底」——避免「以为去了重」。
"""

import json
from typing import cast

from redis.asyncio import Redis

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import RedisUnavailableError
from bms_core.core.logging import get_logger
from bms_core.idempotency.base import (
    DEFAULT_IDEMPOTENCY_TTL,
    IDEMPOTENCY_PAYLOAD_TYPE,
    IdempotencyStore,
)

__all__ = ["RedisIdempotencyStore"]

_LOGGER = get_logger("bms")

_PROCESSING_MARKER: ConcurrentStableDict[str, object] = ConcurrentStableDict({"__processing__": True})
"""首次占用占位值（尚未写入结果）。"""


def _dump(value: object) -> str:
    """JSON 序列化（非 ASCII 直出、不可序列化项降级 str）。

    Args:
        value: 原始值。

    Returns:
        str: JSON 字符串。
    """
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _load(raw: object) -> object | None:
    """JSON 反序列化（失败按未命中）。

    Args:
        raw: Redis 原始值。

    Returns:
        object | None: 反序列化值；脏值返回 None。
    """
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    if not isinstance(raw, str):
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError, TypeError:
        return None


class RedisIdempotencyStore(IdempotencyStore):
    """Redis 幂等存储（插件名 `redis`）：SETNX 去重 + 首次结果存取。"""

    plugin_name = "redis"

    def __init__(self, url: str, *, client: Redis | None = None) -> None:
        """初始化（客户端惰性取用：显式注入优先，否则取进程共享客户端）。

        Args:
            url: Redis 连接串（保留兼容；连接参数统一取 `[redis]` 与共享客户端）。
            client: 注入的 Redis 客户端（测试用）；None 则取进程共享客户端。
        """
        self._client = client

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

    async def begin(self, key: str, *, ttl: int = DEFAULT_IDEMPOTENCY_TTL) -> bool:
        """前置去重（SETNX 首次占用）。

        Args:
            key: 幂等 key。
            ttl: 键有效期（秒）。

        Returns:
            bool: 首次 True；重复 False。

        Raises:
            RedisUnavailableError: Redis 不可用（fail-closed）。
        """
        try:
            stored = await self.client.set(key, _dump(dict(_PROCESSING_MARKER)), nx=True, ex=ttl)
        except RedisUnavailableError:
            raise
        except Exception as exc:  # Redis 不可用：fail-closed（不静默放行）
            _LOGGER.warning("redis_unavailable", op="idempotency_begin", error=repr(exc))
            raise RedisUnavailableError("幂等去重失败：Redis 不可用", data={"op": "begin"}) from exc
        return bool(stored)

    async def load(self, key: str) -> IDEMPOTENCY_PAYLOAD_TYPE | None:
        """取首次结果（处理中返回 None）。

        Args:
            key: 幂等 key。

        Returns:
            IDEMPOTENCY_PAYLOAD_TYPE | None: 首次结果；处理中 / 未缓存返回 None。

        Raises:
            RedisUnavailableError: Redis 不可用（fail-closed）。
        """
        try:
            value = _load(await self.client.get(key))
        except RedisUnavailableError:
            raise
        except Exception as exc:  # Redis 不可用：fail-closed（不按未命中放行）
            _LOGGER.warning("redis_unavailable", op="idempotency_load", error=repr(exc))
            raise RedisUnavailableError("幂等结果读取失败：Redis 不可用", data={"op": "load"}) from exc
        if value == dict(_PROCESSING_MARKER):
            return None
        if isinstance(value, dict):
            return cast("IDEMPOTENCY_PAYLOAD_TYPE", value)
        return None

    async def save(self, key: str, payload: IDEMPOTENCY_PAYLOAD_TYPE, *, ttl: int = DEFAULT_IDEMPOTENCY_TTL) -> None:
        """写首次结果（供重复请求复用）。

        Args:
            key: 幂等 key。
            payload: 首次结果载荷。
            ttl: 键有效期（秒）。

        Raises:
            RedisUnavailableError: Redis 不可用（fail-closed）。
        """
        try:
            await self.client.set(key, _dump(payload), ex=ttl)
        except RedisUnavailableError:
            raise
        except Exception as exc:  # Redis 不可用：fail-closed（结果不落缓存即报错）
            _LOGGER.warning("redis_unavailable", op="idempotency_save", error=repr(exc))
            raise RedisUnavailableError("幂等结果写入失败：Redis 不可用", data={"op": "save"}) from exc
