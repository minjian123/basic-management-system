"""帮助内容解析缓存（数据库实现层）：命中 / 版本失效 / 未命中不缓存（Kiwi 2529）。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

import pytest

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import (
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.db.session import DbSession
from bms_core.help.cache import bump_content_version
from bms_core.help.content import (
    HelpAnchorCandidate,
    HelpArticle,
    HelpCategory,
    HelpContentQuery,
    HelpContentResult,
    HelpLevel,
)
from bms_platform.domains.help.repositories.content import HelpContentRepository
from bms_platform.domains.help.services.resolver import DatabaseHelpContentResolver

pytestmark = pytest.mark.kiwi_id(2529)


@asynccontextmanager
async def _opener() -> AsyncGenerator[DbSession]:
    """测试会话开合口（仓储方法被打桩，不真正查库）。

    Yields:
        DbSession: 占位会话。
    """
    yield cast("DbSession", object())


def _query() -> HelpContentQuery:
    """构造只含全局候选的解析请求。

    Returns:
        HelpContentQuery: 解析请求。
    """
    return HelpContentQuery(
        locale="zh-CN",
        candidates=ConcurrentStableFrozenList((HelpAnchorCandidate(level=HelpLevel.GLOBAL, help_key=None),)),
    )


def _matched() -> HelpContentResult:
    """构造命中结果。

    Returns:
        HelpContentResult: 命中结果。
    """
    return HelpContentResult(
        level=HelpLevel.GLOBAL,
        article=HelpArticle(article_id=1, title="快速上手", content="<p>正文</p>", source="tenant"),
        categories=ConcurrentStableFrozenList((HelpCategory(category_id=10, name="快速上手", path="快速上手"),)),
    )


async def test_resolve_cache_hit_and_invalidate(monkeypatch: pytest.MonkeyPatch) -> None:
    """二次解析命中缓存；内容版本递增后回源。"""
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    async def _resolve(self: HelpContentRepository, query: HelpContentQuery) -> HelpContentResult:
        """仓储打桩：记录调用并返回命中结果。"""
        del self, query
        calls.add("call")
        return _matched()

    monkeypatch.setattr(HelpContentRepository, "resolve", _resolve)
    cache = MemoryCacheRegion()
    resolver = DatabaseHelpContentResolver(cache=cache, session_opener=_opener)
    first = await resolver.resolve(_query())
    second = await resolver.resolve(_query())
    assert first.matched is True and second.matched is True
    assert len(calls) == 1
    await bump_content_version(cache, tenant=None)
    third = await resolver.resolve(_query())
    assert third.matched is True
    assert len(calls) == 2


async def test_resolve_miss_is_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """未命中不写缓存（内容写入后立即生效）。"""
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    async def _resolve(self: HelpContentRepository, query: HelpContentQuery) -> HelpContentResult:
        """仓储打桩：记录调用并返回未命中。"""
        del self, query
        calls.add("call")
        return HelpContentResult()

    monkeypatch.setattr(HelpContentRepository, "resolve", _resolve)
    resolver = DatabaseHelpContentResolver(cache=MemoryCacheRegion(), session_opener=_opener)
    first = await resolver.resolve(_query())
    second = await resolver.resolve(_query())
    assert first.matched is False and second.matched is False
    assert len(calls) == 2
