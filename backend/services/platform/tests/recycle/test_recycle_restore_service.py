"""回收站恢复服务：显式审计 / 白名单跳过 / 缓存失效 / 失败只告警。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.audit.base import FieldChange
from bms_core.audit.null import NullAuditCapturer
from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.config import RecycleSettings
from bms_core.events.base import EventEnvelope
from bms_core.help.cache import content_version
from bms_core.menu import menu_version_key
from bms_core.models.outbox import SysOutbox
from bms_core.models.platform.dashboard import SysDashboardCard, SysDashboardCardI18n
from bms_core.models.platform.help import SysHelpArticle, SysHelpArticleI18n, SysHelpArticleTarget, SysHelpCategory
from bms_core.models.platform.icon import SysIcon, SysIconI18n
from bms_core.models.platform.user import SysUser, SysUserExtension
from bms_platform.domains.recycle.services.restore import RecycleRestoreService

pytestmark = [
    pytest.mark.kiwi_id(2530),
    pytest.mark.own_db("恢复服务需按表族独立建表，分别验证审计 / 缓存失效 / 失败降级，不污染共享库"),
]

_NOW = datetime(2026, 11, 18, 12, 0, 0)
_TABLES = (
    SysHelpCategory.__table__,
    SysHelpArticle.__table__,
    SysHelpArticleI18n.__table__,
    SysHelpArticleTarget.__table__,
    SysIcon.__table__,
    SysIconI18n.__table__,
    SysDashboardCard.__table__,
    SysDashboardCardI18n.__table__,
    SysUser.__table__,
    SysUserExtension.__table__,
    SysOutbox.__table__,
)


class RecordingAudit(NullAuditCapturer):
    """测试替身：记录显式留痕调用。"""

    plugin_name: str = "recycle_recording_audit"

    def __init__(self, *, audited: bool = False) -> None:
        """初始化。

        Args:
            audited: `is_audited` 返回值（True = 白名单表，跳过显式留痕）。
        """
        self.calls: ConcurrentStableList[tuple[str, int, ConcurrentStableList[FieldChange]]] = ConcurrentStableList()
        self.audited = audited

    def is_audited(self, table: str) -> bool:
        """按测试设定返回是否审计。"""
        del table
        return self.audited

    def capture(
        self,
        *,
        table: str,
        model_id: int,
        changes: ConcurrentStableList[FieldChange],
        actor: int | None = None,
    ) -> EventEnvelope:
        """记录调用并返回占位信封。"""
        del actor
        self.calls.add((table, model_id, changes))
        return EventEnvelope(event_type="test.recycle", payload=ConcurrentStableDict({"table": table}))


class BrokenAudit(RecordingAudit):
    """测试替身：留痕抛错。"""

    plugin_name: str = "recycle_broken_audit"

    def capture(
        self,
        *,
        table: str,
        model_id: int,
        changes: ConcurrentStableList[FieldChange],
        actor: int | None = None,
    ) -> EventEnvelope:
        """抛错（验证不反噬恢复）。"""
        del table, model_id, changes, actor
        raise RuntimeError("audit down")


class BrokenCache(MemoryCacheRegion):
    """测试替身：缓存递增抛错。"""

    async def aincrease(self, key: str, amount: int = 1, *, ttl: int | None = None) -> int:
        """抛错（验证不反噬恢复）。"""
        del key, amount, ttl
        raise RuntimeError("cache down")


@pytest.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    """独立 SQLite 库（恢复服务涉及的表）。"""
    engine: AsyncEngine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'recycle_restore.db'}")
    async with engine.begin() as connection:
        for table in _TABLES:
            await connection.run_sync(cast("Table", table).create, checkfirst=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db_session:
        yield db_session
    await engine.dispose()


async def _deleted_article(session: AsyncSession) -> SysHelpArticle:
    """造一篇软删文章。"""
    category = SysHelpCategory(parent_id=0, name="恢复分类", sort=1)
    session.add(category)
    await session.flush()
    article = SysHelpArticle(category_id=int(category.id), title="恢复文章")
    session.add(article)
    await session.flush()
    article.deleted_at = _NOW
    await session.commit()
    return article


async def _deleted_category(session: AsyncSession) -> SysHelpCategory:
    """造一个软删分类（非字段级审计白名单表）。"""
    category = SysHelpCategory(parent_id=0, name="待恢复分类", sort=1)
    session.add(category)
    await session.flush()
    category.deleted_at = _NOW
    await session.commit()
    return category


async def test_restore_service_audits_non_whitelisted_and_bumps_help_cache(session: AsyncSession) -> None:
    """非白名单表显式留痕；帮助内容恢复后递增内容版本。"""
    category = await _deleted_category(session)
    audit = RecordingAudit()
    cache = MemoryCacheRegion(domain="generic")
    service = RecycleRestoreService(session, RecycleSettings(), audit=audit, cache=cache)
    await service.restore("sys_help_category", int(category.id))
    assert len(audit.calls) == 1
    assert audit.calls[0][0] == "sys_help_category"
    assert await content_version(cache, tenant=None) == 1


async def test_restore_service_skips_whitelisted_table(session: AsyncSession) -> None:
    """白名单表由 ORM 捕获，不再显式留痕；用户恢复不递增缓存。"""
    user = SysUser(username="carol", name="恢复用户", password_hash="x", status="enabled")
    session.add(user)
    await session.flush()
    user.deleted_at = _NOW
    await session.commit()
    audit = RecordingAudit(audited=True)
    cache = MemoryCacheRegion(domain="generic")
    service = RecycleRestoreService(session, RecycleSettings(), audit=audit, cache=cache)
    await service.restore("sys_user", int(user.id))
    assert audit.calls == []
    assert await content_version(cache, tenant=None) == 0


async def test_restore_service_bumps_metadata_and_dashboard_versions(session: AsyncSession) -> None:
    """图标恢复递增元数据版本；工作台卡片恢复递增工作台版本。"""
    icon = SysIcon(code="recycle_icon", name="图标", category="test", svg="<svg/>")
    card = SysDashboardCard(code="recycle_card", name="卡片", card_type="dataset")
    session.add_all((icon, card))
    await session.flush()
    icon.deleted_at = _NOW
    card.deleted_at = _NOW
    await session.commit()
    cache = MemoryCacheRegion(domain="generic")
    service = RecycleRestoreService(session, RecycleSettings(), cache=cache)
    await service.restore("sys_icon", int(icon.id))
    assert int(str(await cache.aget(menu_version_key()) or 0)) > 0
    await service.restore("sys_dashboard_card", int(card.id))
    version = await cache.aget(cache.build_key("version", tenant=None))
    assert int(str(version or 0)) > 0


async def test_restore_service_swallows_audit_and_cache_failures(session: AsyncSession) -> None:
    """留痕 / 缓存失败只告警，恢复保持成功。"""
    category = await _deleted_category(session)
    service = RecycleRestoreService(
        session,
        RecycleSettings(),
        audit=BrokenAudit(),
        cache=BrokenCache(domain="generic"),
    )
    outcome = await service.restore("sys_help_category", int(category.id))
    assert outcome.id == int(category.id)
    await session.refresh(category)
    assert category.deleted_at is None


async def test_restore_service_without_audit_or_cache(session: AsyncSession) -> None:
    """审计 / 缓存均未注入时不报错。"""
    article = await _deleted_article(session)
    service = RecycleRestoreService(session, RecycleSettings())
    outcome = await service.restore("sys_help_article", int(article.id))
    assert outcome.id == int(article.id)


def test_unique_columns_handles_unique_indexes() -> None:
    """唯一索引同样纳入冲突判定；含 form_key 的约束 / 索引跳过。"""
    from sqlalchemy import Column, Index, Integer, MetaData, String, Table

    from bms_core.recycle.engine import RecycleEngine

    metadata = MetaData()
    table = Table(
        "t_unique_probe",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("code", String(32)),
        Column("form_key", String(32)),
        Column("deleted_at", String(32)),
    )
    Index("uq_t_unique_probe_code", table.c.code, unique=True)
    Index("uq_t_unique_probe_form", table.c.form_key, unique=True)
    Index("idx_t_unique_probe_code", table.c.code)
    columns = RecycleEngine._unique_columns(table)  # pyright: ignore[reportPrivateUsage]
    assert ConcurrentStableFrozenList(("code",)) in columns
    assert ConcurrentStableFrozenList(("form_key",)) not in columns
