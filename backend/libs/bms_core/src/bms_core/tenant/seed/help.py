"""帮助内容种子：三分类 + 三篇双语基础文章（幂等、只增不改，12_01）。

**口径**（概要 17 §6）：

- 分类：快速上手 / 系统管理 / 业务操作（根级，`sort` 10 / 20 / 30）；
- 文章：快速上手挂全局锚点（页面内帮助全不命中时的兜底内容），系统管理与业务操作只按分类阅读；
- 每篇 `zh-CN` + `en-US` 双语、`published`、`source=tenant`；主表标题 / 正文取默认语言快照（本种子用中文）；
- **只增不改**：分类按「根级同名」查活行；文章按「该分类是否已有租户自建文章」判定——
  已有内容即整类跳过，运营改名 / 改内容后重跑不会覆盖也不会重复插入。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList
from bms_core.core.objects import BaseValueObject
from bms_core.db.session import DbSession
from bms_core.help.values import (
    ARTICLE_SOURCE_TENANT,
    ARTICLE_STATUS_PUBLISHED,
    GENERATED_BY_MANUAL,
    TARGET_TYPE_GLOBAL,
)
from bms_core.models.platform.help import SysHelpArticle, SysHelpArticleI18n, SysHelpArticleTarget, SysHelpCategory

__all__ = [
    "HELP_SEED_ARTICLES",
    "HELP_SEED_CATEGORIES",
    "HelpSeedOutcome",
    "seed_help_content",
    "seed_help_entry",
]

SEED_LOCALE_ZH = "zh-CN"
"""种子中文语言标识。"""

SEED_LOCALE_EN = "en-US"
"""种子英文语言标识。"""


@dataclass(frozen=True)
class HelpCategorySpec(BaseValueObject):
    """帮助分类种子声明。"""

    name: str
    """分类名（默认语言快照）。"""
    sort: int
    """同级排序。"""


@dataclass(frozen=True)
class HelpArticleSpec(BaseValueObject):
    """帮助文章种子声明。"""

    category_name: str
    """所属分类名（根级）。"""
    title: str
    """中文标题（主表快照）。"""
    title_en: str
    """英文标题（多语言附表）。"""
    content: str
    """中文正文（已净化 HTML）。"""
    content_en: str
    """英文正文（已净化 HTML）。"""
    global_target: bool
    """是否挂全局锚点（`target_type=global`）。"""


HELP_SEED_CATEGORIES: ConcurrentStableFrozenList[HelpCategorySpec] = ConcurrentStableFrozenList(
    (
        HelpCategorySpec(name="快速上手", sort=10),
        HelpCategorySpec(name="系统管理", sort=20),
        HelpCategorySpec(name="业务操作", sort=30),
    )
)
"""根级分类清单。"""

HELP_SEED_ARTICLES: ConcurrentStableFrozenList[HelpArticleSpec] = ConcurrentStableFrozenList(
    (
        HelpArticleSpec(
            category_name="快速上手",
            title="快速上手：认识平台",
            title_en="Getting started: platform overview",
            content=(
                "<h2>认识平台</h2>"
                "<p>平台由工作台、菜单与表单三部分构成：工作台汇总待办与常用入口，菜单进入各业务功能，"
                "表单完成录入与查询。</p>"
                "<p>右上角的帮助按钮会按当前页面给出对应说明；也可以打开帮助中心按分类浏览。</p>"
            ),
            content_en=(
                "<h2>Platform overview</h2>"
                "<p>The platform consists of the dashboard, menus and forms: the dashboard summarizes to-dos "
                "and shortcuts, menus lead to business functions, and forms handle entry and queries.</p>"
                "<p>The help button in the top-right corner shows context help for the current page; you can also "
                "browse the help center by category.</p>"
            ),
            global_target=True,
        ),
        HelpArticleSpec(
            category_name="系统管理",
            title="系统管理：账号与权限",
            title_en="System management: accounts and permissions",
            content=(
                "<h2>账号与权限</h2>"
                "<p>账号由管理员创建并分配角色；角色决定可见菜单与可执行动作，权限码控制到按钮级。</p>"
                "<p>如需新增权限，请联系系统管理员在角色管理中授权后重新登录生效。</p>"
            ),
            content_en=(
                "<h2>Accounts and permissions</h2>"
                "<p>Accounts are created by administrators and assigned roles. Roles determine visible menus and "
                "available actions, with permission codes controlling button-level access.</p>"
                "<p>To request new permissions, contact your system administrator to grant them in role management, "
                "then sign in again.</p>"
            ),
            global_target=False,
        ),
        HelpArticleSpec(
            category_name="业务操作",
            title="业务操作：单据处理流程",
            title_en="Business operations: document workflow",
            content=(
                "<h2>单据处理流程</h2>"
                "<p>业务单据按「新建 → 提交 → 审批 → 完成」流转；列表页可按状态筛选，表单页保存后进入待提交状态。</p>"
                "<p>审批被驳回时，单据回到新建人处修改后重新提交；已完成的单据不可直接修改。</p>"
            ),
            content_en=(
                "<h2>Document workflow</h2>"
                "<p>Business documents flow through draft → submit → approve → complete. Use the list page to filter "
                "by status; a saved form enters the pending-submit state.</p>"
                "<p>Rejected documents return to the creator for edits and resubmission; completed documents cannot be "
                "modified directly.</p>"
            ),
            global_target=False,
        ),
    )
)
"""基础文章清单（三篇，覆盖全局兜底与两个分类）。"""


@dataclass(frozen=True)
class HelpSeedOutcome(BaseValueObject):
    """种子执行结果（逐项计数，供编排报告与用例断言）。"""

    created_categories: int = 0
    """新建分类数。"""
    created_articles: int = 0
    """新建文章数。"""
    created_texts: int = 0
    """新增多语言文案行数。"""


async def _category(session: DbSession, name: str) -> SysHelpCategory | None:
    """按根级分类名取活行。

    Args:
        session: 目标租户库会话。
        name: 分类名。

    Returns:
        SysHelpCategory | None: 分类行；不存在为 None。
    """
    statement = (
        select(SysHelpCategory)
        .where(SysHelpCategory.parent_id == 0)
        .where(SysHelpCategory.name == name)
        .where(SysHelpCategory.deleted_at.is_(None))
    )
    return (await session.execute(statement)).scalars().first()


async def _has_tenant_article(session: DbSession, category_id: int) -> bool:
    """判断分类下是否已有租户自建文章（存在即跳过该分类的种子文章）。

    Args:
        session: 目标租户库会话。
        category_id: 分类主键。

    Returns:
        bool: 已有文章为 True。
    """
    statement = (
        select(SysHelpArticle.id)
        .where(SysHelpArticle.category_id == category_id)
        .where(SysHelpArticle.source == ARTICLE_SOURCE_TENANT)
        .where(SysHelpArticle.deleted_at.is_(None))
        .limit(1)
    )
    return (await session.execute(statement)).scalars().first() is not None


async def seed_help_content(session: DbSession) -> HelpSeedOutcome:
    """写入帮助分类、基础文章、双语文案与全局锚点（幂等、只增不改）。

    Args:
        session: 目标租户库会话（编排层负责事务提交）。

    Returns:
        HelpSeedOutcome: 逐项计数。
    """
    created_categories = 0
    category_ids: ConcurrentStableDict[str, int] = ConcurrentStableDict()
    for spec in HELP_SEED_CATEGORIES:
        existing = await _category(session, spec.name)
        if existing is None:
            row = SysHelpCategory(parent_id=0, name=spec.name, sort=spec.sort, status="enabled")
            session.add(row)
            await session.flush()
            created_categories += 1
            existing = row
        category_ids.set(spec.name, int(existing.id))
    created_articles = 0
    created_texts = 0
    for spec in HELP_SEED_ARTICLES:
        category_id = category_ids.get(spec.category_name)
        if category_id is None:  # pragma: no cover - 分类清单与文章清单同源，缺分类属声明错误
            continue
        if await _has_tenant_article(session, category_id):
            continue
        article = SysHelpArticle(
            category_id=category_id,
            title=spec.title,
            content=spec.content,
            status=ARTICLE_STATUS_PUBLISHED,
            is_top=False,
            source=ARTICLE_SOURCE_TENANT,
            generated_by=GENERATED_BY_MANUAL,
            view_count=0,
            helpful_count=0,
            unhelpful_count=0,
        )
        session.add(article)
        await session.flush()
        created_articles += 1
        session.add(
            SysHelpArticleI18n(
                article_id=int(article.id),
                locale=SEED_LOCALE_ZH,
                title=spec.title,
                content=spec.content,
            )
        )
        session.add(
            SysHelpArticleI18n(
                article_id=int(article.id),
                locale=SEED_LOCALE_EN,
                title=spec.title_en,
                content=spec.content_en,
            )
        )
        created_texts += 2
        if spec.global_target:
            session.add(
                SysHelpArticleTarget(
                    article_id=int(article.id),
                    target_type=TARGET_TYPE_GLOBAL,
                    target_key="",
                )
            )
        await session.flush()
    return HelpSeedOutcome(
        created_categories=created_categories,
        created_articles=created_articles,
        created_texts=created_texts,
    )


async def seed_help_entry(session: DbSession, args: ConcurrentStableDict[str, object]) -> None:
    """XA 分支入口（种子编排调用）：在分支会话内幂等写入帮助内容种子。

    Args:
        session: 已绑定 XA 分支连接的会话。
        args: 分支参数（本种子不消费）。
    """
    del args
    await seed_help_content(session)
