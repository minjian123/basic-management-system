"""批量打印作业用例（Kiwi 2402）：超阈值转后台 / 作业体渲染与汇总 / 取消。"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import cast

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.api.deps import get_config_source, get_uow
from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.jobs.base import JobContext
from bms_core.jobs.spec import JobSubmission
from bms_core.print.base import (
    PRINT_CONTENT_TYPE,
    BasePrintExporter,
    PrintBatchResult,
    PrintDocument,
    PrintExportResult,
    PrintOptions,
)
from bms_core.transfer.base import ColumnSpec
from bms_report.domains.report.jobs import PrintBatchJob
from tests_support.auth import auth_headers

pytestmark = pytest.mark.kiwi_id(2402)


class _Config(BaseConfigSource):
    """固定值参数源。"""

    plugin_name = ""

    async def get_many(self, keys: ConcurrentStableList[str]) -> ConcurrentStableDict[str, str]:
        return ConcurrentStableDict({"export.pdf.sync_max_docs": "1"})


class _FakeUow(UnitOfWork):
    """事务工作单元替身（无库）。"""

    @property
    def session(self):  # pyright: ignore[reportIncompatibleMethodOverride] - 替身无库，返回占位对象
        """替身会话。

        Returns:
            object: 占位会话对象。
        """
        return object()

    def begin(self):
        """返回空事务上下文。

        Returns:
            object: 异步上下文管理器。
        """

        @asynccontextmanager
        async def _ctx() -> AsyncGenerator[None]:
            yield None

        return _ctx()

    async def commit(self) -> None:
        """空提交（替身无库）。"""

    async def rollback(self) -> None:
        """空回滚（替身无库）。"""


@dataclass
class _Capture:
    """捕获的作业提交。"""

    submissions: ConcurrentStableList[object]
    tenant_ids: ConcurrentStableList[object]


class _FakeExporter(BasePrintExporter):
    """打印导出替身：记录入参并返回固定产物。"""

    plugin_name = ""

    def __init__(self) -> None:
        self.calls: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()

    async def export_pdf(
        self, template_key: str, document: PrintDocument, *, options: PrintOptions | None = None
    ) -> PrintExportResult:
        """单条导出（替身不实现）。"""
        raise NotImplementedError

    async def export_list(
        self,
        title: str,
        columns: ConcurrentStableList[ColumnSpec],
        rows: ConcurrentStableList[ConcurrentStableDict[str, object]],
        *,
        options: PrintOptions | None = None,
    ) -> PrintExportResult:
        """列表导出（替身不实现）。"""
        raise NotImplementedError

    async def batch_print(
        self,
        keys: ConcurrentStableList[str],
        *,
        template_key: str,
        mode: str = "separate",
        options: PrintOptions | None = None,
        documents: ConcurrentStableList[PrintDocument] | None = None,
    ) -> PrintBatchResult:
        """批量打印（替身记录入参）。"""
        self.calls.add(
            ConcurrentStableDict(
                {
                    "keys": len(keys),
                    "mode": mode,
                    "documents": None if documents is None else len(documents),
                    "template_key": template_key,
                }
            )
        )
        item = PrintExportResult(
            object_key=f"demo/prints/{template_key}/{keys[0]}.pdf",
            file_name="a.pdf",
            size=10,
            content_type=PRINT_CONTENT_TYPE,
            url="file://a.pdf",
            expires_in=60,
        )
        return PrintBatchResult(total=len(keys), succeeded=len(keys), failed=0, items=ConcurrentStableList((item,)))


def _context(payload: ConcurrentStableDict[str, object], *, cancel: bool = False) -> JobContext:
    """构造作业上下文（无库）。"""

    @asynccontextmanager
    async def _open() -> AsyncGenerator[object]:
        yield object()

    async def _report(done: int, total: int | None) -> None:
        return None

    async def _cancelled() -> bool:
        return cancel

    return JobContext(
        job_id=1,
        job_type="print.batch.execute",
        service_key="report",
        db_key="tenant_demo",
        payload=payload,
        max_attempts=1,
        open_session=_open,
        progress_reporter=_report,
        cancel_checker=_cancelled,
    )


async def test_batch_job_renders_with_documents() -> None:
    """作业体：按 documents 渲染并回产物清单。"""
    exporter = _FakeExporter()
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "template_key": "generic_document",
            "keys": ConcurrentStableList(("A", "B")),
            "documents": ConcurrentStableList(({"biz_key": "A", "fields": {}, "rows": []},)),  # pyright: ignore[reportUnknownArgumentType]
            "mode": "separate",
            "options": {"paper": "A5", "orientation": "landscape", "watermark": "内部"},
        }
    )
    result = await PrintBatchJob(exporter=exporter).run(_context(payload))
    assert result.status == "succeeded"
    output = cast("ConcurrentStableDict[str, object]", result.output)
    assert output["total"] == 2
    assert output["succeeded"] == 2
    items = cast("ConcurrentStableList[object]", output["items"])
    assert len(items) == 1
    call = exporter.calls[0]
    assert call["keys"] == 2
    assert call["documents"] == 1
    assert call["mode"] == "separate"


async def test_batch_job_without_documents_passes_none() -> None:
    """作业体：无 documents 时传 None（渲染简版页）。"""
    exporter = _FakeExporter()
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {"template_key": "generic_document", "keys": ConcurrentStableList(("A",)), "mode": "merged"}
    )
    result = await PrintBatchJob(exporter=exporter).run(_context(payload))
    assert result.status == "succeeded"
    assert exporter.calls[0]["documents"] is None
    assert exporter.calls[0]["mode"] == "merged"


async def test_batch_job_canceled_before_start() -> None:
    """已请求取消：不执行导出。"""
    exporter = _FakeExporter()
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {"template_key": "generic_document", "keys": ConcurrentStableList(("A",))}
    )
    result = await PrintBatchJob(exporter=exporter).run(_context(payload, cancel=True))
    assert result.status == "canceled"
    assert len(exporter.calls) == 0


@pytest_asyncio.fixture
async def app_with_stubs(service_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FastAPI]:
    """路由级替身：uow / config 覆盖，runner 用替身捕获提交。"""
    capture = _Capture(submissions=ConcurrentStableList(), tenant_ids=ConcurrentStableList())

    class _Runner:
        async def submit(self, session: object, submission: object, *, tenant_id: object = None) -> object:
            """记录提交并返回带主键的记录。"""
            del session
            capture.submissions.add(submission)
            capture.tenant_ids.add(tenant_id)
            return SimpleNamespace(id=4242)

    monkeypatch.setattr("bms_report.jobs.build_runner", lambda: _Runner())
    service_app.dependency_overrides[get_uow] = _FakeUow
    service_app.dependency_overrides[get_config_source] = _Config
    service_app.state.capture = capture
    try:
        yield service_app
    finally:
        service_app.dependency_overrides.pop(get_uow, None)
        service_app.dependency_overrides.pop(get_config_source, None)


async def test_batch_over_threshold_submits_job(app_with_stubs: FastAPI) -> None:
    """超同步阈值：返回 task_id 且提交一条 `print.batch.execute` 作业。"""
    async with AsyncClient(transport=ASGITransport(app=app_with_stubs), base_url="http://test") as client:
        client.headers.update(auth_headers())
        response = await client.post(
            "/api/v1/prints/batch",
            json={"template_key": "generic_document", "keys": ["A", "B"], "documents": [{"biz_key": "A"}]},  # pyright: ignore[reportUnknownArgumentType]
        )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["task_id"] == "4242"
    capture = cast("_Capture", app_with_stubs.state.capture)
    assert len(capture.submissions) == 1
    submission = cast("JobSubmission", capture.submissions[0])
    assert submission.job_type == "print.batch.execute"
    payload = submission.payload
    assert payload["template_key"] == "generic_document"
    assert len(cast("ConcurrentStableList[object]", payload["keys"])) == 2
    assert len(cast("ConcurrentStableList[object]", payload["documents"])) == 1


async def test_batch_threshold_reads_print_key(app_with_stubs: FastAPI) -> None:
    """阈值从 `print.pdf.sync_max_docs` 读取：新键优先于旧键（旧键值更宽松也不生效）。"""

    class _BothKeys(BaseConfigSource):
        """同时提供新旧两键的参数源（新键严格、旧键宽松，用于区分读取来源）。"""

        plugin_name = ""

        async def get_many(self, keys: ConcurrentStableList[str]) -> ConcurrentStableDict[str, str]:
            """返回两键固定值。

            Args:
                keys: 请求键。

            Returns:
                ConcurrentStableDict[str, str]: 键值。
            """
            del keys
            return ConcurrentStableDict({"print.pdf.sync_max_docs": "1", "export.pdf.sync_max_docs": "99"})

    app_with_stubs.dependency_overrides[get_config_source] = _BothKeys
    async with AsyncClient(transport=ASGITransport(app=app_with_stubs), base_url="http://test") as client:
        client.headers.update(auth_headers())
        response = await client.post(
            "/api/v1/prints/batch",
            json={"template_key": "generic_document", "keys": ["A", "B"]},
        )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["task_id"] == "4242"


class _PartialFailExporter(_FakeExporter):
    """打印导出替身：整批部分失败（验证失败汇总与告警分支）。"""

    async def batch_print(
        self,
        keys: ConcurrentStableList[str],
        *,
        template_key: str,
        mode: str = "separate",
        options: PrintOptions | None = None,
        documents: ConcurrentStableList[PrintDocument] | None = None,
    ) -> PrintBatchResult:
        """批量打印：成功 1 / 失败 1。"""
        del mode, options, documents
        item = PrintExportResult(
            object_key=f"demo/prints/{template_key}/{keys[0]}.pdf",
            file_name="a.pdf",
            size=10,
            content_type=PRINT_CONTENT_TYPE,
            url="file://a.pdf",
            expires_in=60,
        )
        return PrintBatchResult(
            total=len(keys),
            succeeded=1,
            failed=1,
            items=ConcurrentStableList((item,)),
            message="部分单据渲染失败",
        )


async def test_batch_job_reports_partial_failure() -> None:
    """作业体：部分失败仍回成功终态，汇总带失败计数。"""
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {"template_key": "generic_document", "keys": ConcurrentStableList(("A", "B"))}
    )
    result = await PrintBatchJob(exporter=_PartialFailExporter()).run(_context(payload))
    output = cast("ConcurrentStableDict[str, object]", result.output)
    assert result.status == "succeeded"
    assert output["succeeded"] == 1
    assert output["failed"] == 1


class _TolerantExporter(_FakeExporter):
    """打印导出替身：不索引键集合（空集合也回空汇总）。"""

    async def batch_print(
        self,
        keys: ConcurrentStableList[str],
        *,
        template_key: str,
        mode: str = "separate",
        options: PrintOptions | None = None,
        documents: ConcurrentStableList[PrintDocument] | None = None,
    ) -> PrintBatchResult:
        """批量打印：按入参回汇总（空集合回零）。"""
        self.calls.add(
            ConcurrentStableDict(
                {"keys": len(keys), "mode": mode, "documents": 0 if documents is None else len(documents)}
            )
        )
        return PrintBatchResult(total=len(keys), succeeded=len(keys), failed=0, items=ConcurrentStableList())


async def test_batch_job_tolerates_broken_payload_items() -> None:
    """作业体：键集合非可迭代 / 单据数据含非映射项 / 明细行含非映射项均按空处理。"""
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "template_key": "generic_document",
            "keys": "not-a-list",
            "documents": ConcurrentStableList(
                ("bad", {"biz_key": None, "rows": ConcurrentStableList(("x", {"项": "值"}))})
            ),
        }
    )
    # 键集合非可迭代 → 空集合；单据数据里的非映射项 / 非映射明细行按空处理
    result = await PrintBatchJob(exporter=_TolerantExporter()).run(_context(payload))
    assert result.status == "succeeded"
    assert cast("ConcurrentStableDict[str, object]", result.output)["total"] == 0


def test_module_exporter_resolves_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    """模块级导出器解析：按配置项经插件注册表取实现。"""
    from bms_report.domains.report import jobs as report_jobs

    stub = object()
    seen: ConcurrentStableList[str] = ConcurrentStableList()

    def _resolve(plugin_key: str, plugin_name: str, *, expected_version: str | None = None) -> object:
        seen.add(f"{plugin_key}:{plugin_name}")
        return stub

    monkeypatch.setattr(report_jobs, "resolve_plugin", _resolve)
    assert report_jobs._exporter() is stub  # pyright: ignore[reportPrivateUsage]
    assert list(seen) == ["print_exporter:reportlab"]
