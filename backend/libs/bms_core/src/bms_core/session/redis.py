"""会话存储能力域：Redis 会话标记实现（`bms:{租户}:sess:{会话 id}`）。

- `RedisSessionStore`（插件名 `redis`）：值经 JSON 序列化写入 Redis（`SET ... EX ttl`），
  `load` 未命中返回 None（= 会话不存在 = 已踢出 / 登出语义），`delete` 删除标记。
- 口径：本实现只承载**会话标记存活性**；每请求校验链（验签 → 类型 → 标记存在性）归上层认证依赖（01_05）。
- 降级：Redis 不可用（连接 / 命令异常）时 `load` 按「标记不存在」处理并记日志（上层按 fail-closed 拒绝）；
  写入 / 删除失败向上暴露异常，由调用方决定语义（登录 / 刷新的写入失败即不可用）。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from redis.asyncio import Redis as AsyncRedis

from bms_core.core.capability import BaseAsyncResource
from bms_core.core.logging import get_logger
from bms_core.session.base import DEFAULT_SESSION_TTL, BaseSessionStore, build_session_key

__all__ = ["RedisSessionStore"]

_LOGGER = get_logger("bms")


def _dump(value: Mapping[str, object]) -> str:
    """序列化会话负载（JSON；不可序列化项经 `default=str` 兜底）。

    Args:
        value: 会话负载。

    Returns:
        str: JSON 字符串。
    """
    return json.dumps(dict(value), ensure_ascii=False, default=str)


def _load(raw: object) -> Mapping[str, object] | None:
    """反序列化会话负载（失败按未命中）。

    Args:
        raw: Redis 原始值。

    Returns:
        Mapping[str, object] | None: 会话负载；未命中 / 脏值返回 None。
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
    return cast("Mapping[str, object]", parsed)


class RedisSessionStore(BaseSessionStore, BaseAsyncResource):
    """Redis 会话标记实现（多副本一致；TTL 与 refresh 对齐）。"""

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
        session_id: str,
        payload: Mapping[str, object],
        *,
        tenant: str | None = None,
        ttl: int = DEFAULT_SESSION_TTL,
    ) -> None:
        """写入 / 覆盖会话标记（`SET key value EX ttl`）。

        Args:
            session_id: 会话 id（`jti`）。
            payload: 会话数据（JSON）。
            tenant: 租户编码（定位键）。
            ttl: 有效期（秒，默认 14 天）。
        """
        key = build_session_key(session_id, tenant=tenant or _tenant_of(payload))
        if ttl > 0:
            await self.client.set(key, _dump(payload), ex=ttl)  # pyright: ignore[reportUnknownMemberType]
        else:
            await self.client.set(key, _dump(payload))  # pyright: ignore[reportUnknownMemberType]

    async def load(self, session_id: str, *, tenant: str | None = None) -> Mapping[str, object] | None:
        """读取会话标记（按租户定位键）。

        Args:
            session_id: 会话 id。
            tenant: 租户编码。

        Returns:
            Mapping[str, object] | None: 会话数据；不存在返回 None。
        """
        try:
            raw = await self.client.get(build_session_key(session_id, tenant=tenant))  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            _LOGGER.warning("会话标记读取降级", session_id=session_id, error=str(exc))
            return None
        return _load(raw)

    async def delete(self, session_id: str, *, tenant: str | None = None) -> None:
        """删除会话标记（幂等）。

        Args:
            session_id: 会话 id。
            tenant: 租户编码。
        """
        await self.client.delete(build_session_key(session_id, tenant=tenant))  # pyright: ignore[reportUnknownMemberType]

    async def blacklist(self, key: str, *, ttl: int) -> None:
        """写入令牌黑名单标记（`SET key 1 EX ttl`）。

        Args:
            key: 黑名单键（`BaseSessionSecurity.blacklist_key(jti)`）。
            ttl: 有效期（秒）。
        """
        await self.client.set(key, "1", ex=max(1, ttl))  # pyright: ignore[reportUnknownMemberType]

    async def is_blacklisted(self, key: str) -> bool:
        """判定令牌是否已入黑名单（Redis 异常按未命中并记日志）。

        Args:
            key: 黑名单键。

        Returns:
            bool: 已入黑名单为 True。
        """
        try:
            return bool(await self.client.exists(key))  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            _LOGGER.warning("黑名单读取降级", key=key, error=str(exc))
            return False

    async def aclose(self) -> None:
        """释放客户端（幂等）。"""
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.aclose()  # pyright: ignore[reportUnknownMemberType]
            except Exception as exc:  # pragma: no cover - 关闭失败仅日志
                _LOGGER.warning("会话存储关闭失败", error=str(exc))


def _tenant_of(payload: Mapping[str, object]) -> str | None:
    """从会话负载取租户编码（无则 None）。

    Args:
        payload: 会话负载。

    Returns:
        str | None: 租户编码。
    """
    value = payload.get("tenant")
    return str(value) if value else None
