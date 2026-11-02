"""导出作业用例：异步导出落产物 / 明文与掩码 / 失败 / 产物过期清理。"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
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

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ExportBizNotRegisteredError
from bms_core.jobs.base import JobContext
from bms_core.models.job import JOB_STATUS_SUCCEEDED, SysJob
from bms_core.models.platform.user import SysUser
from bms_core.print.exporter import StoragePrintExporter
from bms_core.print.templates import BuiltinPrintTemplateProvider
from bms_core.storage.local import LocalObjectStorage
from bms_core.testing.schema import ensure_tables
from bms_core.transfer.artifacts import ExportArtifactStore, ObjectStorageExportArtifactStore
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
    async def _open() -> AsyncGenerator[AsyncSession]:
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


def _rows(content: bytes) -> ConcurrentStableList[ConcurrentStableFrozenList[object]]:
    """读取 xlsx 行。"""
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    try:
        rows: ConcurrentStableList[ConcurrentStableFrozenList[object]] = ConcurrentStableList()
        for row in workbook["数据"].iter_rows(values_only=True):
            rows.add(ConcurrentStableFrozenList(row))
        return rows
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
    phone = next(row[2] for row in rows if row[0] == "jobuser1")
    assert isinstance(phone, str) and "*" in phone


async def test_execute_job_plain(env: _Env) -> None:
    """payload.plain=True：明文导出（提交时固化的权限）。"""
    result = await _job(env).run(_context(env, _payload(plain=True)))
    output = cast("ConcurrentStableDict[str, object]", result.output)
    rows = _rows(await env.storage.get(str(output["object_key"])))
    phone = next(row[2] for row in rows if row[0] == "jobuser1")
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
    # 共享库带其他用例的作业：只判本用例两条的标记结果
    own = [row for row in jobs if row.result and ("old.xlsx" in row.result or "new.xlsx" in row.result)]
    assert len([row for row in own if "expired_at" in row.result]) == 1
    assert len([row for row in own if "expired_at" not in row.result]) == 1


def _canceled_context(env: _Env, payload: ExportPayload) -> JobContext:
    """构造「已请求取消」的作业上下文。"""

    @asynccontextmanager
    async def _open() -> AsyncGenerator[AsyncSession]:
        async with env.factory() as session:
            yield session

    async def _report(done: int, total: int | None) -> None:
        return None

    async def _cancelled() -> bool:
        return True

    return JobContext(
        job_id=2,
        job_type=JOB_TYPE,
        service_key="platform",
        db_key="tenant_demo",
        payload=payload.to_job_payload(),
        tenant_id=None,
        max_attempts=1,
        open_session=_open,
        progress_reporter=_report,
        cancel_checker=_cancelled,
    )


async def test_execute_job_canceled_before_store(env: _Env) -> None:
    """进度回调处发现已取消：作业回取消终态（不落产物）。"""
    result = await _job(env).run(_canceled_context(env, _payload()))
    assert result.status == "canceled"


async def test_cleanup_job_skips_marked_and_missing_key(env: _Env) -> None:
    """清理：已标记跳过、无产物键只标记不删、删除失败计 failed 且不中断。"""
    await env.storage.put("demo/exports/users/ok.xlsx", b"PK", content_type="application/octet-stream")
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
                    result='{"object_key": "demo/exports/users/ok.xlsx", "expired_at": "2026-01-01T00:00:00Z"}',
                    finished_at=expired_at,
                ),
                SysJob(
                    job_type=JOB_TYPE,
                    service_key="platform",
                    domain_key="import_export",
                    status=JOB_STATUS_SUCCEEDED,
                    payload="{}",
                    result='{"file_name": "no-key.xlsx"}',
                    finished_at=expired_at,
                ),
                SysJob(
                    job_type=JOB_TYPE,
                    service_key="platform",
                    domain_key="import_export",
                    status=JOB_STATUS_SUCCEEDED,
                    payload="{}",
                    result='{"object_key": "demo/exports/users/missing.xlsx"}',
                    finished_at=expired_at,
                ),
            ]
        )
        await session.commit()

    result = await ExportCleanupJob(
        artifacts=cast("ExportArtifactStore", _FailingDeleteStore(env.artifacts)),
        limits=ExportLimits(),
    ).run(_context(env, _payload()))
    output = cast("ConcurrentStableDict[str, object]", result.output)
    # 已标记的那条不计入扫描；无键与删除失败两条计入
    assert int(cast("int", output["scanned"])) >= 2
    assert int(cast("int", output["failed"])) >= 1
    # 已标记记录的产物未被删除
    assert await env.storage.exists("demo/exports/users/ok.xlsx")


async def test_cleanup_job_canceled_stops_loop(env: _Env) -> None:
    """清理：批间发现取消即停止，仍回成功汇总。"""
    expired_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
    async with env.factory() as session:
        session.add(
            SysJob(
                job_type=JOB_TYPE,
                service_key="platform",
                domain_key="import_export",
                status=JOB_STATUS_SUCCEEDED,
                payload="{}",
                result='{"file_name": "cancel.xlsx"}',
                finished_at=expired_at,
            )
        )
        await session.commit()

    result = await ExportCleanupJob(artifacts=env.artifacts, limits=ExportLimits()).run(
        _canceled_context(env, _payload())
    )
    assert result.status == "succeeded"


def test_result_helpers_tolerate_missing_and_broken_json() -> None:
    """结果读写助手：空值 / 非法 JSON 按「无标记」处理，已标记的原样保留。"""
    from bms_platform.domains.import_export import export_jobs

    is_expired = vars(export_jobs)["_is_expired"]
    with_expired = vars(export_jobs)["_with_expired"]

    assert is_expired(None) is False
    assert is_expired("not-json") is False
    assert is_expired('{"expired_at": "2026-01-01T00:00:00Z"}') is True

    assert "expired_at" in with_expired(None)
    assert "expired_at" in with_expired("not-json")
    assert "expired_at" in with_expired('{"object_key": "k"}')
    assert with_expired('{"expired_at": "keep"}') == '{"expired_at": "keep"}'


def test_worker_dependency_resolvers_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """worker 依赖解析：服务间客户端不可用时回落空实现，参数源 / 插件按实现解析。"""
    from bms_core.config.null import NullConfigSource
    from bms_core.core.exceptions import ServiceUnavailableError
    from bms_core.servicecall.null import NullServiceClient
    from bms_platform.domains.import_export import export_jobs

    def _unavailable() -> object:
        raise ServiceUnavailableError("未启用")

    monkeypatch.setattr(export_jobs, "build_service_client", _unavailable)
    client = export_jobs._service_client()  # pyright: ignore[reportPrivateUsage]
    assert isinstance(client, NullServiceClient)
    assert isinstance(export_jobs._config_source(), NullConfigSource)  # pyright: ignore[reportPrivateUsage]

    plugins: ConcurrentStableList[str] = ConcurrentStableList()
    stub = object()

    def _resolve(plugin_key: str, plugin_name: str, *, expected_version: str | None = None) -> object:
        plugins.add(f"{plugin_key}:{plugin_name}")
        return stub

    monkeypatch.setattr(export_jobs, "resolve_plugin", _resolve)
    settings = get_settings()
    assert export_jobs._artifacts(settings) is not None  # pyright: ignore[reportPrivateUsage]
    assert export_jobs._excel_exporter(settings) is stub  # pyright: ignore[reportPrivateUsage]
    assert export_jobs._print_exporter(settings) is stub  # pyright: ignore[reportPrivateUsage]
    assert list(plugins) == ["object_storage:local", "exporter:openpyxl", "print_exporter:reportlab"]

    # 服务间客户端可用时参数源走 HTTP 实现
    monkeypatch.setattr(export_jobs, "build_service_client", lambda: object())
    assert export_jobs._config_source() is not None  # pyright: ignore[reportPrivateUsage]


class _FailingDeleteStore:
    """产物端口替身：删除恒抛（验证单条失败不阻断整批）。"""

    def __init__(self, inner: ObjectStorageExportArtifactStore) -> None:
        """初始化。

        Args:
            inner: 真实端口（预签名走真实实现）。
        """
        self._inner = inner

    async def delete(self, key: str) -> None:
        """删除恒失败。

        Args:
            key: 产物对象 key。

        Raises:
            RuntimeError: 恒抛（模拟存储不可用）。
        """
        raise RuntimeError(f"存储不可用：{key}")

    async def presign(self, key: str, *, expires_in: int = 60) -> object:
        """预签名委托真实实现。"""
        return await self._inner.presign(key, expires_in=expires_in)


async def test_cleanup_job_with_all_marked_skips_marking(env: _Env) -> None:
    """清理：批内作业全部已标记 ⇒ 不重复写标记（空集合直接返回）。"""
    expired_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
    async with env.factory() as session:
        session.add(
            SysJob(
                job_type=JOB_TYPE,
                service_key="platform",
                domain_key="import_export",
                status=JOB_STATUS_SUCCEEDED,
                payload="{}",
                result='{"object_key": "demo/exports/users/marked.xlsx", "expired_at": "2026-01-01T00:00:00Z"}',
                finished_at=expired_at,
            )
        )
        await session.commit()

    result = await ExportCleanupJob(artifacts=env.artifacts, limits=ExportLimits()).run(_context(env, _payload()))
    output = cast("ConcurrentStableDict[str, object]", result.output)
    # 已标记的作业不删对象（共享库可能带其他用例的待处理行，只判本用例语义）
    assert result.status == "succeeded"
    assert int(cast("int", output["cleaned"])) == 0


async def test_mark_expired_skips_missing_job(env: _Env) -> None:
    """标记过期：作业主键不存在时跳过（不抛错、不写脏数据）。"""
    from bms_platform.domains.import_export import export_jobs

    mark_expired = vars(export_jobs)["_mark_expired"]
    # 空集合：直接返回（不写库）；不存在的主键：逐条跳过（不抛错）
    await mark_expired(_context(env, _payload()), ConcurrentStableList())
    await mark_expired(_context(env, _payload()), ConcurrentStableList((999999,)))
