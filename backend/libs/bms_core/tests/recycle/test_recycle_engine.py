"""回收站通用引擎：计数 / 分页 / 详情 / 恢复（冲突 / 级联）/ 逐表清理。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.config import RecycleSettings
from bms_core.core.exceptions import (
    ParamError,
    RecycleAlreadyRestoredError,
    RecycleRecordNotFoundError,
    RecycleRestoreConflictError,
    RecycleTableNotSupportedError,
)
from bms_core.models.outbox import SysOutbox
from bms_core.models.platform.dashboard import (
    SysDashboardCard,
    SysDashboardCardI18n,
    SysDashboardTemplate,
)
from bms_core.models.platform.form_design import (
    SysFieldExt,
    SysFieldExtI18n,
    SysFormFieldAttr,
    SysFormLayout,
)
from bms_core.models.platform.help import (
    SysHelpArticle,
    SysHelpArticleI18n,
    SysHelpArticleTarget,
    SysHelpCategory,
    SysHelpFeedback,
    SysHelpPackage,
)
from bms_core.models.platform.icon import SysIcon, SysIconI18n
from bms_core.models.platform.recycle import SysRecycleLog
from bms_core.models.platform.role import SysRole
from bms_core.models.platform.user import SysUser, SysUserExtension
from bms_core.recycle.engine import (
    RecycleEngine,
    _format_value,  # pyright: ignore[reportPrivateUsage]
    _utc_now,  # pyright: ignore[reportPrivateUsage]
)
from bms_core.recycle.registry import recycle_spec_of
from bms_core.recycle.spec import RecycleCascade

pytestmark = [
    pytest.mark.kiwi_id(2530),
    pytest.mark.own_db("回收站引擎需按纳管表子集独立建表，验证跨表批删 / 级联 / 冲突，不污染共享库"),
]

_NOW = datetime(2026, 11, 18, 12, 0, 0)
_TABLES = (
    SysUser.__table__,
    SysUserExtension.__table__,
    SysRole.__table__,
    SysIcon.__table__,
    SysIconI18n.__table__,
    SysHelpCategory.__table__,
    SysHelpArticle.__table__,
    SysHelpArticleI18n.__table__,
    SysHelpArticleTarget.__table__,
    SysHelpFeedback.__table__,
    SysHelpPackage.__table__,
    SysDashboardCard.__table__,
    SysDashboardCardI18n.__table__,
    SysDashboardTemplate.__table__,
    SysFormLayout.__table__,
    SysFormFieldAttr.__table__,
    SysFieldExt.__table__,
    SysFieldExtI18n.__table__,
    SysRecycleLog.__table__,
    SysOutbox.__table__,
)


@pytest.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    """独立 SQLite 库（只建回收站纳管表）。"""
    engine: AsyncEngine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'recycle.db'}")
    async with engine.begin() as connection:
        for table in _TABLES:
            await connection.run_sync(cast("Table", table).create, checkfirst=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db_session:
        yield db_session
    await engine.dispose()


def _engine(session: AsyncSession) -> RecycleEngine:
    """构造引擎（固定时钟）。"""
    return RecycleEngine(session, RecycleSettings(), clock=lambda: _NOW)


async def _article(session: AsyncSession, title: str, *, deleted_at: datetime | None = None) -> SysHelpArticle:
    """造一篇文章（可同时软删）。"""
    category = SysHelpCategory(parent_id=0, name=f"分类-{title}", sort=1)
    session.add(category)
    await session.flush()
    article = SysHelpArticle(category_id=int(category.id), title=title)
    session.add(article)
    await session.flush()
    if deleted_at is not None:
        article.deleted_at = deleted_at
        await session.flush()
    return article


async def test_modules_counts_only_visible_tables(session: AsyncSession) -> None:
    """模块计数只统计可见表；隐藏子表不出现。"""
    await _article(session, "已删文章", deleted_at=_NOW)
    await _article(session, "在用文章")
    await session.commit()
    modules = await _engine(session).modules()
    by_key = {module.module_key: module for module in modules}
    assert [module.module_key for module in modules] == [
        "user",
        "role",
        "permission_meta",
        "help",
        "dashboard",
        "form_design",
    ]
    help_module = by_key["help"]
    counts = {table.table: table.deleted_count for table in help_module.tables}
    assert counts["sys_help_article"] == 1
    assert "sys_help_article_i18n" not in counts
    assert help_module.deleted_count >= 1


async def test_page_filters_and_ordering(session: AsyncSession) -> None:
    """单表分页：只出软删行；关键字 / 时间范围 / 排序生效；范围颠倒拒绝。"""
    await _article(session, "100% 指南", deleted_at=_NOW)
    await _article(session, "普通文章", deleted_at=_NOW - timedelta(days=1))
    await _article(session, "在用文章")
    await session.commit()
    engine = _engine(session)
    rows, total = await engine.page("sys_help_article", page=1, size=10)
    assert total == 2
    assert [row.title for row in rows] == ["100% 指南", "普通文章"]
    keyword_rows, keyword_total = await engine.page("sys_help_article", keyword="100%", page=1, size=10)
    assert keyword_total == 1
    assert keyword_rows[0].title == "100% 指南"
    recent, recent_total = await engine.page("sys_help_article", deleted_from=_NOW, page=1, size=10)
    assert recent_total == 1
    assert recent[0].title == "100% 指南"
    with pytest.raises(ParamError):
        await engine.page(
            "sys_help_article",
            deleted_from=_NOW,
            deleted_to=_NOW - timedelta(days=1),
            page=1,
            size=10,
        )


async def test_detail_fields_and_failures(session: AsyncSession) -> None:
    """详情只返回展示列；未删除 / 隐藏子表按错误码拒绝。"""
    article = await _article(session, "详情文章", deleted_at=_NOW)
    live = await _article(session, "在用文章")
    await session.commit()
    detail = await _engine(session).detail("sys_help_article", int(article.id))
    assert detail.title == "详情文章"
    assert detail.fields["标题"] == "详情文章"
    assert detail.fields["置顶"] == "否"
    assert "content" not in detail.fields
    with pytest.raises(RecycleRecordNotFoundError):
        await _engine(session).detail("sys_help_article", int(live.id))
    with pytest.raises(RecycleTableNotSupportedError):
        await _engine(session).detail("sys_help_article_i18n", int(article.id))


async def test_restore_cascades_children(session: AsyncSession) -> None:
    """文章恢复时多语言与锚点一并恢复，返回级联计数。"""
    article = await _article(session, "待恢复文章", deleted_at=_NOW)
    i18n = SysHelpArticleI18n(article_id=int(article.id), locale="zh-CN", title="待恢复文章")
    target = SysHelpArticleTarget(article_id=int(article.id), target_type="global", target_key="")
    session.add_all((i18n, target))
    await session.flush()
    i18n.deleted_at = _NOW
    target.deleted_at = _NOW
    await session.commit()
    outcome = await _engine(session).restore("sys_help_article", int(article.id))
    assert outcome.title == "待恢复文章"
    assert outcome.cascaded["sys_help_article_i18n"] == 1
    assert outcome.cascaded["sys_help_article_target"] == 1
    await session.refresh(article)
    await session.refresh(i18n)
    await session.refresh(target)
    assert article.deleted_at is None
    assert i18n.deleted_at is None
    assert target.deleted_at is None


async def test_restore_category_subtree(session: AsyncSession) -> None:
    """分类恢复递归带回子树。"""
    parent = SysHelpCategory(parent_id=0, name="父分类", sort=1)
    session.add(parent)
    await session.flush()
    child = SysHelpCategory(parent_id=int(parent.id), name="子分类", sort=1)
    session.add(child)
    await session.flush()
    parent.deleted_at = _NOW
    child.deleted_at = _NOW
    await session.commit()
    outcome = await _engine(session).restore("sys_help_category", int(parent.id))
    assert outcome.cascaded["sys_help_category"] == 1
    await session.refresh(child)
    assert child.deleted_at is None


async def test_restore_category_depth_limit(session: AsyncSession) -> None:
    """自引用级联展开到深度上限即停止（防病态树）。"""
    rows: ConcurrentStableList[SysHelpCategory] = ConcurrentStableList()
    parent_id = 0
    for index in range(7):
        row = SysHelpCategory(parent_id=parent_id, name=f"深层{index}", sort=1)
        session.add(row)
        await session.flush()
        rows.add(row)
        parent_id = int(row.id)
    for row in rows:
        row.deleted_at = _NOW
    await session.commit()
    outcome = await _engine(session).restore("sys_help_category", int(rows[0].id))
    assert outcome.cascaded["sys_help_category"] == 5
    await session.refresh(rows[-1])
    assert rows[-1].deleted_at is not None


async def test_restore_conflict_reports_fields(session: AsyncSession) -> None:
    """同名 / 同码冲突返回 95002 并给出冲突字段，整体回滚。"""
    live = SysUser(username="alice", name="在用", password_hash="x", status="enabled")
    deleted = SysUser(username="alice", name="已删", password_hash="x", status="enabled")
    session.add_all((live, deleted))
    await session.flush()
    deleted.deleted_at = _NOW
    await session.commit()
    with pytest.raises(RecycleRestoreConflictError) as exc:
        await _engine(session).restore("sys_user", int(deleted.id))
    data = exc.value.data
    assert data is not None
    assert data["table"] == "sys_user"  # type: ignore[index]
    assert "code" in data["fields"]  # type: ignore[index]
    await session.refresh(deleted)
    assert deleted.deleted_at is not None


async def test_restore_not_found_already_restored_and_unsupported(session: AsyncSession) -> None:
    """不存在 95001；已恢复 95003；隐藏 / 未纳管表 95004。"""
    live = await _article(session, "在用文章")
    deleted = await _article(session, "已删文章", deleted_at=_NOW)
    await session.commit()
    engine = _engine(session)
    with pytest.raises(RecycleRecordNotFoundError):
        await engine.restore("sys_help_article", 999999999)
    with pytest.raises(RecycleAlreadyRestoredError):
        await engine.restore("sys_help_article", int(live.id))
    with pytest.raises(RecycleTableNotSupportedError):
        await engine.restore("sys_help_article_i18n", int(deleted.id))
    with pytest.raises(RecycleTableNotSupportedError):
        await engine.restore("sys_recycle_log", 1)


async def test_purge_respects_retention_and_limits(session: AsyncSession) -> None:
    """只删超期行；分批提交；单轮上限生效。"""
    old_one = await _article(session, "超期一", deleted_at=_NOW - timedelta(days=40))
    old_two = await _article(session, "超期二", deleted_at=_NOW - timedelta(days=40))
    old_three = await _article(session, "超期三", deleted_at=_NOW - timedelta(days=40))
    recent = await _article(session, "保留期内", deleted_at=_NOW - timedelta(days=1))
    await session.commit()
    cutoff = _NOW - timedelta(days=30)
    outcome = await _engine(session).purge_table("sys_help_article", cutoff=cutoff, batch_size=1, max_rows=2)
    assert outcome.deleted_count == 2
    assert outcome.batches == 2
    remaining = int(
        (
            await session.execute(
                select(func.count()).select_from(SysHelpArticle).where(SysHelpArticle.deleted_at.is_not(None))
            )
        ).scalar_one()
    )
    assert remaining == 2
    await session.refresh(recent)
    assert recent.deleted_at is not None
    assert len({int(old_one.id), int(old_two.id), int(old_three.id)}) == 3


def test_utc_now_and_format_value() -> None:
    """内部时钟与展示值格式化（空 / 布尔 / 时间 / 数字）。"""
    assert _utc_now().tzinfo is None
    assert _format_value(None) == ""
    assert _format_value(True) == "是"
    assert _format_value(False) == "否"
    assert _format_value(datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02 03:04:05"
    assert _format_value(7) == "7"


async def test_page_deleted_to_filter(session: AsyncSession) -> None:
    """删除时间上界筛选生效。"""
    await _article(session, "较早删除", deleted_at=_NOW - timedelta(days=2))
    await _article(session, "最近删除", deleted_at=_NOW)
    await session.commit()
    rows, total = await _engine(session).page("sys_help_article", deleted_to=_NOW - timedelta(days=1), page=1, size=10)
    assert total == 1
    assert rows[0].title == "较早删除"


async def test_purge_unknown_table(session: AsyncSession) -> None:
    """未纳管表清理按 95004 拒绝。"""
    with pytest.raises(RecycleTableNotSupportedError):
        await _engine(session).purge_table("sys_recycle_log")


async def test_restore_deduplicates_cascade_paths(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """同一子行被多条级联路径命中时只恢复一次。"""
    article = await _article(session, "重复级联文章", deleted_at=_NOW)
    i18n = SysHelpArticleI18n(article_id=int(article.id), locale="zh-CN", title="重复级联文章")
    session.add(i18n)
    await session.flush()
    i18n.deleted_at = _NOW
    await session.commit()
    base = recycle_spec_of("sys_help_article")
    assert base is not None
    cascade = RecycleCascade(table="sys_help_article_i18n", column="article_id")
    duplicate = replace(base, cascades=ConcurrentStableFrozenList((cascade, cascade)))
    original = recycle_spec_of

    def _patched(table: str) -> object:
        return duplicate if table == "sys_help_article" else original(table)

    monkeypatch.setattr("bms_core.recycle.engine.recycle_spec_of", _patched)
    outcome = await _engine(session).restore("sys_help_article", int(article.id))
    assert outcome.cascaded["sys_help_article_i18n"] == 1


async def test_restore_skips_nullable_unique_column(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """唯一列值为空时按标准 SQL 语义跳过冲突判定。"""
    feedback = SysHelpFeedback(article_id=1, user_id=2, feedback="helpful", comment=None)
    session.add(feedback)
    await session.flush()
    feedback.deleted_at = _NOW
    await session.commit()

    def _unique_columns(table: Table) -> ConcurrentStableSet[ConcurrentStableFrozenList[str]]:
        del table
        return ConcurrentStableSet((ConcurrentStableFrozenList(("comment",)),))

    monkeypatch.setattr(RecycleEngine, "_unique_columns", staticmethod(_unique_columns))
    outcome = await _engine(session).restore("sys_help_feedback", int(feedback.id))
    assert outcome.table == "sys_help_feedback"


async def test_restore_integrity_error_maps_conflict(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """预检未命中但数据库约束拦截时转 95002。"""
    article = await _article(session, "数据库冲突文章", deleted_at=_NOW)
    engine = _engine(session)

    async def _boom() -> None:
        raise IntegrityError("stmt", {}, Exception("unique"))

    monkeypatch.setattr(session, "flush", _boom)
    with pytest.raises(RecycleRestoreConflictError):
        await engine.restore("sys_help_article", int(article.id))
