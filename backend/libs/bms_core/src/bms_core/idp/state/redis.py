"""流程状态存储能力域：Redis 实现（`bms:{租户}:idpstate:{state}`）。

- `RedisIdpStateStore`（插件名 `redis`）：值经 JSON 序列化（`SET ... EX ttl`）；
  `consume` 用 `GETDEL` 实现**一次性原子消费**（并发回调只有一个能拿到状态）。
- 降级：Redis 不可用（连接 / 命令异常）时 `consume` 按「未命中」处理并记日志
  （上层按回调校验失败 fail-closed 拒绝）；写入 / 删除失败向上暴露异常，由调用方决定语义。
"""

from __future__ import annotations

import json
from typing import cast

from redis.asyncio import Redis as AsyncRedis

from bms_core.core.capability import BaseAsyncResource
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.logging import get_logger
from bms_core.idp.state.base import (
    DEFAULT_IDP_STATE_TTL,
    IDP_STATE_DEFAULT_NAMESPACE,
    BaseIdpStateStore,
    build_idp_state_key,
)

__all__ = ["RedisIdpStateStore"]

_LOGGER = get_logger("bms")


def _dump(value: ConcurrentStableDict[str, object]) -> str:
    """序列化流程状态负载（JSON；不可序列化项经 `default=str` 兜底）。

    Args:
        value: 流程状态负载。

    Returns:
        str: JSON 字符串。
    """
    return json.dumps(dict(value), ensure_ascii=False, default=str)


def _load(raw: object) -> ConcurrentStableDict[str, object] | None:
    """反序列化流程状态负载（失败按未命中）。

    Args:
        raw: Redis 原始值。

    Returns:
        ConcurrentStableDict[str, object] | None: 流程状态负载；未命中 / 脏值返回 None。
    """
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return ConcurrentStableDict(cast("dict[str, object]", parsed))


class RedisIdpStateStore(BaseIdpStateStore, BaseAsyncResource):
    """Redis 流程状态实现（多副本一致；`GETDEL` 一次性消费）。"""

    def __init__(self, *, url: str | None = None, client: AsyncRedis | None = None) -> None:
        """初始化（懒建连）。

        Args:
            url: Redis 连接串（缺省由装配工厂取 `settings.redis.url` 注入）。
            client: 异步客户端（测试注入 `fakeredis.aioredis.FakeRedis`；缺省按 `url` 懒建）。
        """
        self._url = url
        self._client = client

    @property
    def client(self) -> AsyncRedis:
        """取异步客户端（懒建）。

        Returns:
            AsyncRedis: 异步客户端实例。
        """
        if self._client is None:
            self._client = AsyncRedis.from_url(self._url or "", decode_responses=True)  # pyright: ignore[reportUnknownMemberType]
        return self._client

    async def save(
        self,
        state: str,
        payload: ConcurrentStableDict[str, object],
        *,
        tenant: str | None = None,
        ttl: int = DEFAULT_IDP_STATE_TTL,
        namespace: str = IDP_STATE_DEFAULT_NAMESPACE,
    ) -> None:
        """写入流程状态（`SET key value EX ttl`）。

        Args:
            state: 流程状态（state）。
            payload: 状态数据（JSON）。
            tenant: 租户编码（定位键）。
            ttl: 有效期（秒）。
            namespace: 命名空间（默认 `idpstate`）。
        """
        key = build_idp_state_key(state, tenant=tenant, namespace=namespace)
        if ttl > 0:
            await self.client.set(key, _dump(payload), ex=ttl)  # pyright: ignore[reportUnknownMemberType]
        else:
            await self.client.set(key, _dump(payload))  # pyright: ignore[reportUnknownMemberType]

    async def consume(
        self,
        state: str,
        *,
        tenant: str | None = None,
        namespace: str = IDP_STATE_DEFAULT_NAMESPACE,
    ) -> ConcurrentStableDict[str, object] | None:
        """一次性原子消费流程状态（`GETDEL`；Redis 异常按未命中并记日志）。

        Args:
            state: 流程状态（state）。
            tenant: 租户编码。
            namespace: 命名空间（默认 `idpstate`）。

        Returns:
            ConcurrentStableDict[str, object] | None: 状态数据；不存在 / 已消费 / 过期返回 None。
        """
        key = build_idp_state_key(state, tenant=tenant, namespace=namespace)
        try:
            raw = await self.client.getdel(key)  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            _LOGGER.warning("流程状态读取降级", state=state[:8], error=str(exc))
            return None
        return _load(raw)

    async def delete(
        self,
        state: str,
        *,
        tenant: str | None = None,
        namespace: str = IDP_STATE_DEFAULT_NAMESPACE,
    ) -> None:
        """删除流程状态（幂等）。

        Args:
            state: 流程状态（state）。
            tenant: 租户编码。
            namespace: 命名空间（默认 `idpstate`）。
        """
        await self.client.delete(build_idp_state_key(state, tenant=tenant, namespace=namespace))  # pyright: ignore[reportUnknownMemberType]

    async def aclose(self) -> None:
        """释放客户端（幂等）。"""
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.aclose()  # pyright: ignore[reportUnknownMemberType]
            except Exception as exc:  # pragma: no cover - 关闭失败仅日志
                _LOGGER.warning("流程状态存储关闭失败", error=str(exc))
