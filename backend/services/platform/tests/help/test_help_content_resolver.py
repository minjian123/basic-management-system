"""帮助内容解析实现测试：来源优先级 / 相关内容 / 分类 / 语言回退（08_03）。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.db.session import DbSession
from bms_core.help.content import HelpAnchorCandidate, HelpContentQuery, HelpLevel
from bms_core.help.values import (
    ARTICLE_SOURCE_BUILTIN,
    ARTICLE_SOURCE_PRODUCT,
    ARTICLE_SOURCE_TENANT,
    ARTICLE_STATUS_PUBLISHED,
)
from bms_core.models.platform.help import SysHelpArticle, SysHelpArticleTarget, SysHelpCategory
from bms_core.testing.namespace import Namespace
from bms_core.testing.transaction import rollback_session
from bms_platform.domains.help.package_spec import load_package
from bms_platform.domains.help.services.package import HelpPackageService
from bms_platform.domains.help.services.resolver import DatabaseHelpContentResolver

from ._support import anchor_map, form_key, module_key, session_opener, write_package

pytestmark = pytest.mark.kiwi_id(2522)


def _query(level: HelpLevel, key: str, locale: str = "zh-CN") -> HelpContentQuery:
    """构造解析请求。

    Args:
        level: 层级。
        key: 锚点键。
        locale: 请求语言。

    Returns:
        HelpContentQuery: 解析请求。
    """
    return HelpContentQuery(
        locale=locale,
        candidates=ConcurrentStableFrozenList(
            (
                HelpAnchorCandidate(level=level, help_key=key),
                HelpAnchorCandidate(level=HelpLevel.GLOBAL, help_key=None),
            )
        ),
    )


async def test_loaded_article_is_resolved_and_locale_fallback(
    shared_tenant_engine: AsyncEngine, tmp_path: Path, ns: Namespace
) -> None:
    """装载后五级解析可命中；语言按请求 → 默认 → 主表快照回退。"""
    package = write_package(tmp_path / "pkg", product_key=ns.prefix, prefix=ns.prefix)
    spec = load_package(package)
    async with rollback_session(shared_tenant_engine) as session:
        await HelpPackageService(session).load(spec, anchors=anchor_map(ns.prefix), apply=True, lenient=False)
        resolver = DatabaseHelpContentResolver(session_opener=lambda: session_opener(session))
        zh = await resolver.resolve(_query(HelpLevel.MODULE, module_key(ns.prefix)))
        assert zh.matched
        assert zh.level == HelpLevel.MODULE
        assert zh.help_key == module_key(ns.prefix)
        assert zh.article is not None
        assert zh.article.title == f"{ns.prefix} 标题"
        en = await resolver.resolve(_query(HelpLevel.MODULE, module_key(ns.prefix), "en-US"))
        assert en.article is not None
        assert en.article.title.endswith("(EN)")
        fallback = await resolver.resolve(_query(HelpLevel.MODULE, module_key(ns.prefix), "fr-FR"))
        assert fallback.article is not None
        assert fallback.article.title == f"{ns.prefix} 标题"
        miss = await resolver.resolve(_query(HelpLevel.FORM, form_key(ns.prefix)))
        assert not miss.matched
        assert any(item.name == f"{ns.prefix}_cat" for item in miss.categories)


async def test_source_priority_and_related(shared_tenant_engine: AsyncEngine, tmp_path: Path, ns: Namespace) -> None:
    """同目标多篇按 builtin > product > tenant 取一篇，其余进相关内容。"""
    package = write_package(tmp_path / "pkg", product_key=ns.prefix, prefix=ns.prefix)
    spec = load_package(package)
    target = module_key(f"{ns.prefix}_p")
    async with rollback_session(shared_tenant_engine) as session:
        await HelpPackageService(session).load(spec, anchors=anchor_map(ns.prefix), apply=True, lenient=False)
        category = (
            (await session.execute(select(SysHelpCategory).where(SysHelpCategory.name == f"{ns.prefix}_cat")))
            .scalars()
            .first()
        )
        assert category is not None
        for index, source in enumerate((ARTICLE_SOURCE_TENANT, ARTICLE_SOURCE_PRODUCT, ARTICLE_SOURCE_BUILTIN)):
            article = SysHelpArticle(
                category_id=int(category.id),
                title=f"{source}-{index}",
                content="<p>x</p>",
                status=ARTICLE_STATUS_PUBLISHED,
                source=source,
                source_key=f"{ns.prefix}.{source}.{index}",
                package_id=None,
                local_override=False,
                generated_by="manual",
            )
            session.add(article)
            await session.flush()
            session.add(SysHelpArticleTarget(article_id=int(article.id), target_type="module", target_key=target))
        await session.flush()
        resolver = DatabaseHelpContentResolver(session_opener=lambda: session_opener(session))
        result = await resolver.resolve(_query(HelpLevel.MODULE, target))
        assert result.article is not None
        assert result.article.source == ARTICLE_SOURCE_BUILTIN
        assert [item.source for item in result.related] == [ARTICLE_SOURCE_PRODUCT, ARTICLE_SOURCE_TENANT]


async def test_resolver_degrades_when_database_unavailable(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """库不可用时返回空结果（不阻断页面）。"""

    @asynccontextmanager
    async def _failing() -> AsyncGenerator[DbSession]:
        raise OperationalError("select 1", {}, Exception("boom"))
        yield  # pragma: no cover - 不可达（只为满足异步生成器形态）

    resolver = DatabaseHelpContentResolver(session_opener=_failing)
    result = await resolver.resolve(_query(HelpLevel.MODULE, module_key(ns.prefix)))
    assert not result.matched
