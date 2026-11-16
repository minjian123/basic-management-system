"""帮助内容侧端口：值对象、空实现与依赖解析（08_02；Kiwi 2521）。"""

from types import SimpleNamespace
from typing import cast

import pytest

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.core.plugin import build_plugin_registry
from bms_core.help.content import (
    HELP_CONTENT_PLUGIN_KEY,
    BaseHelpContentResolver,
    HelpArticle,
    HelpArticleSummary,
    HelpCategory,
    HelpContentQuery,
    HelpContentResult,
    HelpLevel,
    get_help_content_resolver,
)
from bms_core.help.null import NullHelpContentResolver

pytestmark = pytest.mark.kiwi_id(2521)


def test_help_level_values() -> None:
    """五级取值与字符串形态稳定（接口 `level` 字段直接取用）。"""
    assert [level.value for level in HelpLevel] == ["field", "action", "form", "module", "global"]


async def test_null_resolver_returns_empty_result() -> None:
    """空实现恒定未命中：无文章 / 无相关内容 / 无分类，且不反噬调用方。"""
    resolver = NullHelpContentResolver()
    query = HelpContentQuery(locale="zh-CN", candidates=ConcurrentStableFrozenList())
    result = await resolver.resolve(query)
    assert result.matched is False
    assert result.level is None
    assert result.help_key is None
    assert result.article is None
    assert list(result.related) == []
    assert list(result.categories) == []


def test_result_matched_only_when_article_present() -> None:
    """命中判据只看文章：有文章即命中，相关内容与分类原样透出。"""
    result = HelpContentResult(
        level=HelpLevel.FORM,
        help_key="platform:probe:probe_form::",
        article=HelpArticle(article_id=1, title="标题", content="<p>正文</p>", source="builtin"),
        related=ConcurrentStableFrozenList([HelpArticleSummary(article_id=2, title="相关内容", source="product")]),
        categories=ConcurrentStableFrozenList([HelpCategory(category_id=3, name="快速上手", path="快速上手")]),
    )
    assert result.matched is True
    assert result.related[0].title == "相关内容"
    assert result.categories[0].path == "快速上手"


def test_get_help_content_resolver_resolves_null_provider() -> None:
    """配置 provider 为空串 → 解析到空实现（与 permission / preference 同口径）。"""
    build_plugin_registry()
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(help_content=SimpleNamespace(provider=""))))
    )
    resolver = get_help_content_resolver(cast("object", request))  # pyright: ignore[reportArgumentType]
    assert isinstance(resolver, NullHelpContentResolver)
    assert isinstance(resolver, BaseHelpContentResolver)
    assert resolver.plugin_key == HELP_CONTENT_PLUGIN_KEY
