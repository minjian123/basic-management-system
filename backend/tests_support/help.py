"""帮助内容用例的数据库辅助（共享基座：**唯一允许建引擎的位置**）。

隔离口径：单库叠加下全 worker 共用一份租户库，本模块只用**用例命名空间**派生分类名 / 文章标题，
不做整表清理；按需清理只针对本用例自造行（标题 / 分类名精确匹配）。
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.help.values import (
    ARTICLE_SOURCE_TENANT,
    ARTICLE_STATUS_PUBLISHED,
    GENERATED_BY_MANUAL,
    PACKAGE_STATUS_LOADED,
    TARGET_TYPE_GLOBAL,
)
from bms_core.models.base import Base
from bms_core.models.platform.help import (
    SysHelpArticle,
    SysHelpArticleI18n,
    SysHelpArticleTarget,
    SysHelpCategory,
    SysHelpFeedback,
    SysHelpPackage,
)
from bms_core.models.platform.i18n import SysI18nLocale
from bms_core.models.platform.permission_meta import SysAction

__all__ = [
    "HELP_MODELS",
    "delete_platform_action",
    "ensure_help_tables",
    "help_session",
    "memory_help_session",
    "memory_locale_session",
    "platform_url",
    "seed_article",
    "seed_category",
    "seed_package",
    "seed_platform_action",
    "tenant_url",
]

HELP_MODELS: ConcurrentStableList[Any] = ConcurrentStableList(
    (
        SysHelpCategory,
        SysHelpArticle,
        SysHelpArticleI18n,
        SysHelpArticleTarget,
        SysHelpPackage,
        SysHelpFeedback,
    )
)
"""帮助内容六表（只用于「确保存在」，不做清场）。"""


def tenant_url() -> str:
    """当前用例的共享测试租户库连接串。

    Returns:
        str: 租户库连接串。
    """
    return os.environ["BMS_DATABASE__TENANTS__URL"]


@asynccontextmanager
async def help_session(url: str) -> AsyncGenerator[AsyncSession]:
    """建共享库会话（调用方负责 commit / rollback）。

    Args:
        url: 租户库连接串。

    Yields:
        AsyncSession: 异步会话。
    """
    engine = create_async_engine(  # own_db: 共享基座模块内建引擎（测试库隔离护栏放行点）
        url,
        pool_pre_ping=True,
    )
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


async def ensure_help_tables(url: str) -> None:
    """确保帮助内容六表存在（缺则建；不清空）。

    Args:
        url: 数据库连接串。
    """
    engine = create_async_engine(  # own_db: 共享基座模块内建引擎（测试库隔离护栏放行点）
        url,
        pool_pre_ping=True,
    )
    try:
        tables = [cast("Table", model.__table__) for model in HELP_MODELS]
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables))
    finally:
        await engine.dispose()


@asynccontextmanager
async def memory_help_session() -> AsyncGenerator[AsyncSession]:
    """进程内内存库会话（帮助六表已建；种子类用例专用，避免污染共享测试库）。

    Yields:
        AsyncSession: 会话（退出时释放引擎）。
    """
    engine = create_async_engine(  # own_db: 共享基座模块内建引擎（测试库隔离护栏放行点）
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    try:
        tables = [cast("Table", model.__table__) for model in HELP_MODELS]
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


@asynccontextmanager
async def memory_locale_session() -> AsyncGenerator[AsyncSession]:
    """进程内内存库会话（仅语言清单表；语言校验用例专用）。

    Yields:
        AsyncSession: 会话（退出时释放引擎）。
    """
    engine = create_async_engine(  # own_db: 共享基座模块内建引擎（测试库隔离护栏放行点）
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    try:
        tables = [cast("Table", SysI18nLocale.__table__)]
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


async def seed_category(
    url: str,
    *,
    name: str,
    parent_id: int = 0,
    sort: int = 0,
    status: str = "enabled",
) -> int:
    """直接插入一个分类并返回主键。

    Args:
        url: 租户库连接串。
        name: 分类名（调用方负责命名空间唯一）。
        parent_id: 上级分类 ID（0 = 根）。
        sort: 排序。
        status: 状态。

    Returns:
        int: 分类主键。
    """
    await ensure_help_tables(url)
    async with help_session(url) as session:
        row = SysHelpCategory(parent_id=parent_id, name=name, sort=sort, status=status)
        session.add(row)
        await session.commit()
        return int(row.id)


async def seed_article(
    url: str,
    *,
    category_id: int,
    title: str,
    content: str = "<p>帮助正文</p>",
    status: str = ARTICLE_STATUS_PUBLISHED,
    source: str = ARTICLE_SOURCE_TENANT,
    is_top: bool = False,
    help_key: str | None = None,
    target_type: str = "module",
    locale: str = "zh-CN",
) -> int:
    """直接插入一篇文章（含多语言与可选目标）并返回主键。

    Args:
        url: 租户库连接串。
        category_id: 分类主键。
        title: 标题（调用方负责命名空间唯一）。
        content: 正文 HTML。
        status: 状态。
        source: 来源。
        is_top: 是否置顶。
        help_key: 目标锚点（None 不插目标）。
        target_type: 目标类型。
        locale: 多语言行语言。

    Returns:
        int: 文章主键。
    """
    await ensure_help_tables(url)
    async with help_session(url) as session:
        row = SysHelpArticle(
            category_id=category_id,
            title=title,
            content=content,
            status=status,
            is_top=is_top,
            source=source,
            generated_by=GENERATED_BY_MANUAL,
            view_count=0,
            helpful_count=0,
            unhelpful_count=0,
        )
        session.add(row)
        await session.flush()
        article_id = int(row.id)
        session.add(SysHelpArticleI18n(article_id=article_id, locale=locale, title=title, content=content))
        if help_key is not None:
            session.add(
                SysHelpArticleTarget(
                    article_id=article_id,
                    target_type=target_type,
                    target_key=help_key,
                )
            )
        elif target_type == TARGET_TYPE_GLOBAL:
            session.add(SysHelpArticleTarget(article_id=article_id, target_type=TARGET_TYPE_GLOBAL, target_key=""))
        await session.commit()
        return article_id


async def seed_package(
    url: str,
    *,
    product_key: str,
    version: str = "1.0.0",
    status: str = PACKAGE_STATUS_LOADED,
    article_count: int = 1,
) -> int:
    """直接插入一条帮助包登记并返回主键。

    Args:
        url: 租户库连接串。
        product_key: 产品键。
        version: 包版本。
        status: 包状态。
        article_count: 清单文章数。

    Returns:
        int: 包登记主键。
    """
    await ensure_help_tables(url)
    async with help_session(url) as session:
        row = SysHelpPackage(
            product_key=product_key,
            package_version=version,
            schema_version=1,
            checksum="sha256:" + "0" * 64,
            article_count=article_count,
            loaded_at=datetime.now(UTC).replace(tzinfo=None),
            status=status,
        )
        session.add(row)
        await session.commit()
        return int(row.id)


def platform_url() -> str:
    """当前用例的共享测试平台库连接串。

    Returns:
        str: 平台库连接串。
    """
    return os.environ["BMS_DATABASE__PLATFORM__URL"]


async def seed_platform_action(url: str, *, code: str, help_key: str) -> int:
    """直接插入一个带锚点的动作码（维护面目标校验的正向探针）。

    Args:
        url: 平台库连接串。
        code: 动作码（调用方负责命名空间唯一）。
        help_key: 五段式锚点（动作码形态：首段与末段非空）。

    Returns:
        int: 动作码主键。
    """
    engine = create_async_engine(  # own_db: 共享基座模块内建引擎（测试库隔离护栏放行点）
        url,
        pool_pre_ping=True,
    )
    try:
        tables = [cast("Table", SysAction.__table__)]
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            row = SysAction(form_key=f"act_{code}", code=code, name=code, status="enabled", help_key=help_key)
            session.add(row)
            await session.commit()
            return int(row.id)
    finally:
        await engine.dispose()


async def delete_platform_action(url: str, code: str) -> None:
    """删除用例自造的动作码（避免污染共享平台库的锚点计数断言）。

    Args:
        url: 平台库连接串。
        code: 动作码。
    """
    engine = create_async_engine(  # own_db: 共享基座模块内建引擎（测试库隔离护栏放行点）
        url,
        pool_pre_ping=True,
    )
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            rows = (await session.execute(select(SysAction).where(SysAction.code == code))).scalars().all()
            for row in rows:
                await session.delete(row)
            await session.commit()
    finally:
        await engine.dispose()
