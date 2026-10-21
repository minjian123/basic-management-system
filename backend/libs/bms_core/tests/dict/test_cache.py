"""字典域缓存实现用例（`02_09` 改指补齐）：L1 / Redis 两层与基类缺省异步实现。

覆盖 `bms_core/dict/cache.py`（`MemoryDictCacheRegion` / `RedisDictCacheRegion`）与
`bms_core/dict/base.py` 的 `DictCacheRegion` 键构成、缺省异步实现与版本 / 互斥锁语义：

- 键构成（`type_cache_key` / `version_cache_key` / `id_cache_key`）与 `is_version_current`；
- 基类缺省实现（`aid_subset` / `aset_id_subset` / `aversion` / `aincrease_version` / `alock` / `arelease_lock`）；
- 内存实现：代理读写、按租户版本、进程内互斥锁（占用 / 令牌比对）；
- Redis 实现：L1 命中短路、Redis 命中回填 L1、双删、版本 `INCR`、SETNX 锁与非数字版本回落；
- 依赖注入提供者（字典取数 / 翻译 / 缓存域）。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import fakeredis
import pytest

from bms_core.cache.redis import RedisCacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.dict.base import (
    DICT_CACHE_DOMAIN,
    DictCacheRegion,
    get_data_source,
    get_dict_cache_region,
    get_dict_translator,
)
from bms_core.dict.cache import MemoryDictCacheRegion, RedisDictCacheRegion


class _BareRegion(DictCacheRegion):
    """最小具体实现：仅落同步四件套，用于覆盖基类缺省异步实现。"""

    def __init__(self) -> None:
        """初始化空缓存与版本号。"""
        self._items: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        self._version = 0

    @property
    def domain(self) -> str:
        """业务域简称。

        Returns:
            str: 域简称。
        """
        return DICT_CACHE_DOMAIN

    def get(self, key: str) -> object | None:
        """读缓存。

        Args:
            key: 缓存 key。

        Returns:
            object | None: 缓存值。
        """
        return self._items.get(key)

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        """写缓存。

        Args:
            key: 缓存 key。
            value: 缓存值。
            ttl: 有效期（秒；本实现忽略）。
        """
        self._items.set(key, value)

    def delete(self, key: str) -> bool:
        """删缓存。

        Args:
            key: 缓存 key。

        Returns:
            bool: 删到为 True。
        """
        if self._items.get(key) is None:
            return False
        self._items.delete(key)
        return True

    def get_global_version(self) -> int:
        """取全局版本号。

        Returns:
            int: 版本号。
        """
        return self._version

    def bump(self) -> None:
        """自增版本号（用例内部使用）。"""
        self._version += 1


def test_bare_region_defaults_and_key_layout() -> None:
    """基类缺省实现 + 键构成 + 版本一致性判定。"""
    region = _BareRegion()
    type_key = region.type_cache_key("t1", "zh-CN", "user_status")
    assert type_key == region.build_key("zh-CN:user_status", tenant="t1")
    assert region.version_cache_key(None) == region.build_key("version", tenant=None)
    assert region.id_cache_key("t1", "zh-CN", "user_status").endswith(":id")

    assert region.is_version_current(0, tenant="t1") is True
    region.bump()
    assert region.is_version_current(0, tenant="t1") is False
    assert region.is_stale("any-key", 0) is True


async def test_bare_region_async_defaults_round_trip() -> None:
    """基类缺省异步实现：类型读写删、按条目 id 子集读写、版本读写、互斥锁恒真。"""
    region = _BareRegion()
    await region.aset_type("t1", "zh-CN", "demo", {"version": 1}, 60)
    assert await region.aget_type("t1", "zh-CN", "demo") == {"version": 1}
    await region.adrop_type("t1", "zh-CN", "demo")
    assert await region.aget_type("t1", "zh-CN", "demo") is None

    assert await region.aversion("t1") == 0
    assert await region.aincrease_version("t1") == 1

    empty = await region.aid_subset("t1", "zh-CN", "demo", ConcurrentStableList([1]))
    assert empty == {}

    cached: ConcurrentStableDict[int, str] = ConcurrentStableDict()
    cached.set(1, "A")
    await region.aset_id_subset("t1", "zh-CN", "demo", cached)
    assert await region.aid_subset("t1", "zh-CN", "demo", ConcurrentStableList([1, 2])) == {1: "A"}

    extra: ConcurrentStableDict[int, str] = ConcurrentStableDict()
    extra.set(2, "B")
    await region.aset_id_subset("t1", "zh-CN", "demo", extra)
    assert await region.aid_subset("t1", "zh-CN", "demo", ConcurrentStableList([1, 2])) == {1: "A", 2: "B"}

    assert await region.alock("t1", "zh-CN", "demo", "tok") is True
    assert await region.arelease_lock("t1", "zh-CN", "demo", "tok") is True


async def test_memory_region_proxy_versions_and_lock() -> None:
    """内存实现：读写删代理、按租户版本、进程内互斥锁占用与令牌比对。"""
    region = MemoryDictCacheRegion(max_items=8)
    region.set("k", "v")
    assert region.get("k") == "v"
    assert region.delete("k") is True
    assert region.delete("k") is False

    assert region.bump_version("t1") == 1
    assert region.bump_version("t1") == 2
    assert region.bump_version(None) == 1
    assert await region.aversion("t1") == 2
    assert await region.aversion(None) == 1
    assert await region.aincrease_version("t1") == 3
    assert region.get_global_version() >= 3

    assert await region.alock("t1", "zh-CN", "demo", "tok-a") is True
    assert await region.alock("t1", "zh-CN", "demo", "tok-b") is False
    assert await region.arelease_lock("t1", "zh-CN", "demo", "tok-b") is False
    assert await region.arelease_lock("t1", "zh-CN", "demo", "tok-a") is True
    assert await region.alock("t1", "zh-CN", "demo", "tok-a") is True


def _redis_region() -> RedisDictCacheRegion:
    """构造以 fakeredis 承载的字典域 Redis 缓存（同步 / 异步共享同一 FakeServer）。

    Returns:
        RedisDictCacheRegion: 两层缓存实例。
    """
    fake: Any = fakeredis
    server = fake.FakeServer()
    inner = RedisCacheRegion(
        domain=DICT_CACHE_DOMAIN,
        sync_client=fake.FakeRedis(server=server, decode_responses=True),
        async_client=fake.aioredis.FakeRedis(server=server, decode_responses=True),
    )
    return RedisDictCacheRegion(redis_region=inner, max_items=8)


async def test_redis_region_two_layer_reads_writes_and_deletes() -> None:
    """Redis 实现：L1 命中短路、Redis 命中回填 L1、写双落、删双删。"""
    region = _redis_region()
    await region.setup()
    inner = region.redis_region

    region.set("k", "v")
    assert region.get("k") == "v"
    assert inner.get("k") == "v"

    # L1 缺失、Redis 命中 → 回填 L1。
    key = region.type_cache_key("t1", "zh-CN", "demo")
    await inner.aset(key, {"version": 1})
    assert await region.aget_type("t1", "zh-CN", "demo") == {"version": 1}
    assert region.get(key) is not None

    await region.aset_type("t1", "zh-CN", "demo", {"version": 2}, 60)
    assert await inner.aget(key) == {"version": 2}
    # L1 命中直接返回。
    assert await region.aget_type("t1", "zh-CN", "demo") == {"version": 2}

    await region.adrop_type("t1", "zh-CN", "demo")
    assert await region.aget_type("t1", "zh-CN", "demo") is None

    # 同步 `get`：L1 缺失后从 Redis 回填。
    inner.set("k2", "v2")
    assert region.get("k2") == "v2"
    assert region.get("missing") is None
    assert region.delete("k") is True

    await region.aclose()


async def test_redis_region_id_subset_versions_and_lock() -> None:
    """Redis 实现：按条目 id 子集（Redis 命中回填 / 未命中空）、版本 `INCR` 与非数字版本回落、SETNX 锁。"""
    region = _redis_region()
    inner = region.redis_region

    # Redis 层预置映射（L1 为空；JSON 键为字符串化 id）→ 读时回填 L1。
    subset_key = region.id_cache_key("t1", "zh-CN", "demo")
    await inner.aset(subset_key, {"1": "A"})
    assert await region.aid_subset("t1", "zh-CN", "demo", ConcurrentStableList([1, 99])) == {1: "A"}
    assert region.get(subset_key) is not None

    # 完全未命中 → 空映射。
    assert await region.aid_subset("t1", "zh-CN", "other", ConcurrentStableList([1])) == {}

    # L1 与 Redis 都缺时写子集（无既有映射可合并）。
    only: ConcurrentStableDict[int, str] = ConcurrentStableDict()
    only.set(5, "X")
    await region.aset_id_subset("t1", "zh-CN", "fresh", only)
    assert await region.aid_subset("t1", "zh-CN", "fresh", ConcurrentStableList([5])) == {5: "X"}

    # L1 已有映射（命中）→ 直接合并，不再回查 Redis。
    again: ConcurrentStableDict[int, str] = ConcurrentStableDict()
    again.set(6, "W")
    await region.aset_id_subset("t1", "zh-CN", "fresh", again)
    assert await region.aid_subset("t1", "zh-CN", "fresh", ConcurrentStableList([5, 6])) == {
        5: "X",
        6: "W",
    }

    # L1 缺、Redis 有映射 → 合并后整体写入。
    await inner.aset(region.id_cache_key("t1", "zh-CN", "fresh2"), {"1": "X"})
    merged_src: ConcurrentStableDict[int, str] = ConcurrentStableDict()
    merged_src.set(2, "Y")
    await region.aset_id_subset("t1", "zh-CN", "fresh2", merged_src)
    assert await region.aid_subset("t1", "zh-CN", "fresh2", ConcurrentStableList([1, 2])) == {
        1: "X",
        2: "Y",
    }

    # 版本：按租户 `INCR`；全局版本经同步客户端读取；非数字回落 0。
    assert await region.aincrease_version("t1") == 1
    assert await region.aversion("t1") == 1
    assert await region.aincrease_version(None) == 1
    assert region.get_global_version() == 1
    await inner.aset(region.version_cache_key("t1"), "not-a-number")
    assert await region.aversion("t1") == 0

    # SETNX 互斥锁 + 令牌释放。
    assert await region.alock("t1", "zh-CN", "demo", "tok") is True
    assert await region.arelease_lock("t1", "zh-CN", "demo", "tok") is True


def test_di_providers_resolve_dict_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    """依赖注入提供者：经 `app.state.settings` 解析字典取数 / 翻译 / 缓存域三契约。"""
    sentinel = object()

    def _resolve(*_args: object, **_kwargs: object) -> object:
        return sentinel

    monkeypatch.setattr("bms_core.dict.base.resolve_plugin", _resolve)
    settings = get_settings()
    request = cast("Any", SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings))))
    assert get_data_source(request) is sentinel
    assert get_dict_translator(request) is sentinel
    assert get_dict_cache_region(request) is sentinel
