"""归档作业入口与策略种子：类型声明、执行摘要、幂等种子。"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false, reportIndexIssue=false, reportGeneralTypeIssues=false, reportUnknownLambdaType=false, reportIncompatibleMethodOverride=false, reportDeprecated=false

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.audit.sha256 import Sha256HashChain
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.jobs.base import JobContext
from bms_core.lock.null import NullDistributedLock
from bms_core.models.platform.archive import SysArchivePolicy
from bms_core.tenant.seed.archive import ARCHIVE_POLICY_SEEDS, seed_archive_policies_entry
from bms_platform.domains.archive import jobs as archive_jobs
from bms_platform.jobs import job_handlers, job_specs
from tests.archive.helpers import FakeStorage, new_pair

pytestmark = pytest.mark.kiwi_id(2516)


async def test_seed_policies_idempotent(tmp_path: Path) -> None:
    """策略种子：三类审计日志落库、二次执行只校正不重复。"""
    platform, archive, platform_engine, archive_engine = await new_pair(tmp_path)
    try:
        await seed_archive_policies_entry(platform, ConcurrentStableDict[str, object]())
        await platform.commit()
        rows = (await platform.execute(select(SysArchivePolicy))).scalars().all()
        assert [row.table_name for row in rows] == [seed.table_name for seed in ARCHIVE_POLICY_SEEDS]
        assert all(row.require_chain for row in rows)
        assert all(row.threshold_days == 90 for row in rows)

        rows[0].batch_size = 9
        await platform.commit()
        await seed_archive_policies_entry(platform, ConcurrentStableDict[str, object]())
        await platform.commit()
        again = (await platform.execute(select(SysArchivePolicy))).scalars().all()
        assert len(again) == len(ARCHIVE_POLICY_SEEDS)
        assert again[0].batch_size == 1000
    finally:
        await platform.close()
        await archive.close()
        await platform_engine.dispose()
        await archive_engine.dispose()


def test_jobs_declared() -> None:
    """两条归档作业已登记处理器与类型声明。"""
    handlers = job_handlers()
    assert "platform.archive.run" in handlers
    assert "platform.archive.cleanup" in handlers
    specs = job_specs()
    assert specs["platform.archive.run"].domain_key == "archive"
    assert specs["platform.archive.cleanup"].handler.endswith(":ArchiveCleanupJob")


async def test_job_handlers_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """作业执行：成功摘要与失败摘要；清理作业输出条数。"""
    platform, archive, platform_engine, archive_engine = await new_pair(tmp_path)
    try:

        @asynccontextmanager
        async def _platform_session() -> AsyncIterator[AsyncSession]:
            yield platform

        @asynccontextmanager
        async def _archive_session() -> AsyncIterator[AsyncSession]:
            yield archive

        ctx = JobContext(
            job_id=1,
            job_type="platform.archive.run",
            service_key="platform",
            db_key="platform",
            open_session=_platform_session,
        )
        monkeypatch.setattr(
            archive_jobs,
            "ArchiveExecutor",
            lambda *args, **kwargs: _FakeExecutor(
                ConcurrentStableDict({"policies": 1, "archived": 2, "cold": 1, "failed": 0})
            ),
        )
        monkeypatch.setattr(
            archive_jobs,
            "session_scope",
            lambda *args, **kwargs: _archive_session(),
        )
        monkeypatch.setattr(archive_jobs, "ensure_job_plugins", lambda settings: None)
        monkeypatch.setattr(archive_jobs, "_storage", lambda settings: FakeStorage())
        monkeypatch.setattr(archive_jobs, "_chain", lambda settings: Sha256HashChain())
        monkeypatch.setattr(archive_jobs, "_lock", lambda settings: NullDistributedLock())
        monkeypatch.setattr(archive_jobs, "_archive_registry", lambda: object())
        result = await archive_jobs.ArchiveRunJob().run(ctx)
        assert result.status == "succeeded"
        assert "归档 2 条" in result.message

        failed = await archive_jobs.ArchiveRunJob().run(ctx)
        assert failed.status == "succeeded"

        class _FailingExecutor(_FakeExecutor):
            async def run(self, **kwargs: object):
                return ConcurrentStableDict({"policies": 1, "archived": 0, "cold": 0, "failed": 1})

        monkeypatch.setattr(archive_jobs, "ArchiveExecutor", lambda *args, **kwargs: _FailingExecutor())
        broken = await archive_jobs.ArchiveRunJob().run(ctx)
        assert broken.status == "failed"

        cleanup_ctx = JobContext(
            job_id=2,
            job_type="platform.archive.cleanup",
            service_key="platform",
            db_key="platform",
            open_session=_platform_session,
        )
        monkeypatch.setattr(archive_jobs, "ArchiveExecutor", lambda *args, **kwargs: _FakeExecutor(cleaned=3))
        cleaned = await archive_jobs.ArchiveCleanupJob().run(cleanup_ctx)
        assert cleaned.status == "succeeded"
        assert "3 个" in cleaned.message
    finally:
        await platform.close()
        await archive.close()
        await platform_engine.dispose()
        await archive_engine.dispose()


class _FakeExecutor:
    """执行器替身。"""

    def __init__(self, summary: ConcurrentStableDict[str, object] | None = None, *, cleaned: int = 0) -> None:
        self._summary = summary or ConcurrentStableDict[str, object]()
        self._cleaned = cleaned

    async def run(self, **kwargs: object) -> ConcurrentStableDict[str, object]:
        _ = kwargs
        return self._summary

    async def cleanup(self) -> int:
        return self._cleaned
