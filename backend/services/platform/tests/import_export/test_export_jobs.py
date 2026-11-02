"""导出作业用例：异步导出落产物 / 明文与掩码 / 失败 / 产物过期清理。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from openpyxl import load_workbook
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ExportBizNotRegisteredError
from bms_core.jobs.base import JobContext
from bms_core.models.job import JOB_STATUS_SUCCEEDED, SysJob
from bms_core.models.platform.user import SysUser
from bms_core.print.exporter import StoragePrintExporter
from bms_core.print.templates import BuiltinPrintTemplateProvider
from bms_core.storage.local import LocalObjectStorage
from bms_core.testing.schema import ensure_tables
from bms_core.transfer.artifacts import ObjectStorageExportArtifactStore
from bms_core.transfer.export_limits import ExportLimits
from bms_core.transfer.openpyxl_exporter import OpenpyxlExporter
from bms_platform.domains.import_export.export_jobs import ExportCleanupJob, ExportExecuteJob
from bms_platform.domains.import_export.services.exports import JOB_TYPE, KIND_EXCEL, ExportPayload

pytestmark = [pytest.mark.kiwi_id(2402), pytest.mark.usefixtures("serial_db_write")]


@dataclass
class _Env:
    """导出作业测试环境。"""

    factory: async_sessionmaker[AsyncSession]
    storage: LocalObjectStorage
    artifacts: ObjectStorageExportArtifactStore


@pytest_asyncio.fixture
async def env(
    shared_tenant_engine: AsyncEngine,
    shared_tenant_db_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[_Env]:
    """自建租户库 + 本地对象存储。"""
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", shared_tenant_db_url)
    monkeypatch.setenv("BMS_STORAGE__OPTIONS__ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    await ensure_tables(
        shared_tenant_engine,
        cast("list[Table]", [SysUser.__table__, SysJob.__table__]),
    )
    factory = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    storage = LocalObjectStorage(root=tmp_path / "storage")
    async with factory() as session:
        session.add_all(
            [
                SysUser(
                    form_key=f"job-user-{index}",
                    username=f"jobuser{index}",
                    password_hash="x",
                    name=f"用户{index}",
                    status="enabled",
                    phone=f"1390000000{index}",
                    email=f"job{index}@example.com",
                )
                for index in range(1, 3)
            ]
        )
        await session.commit()
    yield _Env(factory=factory, storage=storage, artifacts=ObjectStorageExportArtifactStore(storage))
    get_settings.cache_clear()


def _context(env: _Env, payload: ExportPayload) -> JobContext:
    """构造作业上下文（会话由 factory 开合）。"""

    @asynccontextmanager
    async def _open() -> AsyncIterator[AsyncSession]:
        async with env.factory() as session:
            yield session

    async def _report(done: int, total: int | None) -> None:
        return None

    async def _not_cancelled() -> bool:
        return False

    return JobContext(
        job_id=1,
        job_type=JOB_TYPE,
        service_key="platform",
        db_key="tenant_demo",
        payload=payload.to_job_payload(),
        tenant_id=None,
        max_attempts=1,
        open_session=_open,
        progress_reporter=_report,
        cancel_checker=_not_cancelled,
    )


def _job(env: _Env, *, plain: bool = False) -> ExportExecuteJob:
    """构造导出作业（注入本地存储 + 真实引擎）。"""
    return ExportExecuteJob(
        excel_exporter=OpenpyxlExporter(),
        print_exporter=StoragePrintExporter(storage=env.storage, templates=BuiltinPrintTemplateProvider()),
        artifacts=env.artifacts,
        limits=ExportLimits(),
    )


def _payload(*, plain: bool = False, biz: str = "users") -> ExportPayload:
    """构造导出意图。"""
    params: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    params.set("order", "asc")
    return ExportPayload(
        biz=biz,
        kind=KIND_EXCEL,
        params=params,
        ids=ConcurrentStableList[str](),
        plain=plain,
        actor=1001,
        tenant_code="demo",
    )


def _rows(content: bytes) -> list[tuple[object, ...]]:
    """读取 xlsx 行。"""
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    try:
        return list(workbook["数据"].iter_rows(values_only=True))
    finally:
        workbook.close()


async def test_execute_job_stores_masked_artifact(env: _Env) -> None:
    """异步导出：产物落存储、结果含 key / 条数、敏感列默认掩码。"""
    result = await _job(env).run(_context(env, _payload()))
    assert result.status == "succeeded"
    output = cast("ConcurrentStableDict[str, object]", result.output)
    key = str(output["object_key"])
    assert key.startswith("demo/exports/users/")
    assert int(cast("int", output["total"])) >= 2
    content = await env.storage.get(key)
    rows = _rows(content)
    phone = next(row[2] for row in rows[1:] if row[0] == "jobuser1")
    assert isinstance(phone, str) and "*" in phone


async def test_execute_job_plain(env: _Env) -> None:
    """payload.plain=True：明文导出（提交时固化的权限）。"""
    result = await _job(env).run(_context(env, _payload(plain=True)))
    output = cast("ConcurrentStableDict[str, object]", result.output)
    rows = _rows(await env.storage.get(str(output["object_key"])))
    phone = next(row[2] for row in rows[1:] if row[0] == "jobuser1")
    assert phone == "13900000001"


async def test_execute_job_unknown_biz(env: _Env) -> None:
    """未注册业务：抛 50401（由执行器转失败终态）。"""
    with pytest.raises(ExportBizNotRegisteredError):
        await _job(env).run(_context(env, _payload(biz="not-exists")))


async def test_cleanup_job_deletes_expired_artifact_only(env: _Env) -> None:
    """清理：过期作业产物被删且 result 写 expired_at；未过期不动。"""
    await env.storage.put("demo/exports/users/old.xlsx", b"PK-old", content_type="application/octet-stream")
    await env.storage.put("demo/exports/users/new.xlsx", b"PK-new", content_type="application/octet-stream")
    expired_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
    async with env.factory() as session:
        session.add_all(
            [
                SysJob(
                    job_type=JOB_TYPE,
                    service_key="platform",
                    domain_key="import_export",
                    status=JOB_STATUS_SUCCEEDED,
                    payload="{}",
                    result='{"object_key": "demo/exports/users/old.xlsx", "file_name": "old.xlsx"}',
                    finished_at=expired_at,
                ),
                SysJob(
                    job_type=JOB_TYPE,
                    service_key="platform",
                    domain_key="import_export",
                    status=JOB_STATUS_SUCCEEDED,
                    payload="{}",
                    result='{"object_key": "demo/exports/users/new.xlsx", "file_name": "new.xlsx"}',
                    finished_at=datetime.now(UTC).replace(tzinfo=None),
                ),
            ]
        )
        await session.commit()

    result = await ExportCleanupJob(artifacts=env.artifacts, limits=ExportLimits()).run(_context(env, _payload()))
    assert result.status == "succeeded"
    output = cast("ConcurrentStableDict[str, object]", result.output)
    assert int(cast("int", output["scanned"])) >= 1
    assert int(cast("int", output["cleaned"])) >= 1
    assert not await env.storage.exists("demo/exports/users/old.xlsx")
    assert await env.storage.exists("demo/exports/users/new.xlsx")

    async with env.factory() as session:
        jobs = (await session.execute(SysJob.__table__.select())).all()
    expired_rows = [row for row in jobs if row.result and "expired_at" in row.result]
    assert len(expired_rows) == 1
