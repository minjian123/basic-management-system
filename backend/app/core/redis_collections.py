"""core 层 Redis 有序集合封装：跨副本共享、Lua 原子、版本号一致性。

- Redis 为唯一事实源；本地只读快照经版本号惰性比对（RedisSnapshot）
- key 命名遵循《命名规范》bms:{租户|global}:{域}:{键}，由调用方传入完整 key
- 序列化：JSON（ensure_ascii=False、sort_keys=True、不可序列化值降级 str）
- 复合操作（写索引 + 写数据）用 Lua 保证原子；版本号 key 为 `{key}:version`
"""

import json
from collections.abc import Awaitable, Callable
from typing import cast

from redis.asyncio import Redis

from app.core.base import BaseObject

_SET_SCRIPT = """
redis.call('HSET', KEYS[2], ARGV[1], ARGV[2])
redis.call('ZADD', KEYS[1], ARGV[3], ARGV[1])
return 1
"""

_SET_IF_ABSENT_SCRIPT = """
if redis.call('HEXISTS', KEYS[2], ARGV[1]) == 1 then
  return redis.call('HGET', KEYS[2], ARGV[1])
end
redis.call('HSET', KEYS[2], ARGV[1], ARGV[2])
redis.call('ZADD', KEYS[1], ARGV[3], ARGV[1])
return false
"""

_DELETE_SCRIPT = """
local removed = redis.call('ZREM', KEYS[1], ARGV[1])
redis.call('HDEL', KEYS[2], ARGV[1])
return removed
"""


def _dump(value: object) -> str:
    """稳定 JSON 序列化（键排序、不可序列化值降级 str）。

    Args:
        value: 原始值。

    Returns:
        str: JSON 字符串。
    """
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _load(raw: bytes | str | None) -> object:
    """反序列化（None 原样返回）。

    Args:
        raw: Redis 原始值。

    Returns:
        object: 反序列化结果。
    """
    if raw is None:
        return None
    return json.loads(raw.decode() if isinstance(raw, bytes) else raw)


def _score_for_key(key: object) -> float:
    """键排序分值：数值键按数值，其余按序列化后的字典序（score=0）。

    Args:
        key: 键对象。

    Returns:
        float: ZSET 分值。
    """
    if isinstance(key, bool) or not isinstance(key, (int, float)):
        return 0.0
    return float(key)


class RedisSortedSet[ItemT](BaseObject):
    """Redis 有序集合（ZSET）：按分值排序，跨副本共享。"""

    def __init__(self, client: Redis, key: str) -> None:
        self._client = client
        self._key = key
        self._version_key = f"{key}:version"

    async def add(self, member: ItemT, score: float) -> bool:
        """添加成员（存在则更新分值）。

        Args:
            member: 成员。
            score: 分值。

        Returns:
            bool: 新增 True（更新为 False）。
        """
        added = await self._client.zadd(self._key, {_dump(member): score})
        await self._bump()
        return bool(added)

    async def incr(self, member: ItemT, amount: float = 1.0) -> float:
        """原子累加分值。

        Args:
            member: 成员。
            amount: 增量。

        Returns:
            float: 新分值。
        """
        score = await self._client.zincrby(self._key, amount, _dump(member))
        await self._bump()
        return float(cast("float", score))

    async def remove(self, member: ItemT) -> bool:
        """移除成员。

        Args:
            member: 成员。

        Returns:
            bool: 移除 True（不存在 False）。
        """
        removed = await self._client.zrem(self._key, _dump(member))
        await self._bump()
        return bool(removed)

    async def score(self, member: ItemT) -> float | None:
        """查询分值。

        Args:
            member: 成员。

        Returns:
            float | None: 分值（不存在 None）。
        """
        value = await self._client.zscore(self._key, _dump(member))
        return float(value) if value is not None else None

    async def range_by_rank(self, start: int = 0, stop: int = -1) -> list[ItemT]:
        """按排名区间查询（分值升序）。

        Args:
            start: 起始排名。
            stop: 结束排名。

        Returns:
            list[ItemT]: 成员列表。
        """
        members = cast("list[str]", await self._client.zrange(self._key, start, stop))  # pyright: ignore[reportUnknownMemberType]
        return [_load(member) for member in members]  # type: ignore[misc]  # JSON 序列化成员即原值

    async def top(self, count: int) -> list[ItemT]:
        """查前 N 名（分值降序）。

        Args:
            count: 数量。

        Returns:
            list[ItemT]: 成员列表。
        """
        members = cast("list[str]", await self._client.zrevrange(self._key, 0, count - 1))  # pyright: ignore[reportUnknownMemberType]
        return [_load(member) for member in members]  # type: ignore[misc]

    async def range_by_score(self, minimum: float, maximum: float) -> list[ItemT]:
        """按分值区间查询。

        Args:
            minimum: 最小分值。
            maximum: 最大分值。

        Returns:
            list[ItemT]: 成员列表。
        """
        members = cast("list[str]", await self._client.zrangebyscore(self._key, minimum, maximum))  # pyright: ignore[reportUnknownMemberType]
        return [_load(member) for member in members]  # type: ignore[misc]

    async def size(self) -> int:
        """成员数。

        Returns:
            int: 成员数。
        """
        return int(await self._client.zcard(self._key))

    async def version(self) -> int:
        """当前版本号（跨副本一致性比对用）。

        Returns:
            int: 版本号（未写入过为 0）。
        """
        value = await self._client.get(self._version_key)
        return int(value) if value is not None else 0

    @property
    def version_key(self) -> str:
        """版本号 key（供 RedisSnapshot 使用）。

        Returns:
            str: 版本号 key。
        """
        return self._version_key

    async def _bump(self) -> int:
        return int(await self._client.incr(self._version_key))


