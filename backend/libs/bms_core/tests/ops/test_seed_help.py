"""帮助内容种子：三分类 + 三篇双语文章、幂等只增不改（12_01）。"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, update

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import get_settings
from bms_core.models.platform.help import (
    SysHelpArticle,
    SysHelpArticleI18n,
    SysHelpArticleTarget,
    SysHelpCategory,
)
from bms_core.tenant.seed.help import (
    HELP_SEED_ARTICLES,
    HELP_SEED_CATEGORIES,
    seed_help_content,
    seed_help_entry,
)
from tests_support.help import memory_help_session


@pytest.fixture(autouse=True)
def _disable_field_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    """关闭字段级审计捕获（内存库无发件箱表；种子用例只验证种子语义）。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
    """
    monkeypatch.setattr(get_settings().audit_capture, "enabled", False)


async def test_seed_creates_categories_articles_and_texts() -> None:
    """首跑：3 分类 + 3 文章 + 6 语言行 + 1 全局目标。"""
    async with memory_help_session() as session:
        outcome = await seed_help_content(session)
        await session.commit()
        assert outcome.created_categories == len(HELP_SEED_CATEGORIES) == 3
        assert outcome.created_articles == len(HELP_SEED_ARTICLES) == 3
        assert outcome.created_texts == 6
        categories = (await session.execute(select(func.count()).select_from(SysHelpCategory))).scalar_one()
        articles = (await session.execute(select(func.count()).select_from(SysHelpArticle))).scalar_one()
        texts = (await session.execute(select(func.count()).select_from(SysHelpArticleI18n))).scalar_one()
        targets = (await session.execute(select(func.count()).select_from(SysHelpArticleTarget))).scalar_one()
        assert (categories, articles, texts, targets) == (3, 3, 6, 1)


async def test_seed_is_idempotent() -> None:
    """重跑零新增（分类与文章均按稳定判据跳过）。"""
    async with memory_help_session() as session:
        await seed_help_content(session)
        await session.commit()
        outcome = await seed_help_content(session)
        await session.commit()
        assert (outcome.created_categories, outcome.created_articles, outcome.created_texts) == (0, 0, 0)


async def test_seed_does_not_override_tenant_edits() -> None:
    """运营改名 / 改正文后重跑：不覆盖、不重复插入。"""
    async with memory_help_session() as session:
        await seed_help_content(session)
        await session.commit()
        article = (await session.execute(select(SysHelpArticle).order_by(SysHelpArticle.id))).scalars().first()
        assert article is not None
        await session.execute(
            update(SysHelpArticle)
            .where(SysHelpArticle.id == article.id)
            .values(title="运营改过的标题", content="<p>运营改过的正文</p>")
        )
        await session.commit()
        outcome = await seed_help_content(session)
        await session.commit()
        assert outcome.created_articles == 0
        refreshed = (await session.execute(select(SysHelpArticle).where(SysHelpArticle.id == article.id))).scalar_one()
        assert refreshed.title == "运营改过的标题"
        count = (await session.execute(select(func.count()).select_from(SysHelpArticle))).scalar_one()
        assert count == 3


async def test_seed_entry_is_idempotent() -> None:
    """XA 分支入口重复执行不新增（种子编排调用）。"""
    async with memory_help_session() as session:
        await seed_help_entry(session, ConcurrentStableDict())
        await seed_help_entry(session, ConcurrentStableDict())
        await session.commit()
        categories = (await session.execute(select(func.count()).select_from(SysHelpCategory))).scalar_one()
        articles = (await session.execute(select(func.count()).select_from(SysHelpArticle))).scalar_one()
        assert (categories, articles) == (3, 3)


async def test_seed_skips_disabled_existing_category() -> None:
    """同名分类已存在（含停用）时不重建、不重复。"""
    async with memory_help_session() as session:
        session.add(SysHelpCategory(parent_id=0, name=HELP_SEED_CATEGORIES[0].name, sort=99, status="disabled"))
        await session.commit()
        outcome = await seed_help_content(session)
        await session.commit()
        assert outcome.created_categories == len(HELP_SEED_CATEGORIES) - 1
        rows = (await session.execute(select(SysHelpCategory).where(SysHelpCategory.parent_id == 0))).scalars().all()
        assert len(rows) == len(HELP_SEED_CATEGORIES)
