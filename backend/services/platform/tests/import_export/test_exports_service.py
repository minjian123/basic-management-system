"""导出编排 / 核心的边界分支：负载还原、查询构造、分批取数、PDF 分支、产物取址与作业提交。

这些分支多为防御与异常路径（取值非法 / 存储不可用 / 0 行 / 转后台），走真实 HTTP 链路代价高，
故用替身定义与替身产物端口直接打点。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import cast

import pytest

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.config import get_settings
from bms_core.core.exceptions import (
    ExportJobNotFoundError,
    ExportRowLimitExceededError,
    ParamError,
)
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.jobs.runner import JobRunner
from bms_core.masking.base import BaseMasker
from bms_core.print.base import (
    PRINT_ORIENTATIONS,
    BasePrintExporter,
    PrintBatchResult,
    PrintDocument,
    PrintExportResult,
    PrintOptions,
)
from bms_core.storage.base import PresignedUrl
from bms_core.transfer.artifacts import ExportArtifactStore
from bms_core.transfer.base import ColumnSpec
from bms_core.transfer.export_definition import BaseExportDefinition, ExportDefinitionRegistry, ExportQuery
from bms_core.transfer.export_limits import ExportLimits
from bms_core.transfer.exporter import BaseExporter
from bms_platform.domains.import_export.services import exports as exports_module
from bms_platform.domains.import_export.services.exports import (
    KIND_EXCEL,
    KIND_PDF,
    ExportExecutor,
    ExportPayload,
    ExportService,
    as_int,
    build_export_masker,
)

pytestmark = pytest.mark.kiwi_id(2402)

_COLUMNS: ConcurrentStableFrozenList[ColumnSpec] = ConcurrentStableFrozenList(
    (ColumnSpec(key="username", title="登录账号"),)
)


class _Definition(BaseExportDefinition):
    """导出定义替身（不连库；条数与批次可控）。"""

    biz = "demo"
    title = "演示导出"

    def __init__(self, *, total: int = 2, chunk: int = 2, empty_after_first: bool = False) -> None:
        """初始化。

        Args:
            total: 统计条数。
            chunk: 每批返回行数。
            empty_after_first: 首批之后返回空批（验证提前结束）。
        """
        self._total = total
        self._chunk = chunk
        self._empty_after_first = empty_after_first
        self.calls: ConcurrentStableList[int] = ConcurrentStableList()

    @property
    def columns(self) -> ConcurrentStableFrozenList[ColumnSpec]:
        """列集。"""
        return _COLUMNS

    async def count(self, session: object, query: ExportQuery) -> int:
        """统计条数。"""
        return self._total

    async def fetch(
        self, session: object, query: ExportQuery, *, offset: int, limit: int
    ) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
        """分批取数。"""
        self.calls.add(offset)
        if self._empty_after_first and offset > 0:
            empty: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
            return empty
        rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
        for index in range(min(self._chunk, max(self._total - offset, 0))):
            rows.add(ConcurrentStableDict({"username": f"user{offset + index}"}))
        return rows


class _Artifacts:
    """产物端口替身（预签名可控失败）。"""

    def __init__(self, *, fail_presign: bool = False) -> None:
        """初始化。

        Args:
            fail_presign: 预签名是否抛错。
        """
        self._fail = fail_presign
        self.keys: ConcurrentStableList[str] = ConcurrentStableList()

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        """写入（记录 key）。"""
        self.keys.add(key)

    async def presign(self, key: str, *, expires_in: int | None = None) -> PresignedUrl:
        """预签名。

        Raises:
            RuntimeError: 构造时声明失败。
        """
        if self._fail:
            raise RuntimeError("存储不可用")
        return PresignedUrl(url=f"https://example.test/{key}", expires_in=expires_in or 60)

    async def delete(self, key: str) -> None:
        """删除（记录 key）。"""
        self.keys.add(key)

    async def exists(self, key: str) -> bool:
        """是否存在（替身恒 True）。"""
        return True


class _PrintExporter(BasePrintExporter):
    """打印导出替身（列表 PDF 恒返回占位产物）。"""

    async def export_pdf(
        self, template_key: str, document: PrintDocument, *, options: PrintOptions | None = None
    ) -> PrintExportResult:
        """单条（未使用）。

        Raises:
            NotImplementedError: 替身不实现。
        """
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
        """批量（未使用）。

        Raises:
            NotImplementedError: 替身不实现。
        """
        raise NotImplementedError

    async def export_list(
        self,
        title: str,
        columns: ConcurrentStableList[ColumnSpec],
        rows: ConcurrentStableList[ConcurrentStableDict[str, object]],
        *,
        options: PrintOptions | None = None,
    ) -> PrintExportResult:
        """列表 PDF：回固定产物。"""
        assert list(columns) == list(_COLUMNS)
        return PrintExportResult(
            object_key=f"demo/prints/list/{title}.pdf",
            file_name=f"{title}.pdf",
            size=len(rows),
            content_type="application/pdf",
            url="https://example.test/list.pdf",
            expires_in=600,
        )


@dataclass
class _Job:
    """作业记录替身。"""

    id: int = 7
    status: str = "succeeded"
    payload: str = '{"biz": "demo", "kind": "excel"}'
    result: str | None = None
    progress_total: int = 2
    progress_done: int = 2
    error: str | None = None


@dataclass
class _Scalars:
    """`scalars()` 结果替身。"""

    job: object | None

    def first(self) -> object | None:
        """取首条。"""
        return self.job


@dataclass
class _Result:
    """`execute()` 结果替身。"""

    job: object | None

    def scalars(self) -> _Scalars:
        """标量集合。"""
        return _Scalars(self.job)


class _Session:
    """会话替身（仅供状态查询与事务判定）。"""

    def __init__(self, job: object | None = None) -> None:
        """初始化。

        Args:
            job: 状态查询返回的作业。
        """
        self._job = job
        self.rolled_back = False

    def in_transaction(self) -> bool:
        """恒视为处于只读事务（验证提交前回滚）。"""
        return True

    async def rollback(self) -> None:
        """记录回滚。"""
        self.rolled_back = True

    async def execute(self, statement: object) -> _Result:
        """执行查询（恒返回替身作业）。"""
        return _Result(self._job)


@dataclass
class _Uow:
    """工作单元替身。"""

    session: object

    @asynccontextmanager
    async def begin(self):
        """开启事务（直接让出）。"""
        yield None


@dataclass
class _Runner:
    """作业提交器替身。"""

    submitted: ConcurrentStableList[object] = field(default_factory=lambda: ConcurrentStableList[object]())

    async def submit(self, session: object, submission: object, *, tenant_id: int | None = None) -> object:
        """提交作业（记录并回主键）。"""
        self.submitted.add(submission)
        return type("Record", (), {"id": 42})()


def _executor(*, total: int = 2, chunk: int = 2, artifacts: _Artifacts | None = None) -> ExportExecutor:
    """构造导出核心（替身定义 + 替身产物端口）。"""
    registry = ExportDefinitionRegistry()
    definition = _Definition(total=total, chunk=chunk)
    registry.register(definition)
    from bms_core.transfer.openpyxl_exporter import OpenpyxlExporter

    return ExportExecutor(
        definitions=registry,
        excel_exporter=OpenpyxlExporter(),
        print_exporter=_PrintExporter(),
        artifacts=cast("ExportArtifactStore", artifacts or _Artifacts()),
        limits=ExportLimits(),
    )


def _service(executor: ExportExecutor, *, runner: object | None = None) -> ExportService:
    """构造导出编排服务。"""
    resolved = runner or _Runner()
    return ExportService(
        executor=executor,
        runner_factory=lambda: cast("JobRunner", resolved),
        limits=ExportLimits(),
    )


def _masker() -> BaseMasker:
    """构造掩码器（无明文权限）。"""
    return build_export_masker(get_settings(), plain=False)


def _payload(kind: str = KIND_EXCEL, **overrides: object) -> ExportPayload:
    """构造导出意图。"""
    params = ConcurrentStableDict({"order": "asc"})
    base: ConcurrentStableDict[str, object] = ConcurrentStableDict({"biz": "demo", "kind": kind, "params": params})
    base.update(overrides)
    return ExportPayload(**dict(base))  # pyright: ignore[reportArgumentType]


def test_masker_applies_configured_rules() -> None:
    """掩码器按 `[masking].options` 取掩码字符与字段规则；明文标志决定放行。"""
    settings = get_settings()
    options = ConcurrentStableDict({"mask_char": "#", "rules": ConcurrentStableDict({"phone": "phone"})})
    patched = settings.model_copy(update={"masking": settings.masking.model_copy(update={"options": options})})

    masker = build_export_masker(patched, plain=False)
    assert masker.check_plain() is False
    masked = masker.mask("phone", "13800000001")
    assert isinstance(masked, str) and "#" in masked

    plain_masker = build_export_masker(patched, plain=True)
    assert plain_masker.check_plain() is True


def test_payload_from_job_payload_rejects_broken_fields() -> None:
    """作业负载还原：缺 biz / kind 非法即拒（10001）。"""
    with pytest.raises(ParamError, match="缺少 biz"):
        ExportPayload.from_job_payload(ConcurrentStableDict({"kind": KIND_EXCEL}))
    with pytest.raises(ParamError, match="kind 非法"):
        ExportPayload.from_job_payload(ConcurrentStableDict({"biz": "demo", "kind": "csv"}))


def test_payload_from_job_payload_normalizes_values() -> None:
    """作业负载还原：参数为空值转空串、ids 归一为字符串、actor 非整数回落 None。"""
    payload = ExportPayload.from_job_payload(
        ConcurrentStableDict(
            {
                "biz": "demo",
                "kind": KIND_PDF,
                "params": ConcurrentStableDict({"kw": None, "status": "enabled"}),
                "ids": ConcurrentStableList(("1", 2)),
                "actor": "bad",
                "tenant_code": "demo",
                "paper": "",
                "orientation": None,
            }
        )
    )
    assert dict(payload.params) == {"kw": "", "status": "enabled"}
    assert list(payload.ids) == ["1", "2"]
    assert payload.actor is None
    assert payload.tenant_code == "demo"
    assert payload.paper
    assert payload.orientation == PRINT_ORIENTATIONS[0]


def test_query_of_rejects_illegal_order() -> None:
    """查询构造：排序方向非白名单即拒。"""
    executor = _executor()
    params = ConcurrentStableDict({"order": "up"})
    with pytest.raises(ParamError, match="排序方向非法"):
        executor.query_of(ExportPayload(biz="demo", kind=KIND_EXCEL, params=params))


def test_query_of_maps_filters_and_ids() -> None:
    """查询构造：筛选参数映射为查询字段，其余参数原样带出，ids 去重保序。"""
    executor = _executor()
    params = ConcurrentStableDict({"kw": "u", "status": "enabled", "order_by": "username", "order": "desc"})
    query = executor.query_of(
        ExportPayload(biz="demo", kind=KIND_EXCEL, params=params, ids=ConcurrentStableList(("3", "1", "3")))
    )
    assert query.keyword == "u"
    assert query.status == "enabled"
    assert query.order_by == "username"
    assert tuple(query.ids) == (3, 1)


def test_print_options_rejects_illegal_orientation() -> None:
    """渲染选项：纸张方向非白名单即拒；水印超长截断。"""
    executor = _executor()
    with pytest.raises(ParamError, match="纸张方向非法"):
        executor.print_options(ExportPayload(biz="demo", kind=KIND_PDF, orientation="斜"))

    options = executor.print_options(ExportPayload(biz="demo", kind=KIND_PDF, watermark="水" * 200))
    assert options.watermark
    assert len(options.watermark) < 200


async def test_collect_breaks_on_empty_chunk_and_reports_progress() -> None:
    """取数：空批提前结束（不空转），进度按批回调。"""
    executor = _executor(total=3, chunk=2)
    definition = _Definition(total=3, chunk=2, empty_after_first=True)
    seen: ConcurrentStableList[int] = ConcurrentStableList()

    async def _progress(done: int, total: int) -> None:
        seen.add(done)

    rows, total = await executor.collect(
        cast("DbSession", None), definition, ExportQuery(), masker=_masker(), progress=_progress
    )
    assert total == 3
    assert len(rows) == 2
    assert list(seen) == [2]
    assert list(definition.calls) == [0, 2]


async def test_collect_rejects_over_max_rows() -> None:
    """取数：统计超上限即拒（50404），不进入分批。"""
    executor = ExportExecutor(
        definitions=ExportDefinitionRegistry(),
        excel_exporter=cast("BaseExporter", object()),
        print_exporter=_PrintExporter(),
        artifacts=cast("ExportArtifactStore", _Artifacts()),
        limits=ExportLimits(max_rows=1),
    )
    with pytest.raises(ExportRowLimitExceededError):
        await executor.collect(cast("DbSession", None), _Definition(total=5), ExportQuery(), masker=_masker())


async def test_execute_and_store_pdf_branch_and_presign() -> None:
    """作业体：PDF 分支走列表打印出口；预签名按参数回有效期。"""
    executor = _executor()
    artifact, total = await executor.execute_and_store(cast("DbSession", None), _payload(KIND_PDF), masker=_masker())
    assert total == 2
    assert artifact.object_key.startswith("demo/prints/list/")
    assert artifact.url

    presigned = await executor.presign("demo/exports/demo/x.xlsx")
    assert presigned.url.endswith("x.xlsx")


async def test_export_pdf_empty_and_async() -> None:
    """列表 PDF：0 行回空结果；超同步上限转后台作业（提交时先结束只读事务）。"""
    empty_service = _service(_executor(total=0))
    session = _Session()
    outcome = await empty_service.export_pdf(
        payload=_payload(KIND_PDF), uow=cast("UnitOfWork", _Uow(session=session)), masker=_masker(), tenant_id=None
    )
    assert outcome.empty is True
    assert outcome.async_mode is False

    runner = _Runner()
    async_service = _service(_executor(total=100), runner=runner)
    busy_session = _Session()
    async_outcome = await async_service.export_pdf(
        payload=_payload(KIND_PDF),
        uow=cast("UnitOfWork", _Uow(session=busy_session)),
        masker=_masker(),
        tenant_id=None,
    )
    assert async_outcome.async_mode is True
    assert async_outcome.job_id == 42
    assert busy_session.rolled_back is True
    assert len(runner.submitted) == 1


async def test_status_maps_job_and_resigns_artifact() -> None:
    """状态查询：作业字段映射为状态结构，产物每次重新取址。"""
    job = _Job(result='{"object_key": "demo/exports/demo/x.xlsx", "file_name": "x.xlsx", "size": 3}')
    service = _service(_executor())
    status = await service.status(job_id=7, uow=cast("UnitOfWork", _Uow(session=_Session(job))))
    assert status["job_id"] == 7
    assert status["kind"] == KIND_EXCEL
    artifact = status["artifact"]
    assert getattr(artifact, "url", None)  # 取址成功
    assert getattr(artifact, "size", None) == 3


async def test_status_missing_job_and_artifact_variants() -> None:
    """状态查询：作业不存在 50402；产物取不到时回空（不阻断状态）。"""
    service = _service(_executor())
    with pytest.raises(ExportJobNotFoundError):
        await service.status(job_id=404, uow=cast("UnitOfWork", _Uow(session=_Session(None))))

    # 无 result / key 非字符串 → 无产物
    assert await service._artifact_of(_Job(result=None)) is None  # pyright: ignore[reportPrivateUsage]
    assert await service._artifact_of(_Job(result='{"object_key": 1}')) is None  # pyright: ignore[reportPrivateUsage]
    # 取址失败 → 产物不带 url
    failing = _service(_executor(artifacts=_Artifacts(fail_presign=True)))
    artifact = await failing._artifact_of(_Job(result='{"object_key": "k", "file_name": "k.xlsx"}'))  # pyright: ignore[reportPrivateUsage]
    assert artifact is not None
    assert artifact.url is None


def test_json_and_value_helpers() -> None:
    """JSON / 集合 / 数值助手：空值与异常输入按空处理。"""
    assert dict(exports_module._parse_json_object(cast("str", None))) == {}  # pyright: ignore[reportPrivateUsage]
    assert dict(exports_module._parse_json_object("not-json")) == {}  # pyright: ignore[reportPrivateUsage]
    assert dict(exports_module._parse_json_object("[1, 2]")) == {}  # pyright: ignore[reportPrivateUsage]

    assert list(exports_module._items("abc")) == []  # pyright: ignore[reportPrivateUsage]
    assert list(exports_module._items(ConcurrentStableList((1, 2)))) == [1, 2]  # pyright: ignore[reportPrivateUsage]

    assert as_int(True) == 1
    assert as_int(5) == 5
    assert as_int(" 12 ") == 12
    assert as_int("x", 9) == 9


async def test_collect_rejects_when_actual_rows_exceed_limit() -> None:
    """取数：统计与实际行数不一致时按实际累加值兜底拒绝（防御统计漂移）。"""
    executor = ExportExecutor(
        definitions=ExportDefinitionRegistry(),
        excel_exporter=cast("BaseExporter", object()),
        print_exporter=_PrintExporter(),
        artifacts=cast("ExportArtifactStore", _Artifacts()),
        limits=ExportLimits(max_rows=2, fetch_batch_size=10),
    )

    class _DriftingDefinition(_Definition):
        """统计回 1 行、实际每批回 3 行（模拟统计与取数漂移）。"""

        async def fetch(
            self, session: object, query: ExportQuery, *, offset: int, limit: int
        ) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
            """恒定回 3 行。"""
            del session, query, offset, limit
            rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
            for index in range(3):
                rows.add(ConcurrentStableDict({"username": f"drift{index}"}))
            return rows

    # count 回 1（在限内），但 fetch 一次返回 3 行 ⇒ 累加越限即拒
    with pytest.raises(ExportRowLimitExceededError):
        await executor.collect(cast("DbSession", None), _DriftingDefinition(total=1), ExportQuery(), masker=_masker())