class RedisSortedDict[KeyT, ValueT](BaseObject):
    """Redis 有序字典：ZSET 索引（键序）+ Hash 数据（值），Lua 保证两结构一致。"""

    def __init__(self, client: Redis, key: str) -> None:
        self._client = client
        self._key = key
        self._index_key = f"{key}:index"
        self._data_key = f"{key}:data"
        self._version_key = f"{key}:version"
        self._set_script = client.register_script(_SET_SCRIPT)
        self._set_if_absent_script = client.register_script(_SET_IF_ABSENT_SCRIPT)
        self._delete_script = client.register_script(_DELETE_SCRIPT)

    async def set(self, key: KeyT, value: ValueT) -> None:
        """写入键值（Lua 原子：索引 + 数据）。

        Args:
            key: 键。
            value: 值。
        """
        await self._set_script(
            keys=[self._index_key, self._data_key],
            args=[_dump(key), _dump(value), _score_for_key(key)],
        )
        await self._bump()

    async def set_if_absent(self, key: KeyT, value: ValueT) -> ValueT | None:
        """不存在才写入（Lua 原子），返回既有值或 None。

        Args:
            key: 键。
            value: 值。

        Returns:
            ValueT | None: 既有值（未写入）或 None（已写入）。
        """
        raw = await self._set_if_absent_script(
            keys=[self._index_key, self._data_key],
            args=[_dump(key), _dump(value), _score_for_key(key)],
        )
        if raw is not None:
            return _load(raw)  # type: ignore[return-value]
        await self._bump()
        return None

    async def delete(self, key: KeyT) -> bool:
        """删除键值（Lua 原子：索引 + 数据）。

        Args:
            key: 键。

        Returns:
            bool: 删除 True（不存在 False）。
        """
        removed = await self._delete_script(keys=[self._index_key, self._data_key], args=[_dump(key)])
        if removed:
            await self._bump()
        return bool(removed)

    async def get(self, key: KeyT) -> ValueT | None:
        """按键取值。

        Args:
            key: 键。

        Returns:
            ValueT | None: 值（不存在 None）。
        """
        raw = await self._client.hget(self._data_key, _dump(key))
        return _load(raw)  # type: ignore[return-value]

    async def contains(self, key: KeyT) -> bool:
        """键是否存在。

        Args:
            key: 键。

        Returns:
            bool: 存在 True。
        """
        return bool(await self._client.hexists(self._data_key, _dump(key)))

    async def items(self) -> list[tuple[KeyT, ValueT]]:
        """全部键值对（按键序）。

        Returns:
            list[tuple[KeyT, ValueT]]: 键值对列表。
        """
        members = cast("list[str]", await self._client.zrange(self._index_key, 0, -1))  # pyright: ignore[reportUnknownMemberType]
        if not members:
            return []
        values = await self._client.hmget(self._data_key, members)
        return [(_load(member), _load(value)) for member, value in zip(members, values, strict=True)]  # type: ignore[misc]

    async def size(self) -> int:
        """键数量。

        Returns:
            int: 键数量。
        """
        return int(await self._client.hlen(self._data_key))

    async def version(self) -> int:
        """当前版本号（跨副本一致性比对用）。

        Returns:
            int: 版本号（未写入过为 0）。
        """
        value = await self._client.get(self._version_key)
        return int(value) if value is not None else 0

    @property
    def version_key(self) -> str:
        """版本号 key（供 RedisSnapshot 使用）。

        Returns:
            str: 版本号 key。
        """
        return self._version_key

    async def _bump(self) -> int:
        return int(await self._client.incr(self._version_key))


class RedisSnapshot[DataT](BaseObject):
    """本地只读快照：远程版本号变化（或本地失效）时重载一次。"""

    def __init__(self, client: Redis, version_key: str, loader: Callable[[], Awaitable[DataT]]) -> None:
        self._client = client
        self._version_key = version_key
        self._loader = loader
        self._version: str | None = None
        self._data: DataT | None = None

    async def get(self) -> DataT:
        """取快照（必要时重载）。

        Returns:
            DataT: 快照数据。
        """
        raw = await self._client.get(self._version_key)
        current = None if raw is None else str(raw)
        if self._data is None or current != self._version:
            self._data = await self._loader()
            self._version = current
        return self._data

    async def invalidate(self) -> None:
        """本地失效（下次 get 强制重载）。"""
        self._version = None
        self._data = None
