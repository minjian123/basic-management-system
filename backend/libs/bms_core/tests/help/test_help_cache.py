"""帮助内容缓存：版本键 / 缓存键 / 编解码 / 降级（12_01）。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

import pytest

from bms_core.cache.base import CacheRegion
from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.exceptions import RedisUnavailableError
from bms_core.help.cache import (
    bump_content_version,
    content_version,
    content_version_key,
    decode_help_result,
    encode_help_result,
    load_cached_result,
    resolve_cache_key,
    store_cached_result,
)
from bms_core.help.content import (
    HelpAnchorCandidate,
    HelpArticle,
    HelpArticleSummary,
    HelpCategory,
    HelpContentResult,
    HelpLevel,
)


class _BrokenCache(CacheRegion):
    """不可用缓存替身（读写均抛 `RedisUnavailableError`）。"""

    @property
    def domain(self) -> str:
        """业务域。

        Returns:
            str: 域简称。
        """
        return "broken"

    def get(self, key: str) -> object | None:
        """读缓存（恒失败）。"""
        raise RedisUnavailableError("cache down")

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        """写缓存（恒失败）。"""
        raise RedisUnavailableError("cache down")

    def delete(self, key: str) -> bool:
        """删缓存（恒失败）。"""
        raise RedisUnavailableError("cache down")

    def get_global_version(self) -> int:
        """全局版本号。

        Returns:
            int: 恒 0。
        """
        return 0

    async def aget(self, key: str) -> object | None:
        """异步读（恒失败）。"""
        raise RedisUnavailableError("cache down")

    async def aset(self, key: str, value: object, ttl: int | None = None) -> None:
        """异步写（恒失败）。"""
        raise RedisUnavailableError("cache down")

    async def aincrease(self, key: str) -> int:
        """原子自增（恒失败）。"""
        raise RedisUnavailableError("cache down")


@asynccontextmanager
async def _memory() -> AsyncGenerator[MemoryCacheRegion]:
    """内存 Region 上下文。

    Yields:
        MemoryCacheRegion: 内存缓存。
    """
    yield MemoryCacheRegion()


def _result() -> HelpContentResult:
    """构造一份带文章 / 相关内容 / 分类的解析结果。

    Returns:
        HelpContentResult: 解析结果。
    """
    return HelpContentResult(
        level=HelpLevel.FIELD,
        help_key="platform:sys:user:username:",
        article=HelpArticle(
            article_id=1,
            title="用户名",
            content="<p>登录账号</p>",
            source="builtin",
        ),
        related=ConcurrentStableFrozenList((HelpArticleSummary(article_id=2, title="账号安全", source="product"),)),
        categories=ConcurrentStableFrozenList((HelpCategory(category_id=10, name="系统管理", path="系统管理"),)),
    )


def test_content_version_key_uses_help_domain() -> None:
    """版本键遵循 `bms:{tenant}:help:content_version`。"""
    assert content_version_key(tenant="demo") == "bms:demo:help:content_version"
    assert content_version_key(tenant=None) == "bms:global:help:content_version"


async def test_version_bump_and_read() -> None:
    """版本号递增可读；缓存不可用时读 0、写返回 None。"""
    async with _memory() as cache:
        assert await content_version(cache, tenant="demo") == 0
        assert await bump_content_version(cache, tenant="demo") == 1
        assert await content_version(cache, tenant="demo") == 1
    broken = _BrokenCache()
    assert await content_version(broken, tenant="demo") == 0
    assert await bump_content_version(broken, tenant="demo") is None


def test_resolve_cache_key_stable_and_discriminating() -> None:
    """同一候选 / 语言 / 版本键稳定；任一维度变化即换键。"""
    candidates: ConcurrentStableList[HelpAnchorCandidate] = ConcurrentStableList(
        (
            HelpAnchorCandidate(level=HelpLevel.FIELD, help_key="platform:sys:user:username:"),
            HelpAnchorCandidate(level=HelpLevel.GLOBAL, help_key=None),
        )
    )
    first = resolve_cache_key(tenant="demo", version=1, locale="zh-CN", candidates=candidates)
    second = resolve_cache_key(tenant="demo", version=1, locale="zh-CN", candidates=candidates)
    assert first == second
    assert first.startswith("bms:demo:help:resolve:v1:zh-CN:")
    assert resolve_cache_key(tenant="demo", version=2, locale="zh-CN", candidates=candidates) != first
    assert resolve_cache_key(tenant="demo", version=1, locale="en-US", candidates=candidates) != first
    other: ConcurrentStableList[HelpAnchorCandidate] = ConcurrentStableList(
        (HelpAnchorCandidate(level=HelpLevel.GLOBAL, help_key=None),)
    )
    assert resolve_cache_key(tenant="demo", version=1, locale="zh-CN", candidates=other) != first


def test_encode_decode_roundtrip() -> None:
    """编解码往返保持结构（JSON 可序列化）。"""
    result = _result()
    payload = encode_help_result(result)
    assert isinstance(payload, dict)
    decoded = decode_help_result(cast("dict[str, object]", payload))
    assert decoded is not None
    assert decoded.level == HelpLevel.FIELD
    assert decoded.help_key == result.help_key
    assert decoded.article is not None and decoded.article.article_id == 1
    assert [item.article_id for item in decoded.related] == [2]
    assert [item.category_id for item in decoded.categories] == [10]


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "x",
        {"level": "unknown"},
        {"level": 1},
        {"help_key": 1},
        {"article": "x"},
        {"article": {"article_id": "x"}},
        {"article": {"article_id": 1, "title": 1}},
        {"related": "x"},
        {"related": [1]},
        {"related": [{"article_id": 1}]},
        {"related": [{"article_id": "x", "title": "t", "source": "s"}]},
        {"related": [], "categories": "x"},
        {"related": [], "categories": [1]},
        {"related": [], "categories": [{"category_id": "x", "name": "n", "path": "p"}]},
        {"related": [], "categories": [{"category_id": 1, "name": 1, "path": "p"}]},
        {"categories": "x"},
        {"categories": [1]},
        {"categories": [{"category_id": 1}]},
    ],
)
def test_decode_dirty_payload_returns_none(payload: object) -> None:
    """脏载荷一律返回 None（由调用方回源重建）。"""
    assert decode_help_result(payload) is None


def test_miss_result_roundtrip() -> None:
    """未命中结果（空文章 + 分类）可往返。"""
    result = HelpContentResult(
        categories=ConcurrentStableFrozenList((HelpCategory(category_id=1, name="快速上手", path="快速上手"),))
    )
    decoded = decode_help_result(encode_help_result(result))
    assert decoded is not None
    assert decoded.matched is False
    assert decoded.level is None
    assert [item.name for item in decoded.categories] == ["快速上手"]


async def test_cache_read_write_and_broken_cache() -> None:
    """命中可读；缓存不可用时读写均降级为空操作。"""
    result = _result()
    async with _memory() as cache:
        await store_cached_result(cache, "k", result)
        loaded = await load_cached_result(cache, "k")
        assert loaded is not None and loaded.article is not None
        assert await load_cached_result(cache, "missing") is None
    broken = _BrokenCache()
    assert await load_cached_result(broken, "k") is None
    await store_cached_result(broken, "k", result)
