"""回收站清理服务与作业：逐表记录 / 单表失败继续 / 超时回收。"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import RecycleSettings
from bms_core.jobs.base import JobContext
from bms_core.models.platform.help import SysHelpArticle, SysHelpCategory
from bms_core.models.platform.recycle import SysRecycleLog
from bms_core.recycle.engine import RecycleEngine
from bms_platform.domains.recycle.jobs import RecyclePurgeJob
from bms_platform.domains.recycle.services.purge import RecyclePurgeService
from tests_support.shared_access import shared_session

pytestmark = [
    pytest.mark.kiwi_id(2530),
    pytest.mark.xdist_group("recycle-purge"),
]
"""回收站清理是**全库破坏性操作**，同组串行，避免并行用例互删对方刚造的超期数据。"""

_NOW = datetime(2026, 11, 18, 12, 0, 0)


@pytest.fixture
async def session(tenant_db: str) -> AsyncIterator[AsyncSession]:
    """共享租户库会话（表由数据初始化一次建好；断言按本批次收敛）。"""
    async with shared_session(tenant_db, read_only=False) as db_session:
        yield db_session


async def _seed_old_article(session: AsyncSession) -> SysHelpArticle:
    """造一篇超期软删文章（标题带随机后缀，避免与共享库他人数据混淆）。"""
    category = SysHelpCategory(parent_id=0, name=f"清理分类-{uuid.uuid4().hex[:8]}", sort=1)
    session.add(category)
    await session.flush()
    article = SysHelpArticle(category_id=int(category.id), title=f"待清理文章-{uuid.uuid4().hex[:8]}")
    session.add(article)
    await session.flush()
    article.deleted_at = _NOW - timedelta(days=40)
    await session.commit()
    return article


async def _logs(session: AsyncSession, *, limit: int = 18) -> ConcurrentStableList[SysRecycleLog]:
    """取最近一批清理记录（本文件同组串行，最近 `limit` 条即本次批次）。"""
    statement = select(SysRecycleLog).order_by(SysRecycleLog.id.desc()).limit(limit)
    rows = (await session.execute(statement)).scalars().all()
    return ConcurrentStableList(reversed(rows))


async def test_purge_service_writes_per_table_logs(session: AsyncSession) -> None:
    """逐表写清理记录；超期数据删除、保留期内数据保留。"""
    article = await _seed_old_article(session)
    service = RecyclePurgeService(session, RecycleSettings(), clock=lambda: _NOW)
    summary = await service.run()
    assert summary["tables"] == 18
    assert int(str(summary["deleted"])) >= 1
    assert summary["failed"] == 0
    logs = await _logs(session)
    assert len(logs) == 18
    article_log = next(log for log in logs if log.table_name == "sys_help_article")
    assert article_log.status == "success"
    assert article_log.deleted_count >= 1
    assert article_log.retention_days == 30
    assert article_log.finished_at is not None
    gone = int(
        (
            await session.execute(
                select(func.count()).select_from(SysHelpArticle).where(SysHelpArticle.id == article.id)
            )
        ).scalar_one()
    )
    assert gone == 0


async def test_purge_service_continues_after_table_failure(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """单表失败不影响其他表；失败表写 failed 记录。"""
    await _seed_old_article(session)
    original = RecycleEngine.purge_table

    async def _fake(self: RecycleEngine, table_name: str, **kwargs: Any) -> Any:
        if table_name == "sys_role":
            raise RuntimeError("模拟清理失败")
        return await original(self, table_name, **kwargs)

    monkeypatch.setattr(RecycleEngine, "purge_table", _fake)
    service = RecyclePurgeService(session, RecycleSettings(), clock=lambda: _NOW)
    summary = await service.run()
    assert summary["failed"] == 1
    logs = await _logs(session)
    role_log = next(log for log in logs if log.table_name == "sys_role")
    assert role_log.status == "failed"
    assert role_log.error_msg is not None
    article_log = next(log for log in logs if log.table_name == "sys_help_article")
    assert article_log.status == "success"


async def test_purge_service_reclaims_stale_running(session: AsyncSession) -> None:
    """陈旧 running 批次回收为 failed。"""
    stale = SysRecycleLog(
        batch_key="recycle:stale",
        table_name="sys_help_article",
        status="running",
        retention_days=30,
        cutoff_at=_NOW,
        started_at=_NOW - timedelta(hours=3),
    )
    session.add(stale)
    await session.commit()
    service = RecyclePurgeService(session, RecycleSettings(), clock=lambda: _NOW)
    await service.run()
    await session.refresh(stale)
    assert stale.status == "failed"
    assert stale.error_msg == "执行超时未完成（进程可能中断）"


async def test_purge_job_returns_success_summary(session: AsyncSession) -> None:
    """作业执行体：成功返回汇总；表数量与清理记录一致。"""
    await _seed_old_article(session)

    @asynccontextmanager
    async def _open() -> AsyncGenerator[AsyncSession]:
        yield session

    ctx = JobContext(
        job_id=1,
        job_type=RecyclePurgeJob.job_type,
        service_key="platform",
        db_key="tenant_platform_test",
        open_session=_open,
    )
    result = await RecyclePurgeJob().run(ctx)
    assert result.status == "succeeded"
    assert result.output is not None
    assert result.output["tables"] == 18
    assert int(str(result.output["deleted"])) >= 1


async def test_purge_job_returns_failed_when_any_table_fails(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """任一张表失败：作业返回可重试失败。"""

    async def _failed(self: RecyclePurgeService) -> Any:
        del self
        return ConcurrentStableDict({"tables": 18, "deleted": 0, "failed": 1})

    monkeypatch.setattr(RecyclePurgeService, "run", _failed)

    @asynccontextmanager
    async def _open() -> AsyncGenerator[AsyncSession]:
        yield session

    ctx = JobContext(
        job_id=2,
        job_type=RecyclePurgeJob.job_type,
        service_key="platform",
        db_key="tenant_platform_test",
        open_session=_open,
    )
    result = await RecyclePurgeJob().run(ctx)
    assert result.status == "failed"
    assert result.output is not None
    assert result.output["failed"] == 1
