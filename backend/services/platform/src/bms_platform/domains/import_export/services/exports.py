"""导出域服务：定义解析 / 同源取数 / 脱敏 / 同步与异步编排 / 状态查询（04_02）。

- `ExportPayload`：端点解析后的导出意图（筛选参数 / 选中集合 / 明文标志 / 渲染参数），可序列化为
  `sys_job.payload`；明文权限在**提交时判定一次**并固化，作业进程不再读用户请求上下文。
- `ExportExecutor`：与作业体共用的核心——定义解析（`50401`）/ 同源取数（`count` 与 `fetch` 同一仓储
  过滤）/ 行数上限（`50404`）/ 脱敏 / 生成产物（Excel 落 `exports/` 段、列表 PDF 走打印出口）。
- `ExportService`：API 侧编排——阈值判定（同步 / 异步 / 0 行）、同步执行、作业提交、状态与产物取址。

口径：同步 Excel 直接回字节（不落存储、不建作业）；异步一律落对象存储并在作业 result 记产物 key，
供状态端点重新 presign 与清理作业回销。异步作业 `max_attempts=1`（导出结果依赖取数时点，不自动重试）。
"""

from __future__ import annotations

import contextlib
import json
import secrets
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableList,
)
from bms_core.core.config import Settings
from bms_core.core.exceptions import (
    ExportBizNotRegisteredError,
    ExportJobNotFoundError,
    ExportRowLimitExceededError,
    ParamError,
)
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.jobs.runner import JobRunner
from bms_core.jobs.spec import JobSubmission
from bms_core.masking.base import BaseMasker
from bms_core.masking.default import DefaultMasker
from bms_core.models.job import SysJob
from bms_core.permission.base import BasePermissionChecker
from bms_core.print.base import (
    DEFAULT_PAPER,
    PRINT_ORIENTATIONS,
    PRINT_PAPERS,
    PRINT_TONES,
    BasePrintExporter,
    PrintOptions,
)
from bms_core.storage.base import PresignedUrl
from bms_core.transfer.artifacts import ExportArtifactStore, build_export_object_key
from bms_core.transfer.base import ColumnSpec
from bms_core.transfer.export_definition import (
    EXPORT_ORDERS,
    BaseExportDefinition,
    ExportDefinitionRegistry,
    ExportQuery,
    parse_ids,
)
from bms_core.transfer.export_limits import ExportLimits
from bms_core.transfer.exporter import BaseExporter
from bms_core.transfer.masking import mask_rows
from bms_core.transfer.openpyxl_io import XLSX_CONTENT_TYPE

__all__ = [
    "CLEANUP_JOB_TYPE",
    "JOB_TYPE",
    "KIND_EXCEL",
    "KIND_PDF",
    "ExportArtifactData",
    "ExportExecutor",
    "ExportOutcome",
    "ExportPayload",
    "ExportService",
    "as_int",
    "build_export_masker",
    "validate_print_options",
]

_LOGGER = get_logger("bms")

JOB_TYPE = "platform.export.execute"
"""异步导出作业类型。"""

CLEANUP_JOB_TYPE = "platform.export.cleanup"
"""导出产物过期清理作业类型。"""

KIND_EXCEL = "excel"
"""导出类型：Excel。"""

KIND_PDF = "pdf"
"""导出类型：列表 PDF。"""

EXPORT_STATUS_URL = "/api/v1/exports/jobs/{job_id}"
"""状态查询地址模板（相对路径）。"""

_TIME_FORMAT = "%Y%m%d%H%M%S"
"""文件名时间戳格式（UTC）。"""

_MAX_TITLE = 64
"""PDF 标题最大字符数。"""

_MAX_WATERMARK = 64
"""水印最大字符数。"""

ProgressCallback = Callable[[int, int], Awaitable[None]]
"""进度回调：`(已完成, 总量)`。"""


def validate_print_options(*, paper: str, orientation: str) -> None:
    """校验纸张 / 方向取值（非法即 `10001`）。

    校验前置到**意图构造**阶段（`_payload`）：参数非法时既不查库也不渲染，直接失败——
    否则「当前筛选无数据」会先返回成功，把非法参数吞掉（共享库并行下表现为间歇性 `0 != 10001`）。

    Args:
        paper: 纸张。
        orientation: 纸张方向。

    Raises:
        ParamError: 纸张 / 方向非法（`10001`）。
    """
    if paper not in PRINT_PAPERS:
        raise ParamError(f"纸张取值非法：{paper}")
    if orientation not in PRINT_ORIENTATIONS:
        raise ParamError(f"纸张方向非法：{orientation}")


class _FixedPlainChecker(BasePermissionChecker):
    """固定布尔权限检查器（作业期按提交时固化的明文权限判定，不读请求快照）。"""

    plugin_name = ""

    def __init__(self, allow_plain: bool) -> None:
        """初始化。

        Args:
            allow_plain: 是否放行明文（`data:plain`）。
        """
        self._allow_plain = allow_plain

    def check(self, code: str) -> bool:
        """是否持指定权限码。

        Args:
            code: 权限码。

        Returns:
            bool: 仅 `data:plain` 且提交时持有时为 True。
        """
        return self._allow_plain and code == "data:plain"


def build_export_masker(settings: Settings, plain: bool) -> BaseMasker:
    """按提交时固化的明文标志构造掩码器（作业期与同步分支共用）。

    Args:
        settings: 应用配置（取掩码字符与全局字段规则）。
        plain: 是否放行明文。

    Returns:
        BaseMasker: 掩码器实例。
    """
    options = settings.masking.options
    mask_char = str(options.get("mask_char") or "*")
    raw_rules = options.get("rules")
    rules: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    if isinstance(raw_rules, Mapping):
        for key, value in cast("Mapping[object, object]", raw_rules).items():
            rules.set(str(key), str(value))
    return DefaultMasker(checker=_FixedPlainChecker(plain), mask_char=mask_char, rules=rules)


@dataclass(frozen=True)
class ExportArtifactData(BaseValueObject):
    """导出产物（服务层数据；API 侧映射为响应契约）。"""

    object_key: str
    """产物对象 key。"""

    file_name: str
    """文件名。"""

    size: int
    """字节数。"""

    content_type: str
    """内容类型。"""

    url: str | None = None
    """限时取址（预签名失败时为空）。"""

    expires_in: int = 0
    """有效期（秒）。"""

    def to_result(self) -> ConcurrentStableDict[str, object]:
        """转作业结果摘要（落 `sys_job.result`）。

        Returns:
            ConcurrentStableDict[str, object]: 结果字段。
        """
        return ConcurrentStableDict(
            {
                "object_key": self.object_key,
                "file_name": self.file_name,
                "size": self.size,
                "content_type": self.content_type,
            }
        )


@dataclass(frozen=True)
class ExportPayload(BaseValueObject):
    """导出意图（端点解析产物；可序列化为作业负载）。"""

    biz: str
    """业务标识。"""

    kind: str
    """导出类型（excel / pdf）。"""

    params: ConcurrentStableDict[str, str] = field(default_factory=lambda: ConcurrentStableDict[str, str]())
    """筛选参数（kw / status / order_by / order）。"""

    ids: ConcurrentStableList[str] = field(default_factory=lambda: ConcurrentStableList[str]())
    """选中行主键（原始字符串，空 = 不限定）。"""

    plain: bool = False
    """是否放行明文（提交时判定并固化）。"""

    actor: int | None = None
    """操作人（用户主键）。"""

    tenant_code: str | None = None
    """租户编码（对象 key 前缀与作业租户位）。"""

    title: str = ""
    """PDF 标题（空 = 取定义标题）。"""

    paper: str = DEFAULT_PAPER
    """纸张。"""

    orientation: str = PRINT_ORIENTATIONS[0]
    """纸张方向。"""

    watermark: str = ""
    """水印文案。"""

    def to_job_payload(self) -> ConcurrentStableDict[str, object]:
        """转作业负载（JSON 对象）。

        Returns:
            ConcurrentStableDict[str, object]: 作业负载。
        """
        return ConcurrentStableDict(
            {
                "biz": self.biz,
                "kind": self.kind,
                "params": ConcurrentStableDict(dict(self.params)),
                "ids": ConcurrentStableList(self.ids),
                "plain": self.plain,
                "actor": self.actor,
                "tenant_code": self.tenant_code,
                "title": self.title,
                "paper": self.paper,
                "orientation": self.orientation,
                "watermark": self.watermark,
            }
        )

    @classmethod
    def from_job_payload(cls, raw: ConcurrentStableDict[str, object]) -> ExportPayload:
        """从作业负载还原。

        Args:
            raw: 作业负载。

        Returns:
            ExportPayload: 导出意图。

        Raises:
            ParamError: 负载缺关键字段（`10001`）。
        """
        biz = raw.get("biz")
        kind = raw.get("kind")
        if not isinstance(biz, str) or not biz:
            raise ParamError("导出作业负载缺少 biz")
        if kind not in (KIND_EXCEL, KIND_PDF):
            raise ParamError(f"导出作业负载 kind 非法：{kind!r}")
        raw_params = raw.get("params")
        params: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        if isinstance(raw_params, Mapping):
            for key, value in cast("Mapping[object, object]", raw_params).items():
                params.set(str(key), "" if value is None else str(value))
        raw_ids = raw.get("ids")
        ids: ConcurrentStableList[str] = ConcurrentStableList()
        for item in _items(raw_ids):
            ids.add(str(item))
        actor = raw.get("actor")
        return cls(
            biz=biz,
            kind=cast("str", kind),
            params=params,
            ids=ids,
            plain=bool(raw.get("plain")),
            actor=actor if isinstance(actor, int) and not isinstance(actor, bool) else None,
            tenant_code=str(raw["tenant_code"]) if raw.get("tenant_code") else None,
            title=str(raw.get("title") or ""),
            paper=str(raw.get("paper") or DEFAULT_PAPER),
            orientation=str(raw.get("orientation") or PRINT_ORIENTATIONS[0]),
            watermark=str(raw.get("watermark") or ""),
        )


@dataclass(frozen=True)
class ExportOutcome(BaseValueObject):
    """导出编排结果（同步文件流 / 同步产物 / 异步受理 / 空结果）。"""

    async_mode: bool
    """是否转异步。"""

    empty: bool
    """是否 0 行（不生成空文件）。"""

    total: int
    """本次条数。"""

    job_id: int | None = None
    """作业主键（异步）。"""

    content: bytes | None = None
    """同步 Excel 文件流。"""

    file_name: str | None = None
    """同步 Excel 文件名。"""

    artifact: ExportArtifactData | None = None
    """同步 PDF 产物。"""


class ExportExecutor(BaseFrameworkObject):
    """导出核心：定义解析 / 同源取数 / 脱敏 / 产物生成（API 同步分支与作业体共用）。"""

    def __init__(
        self,
        *,
        definitions: ExportDefinitionRegistry,
        excel_exporter: BaseExporter,
        print_exporter: BasePrintExporter,
        artifacts: ExportArtifactStore,
        limits: ExportLimits,
    ) -> None:
        """初始化。

        Args:
            definitions: 导出定义注册表。
            excel_exporter: Excel 导出器（真实实现 `openpyxl`）。
            print_exporter: 打印导出（列表 PDF）。
            artifacts: 产物存储端口（落库 + 取址 + 删除）。
            limits: 生效参数。
        """
        self._definitions = definitions
        self._excel_exporter = excel_exporter
        self._print_exporter = print_exporter
        self._artifacts = artifacts
        self._limits = limits

    def definition(self, biz: str) -> BaseExportDefinition:
        """按业务标识取定义。

        Args:
            biz: 业务标识。

        Returns:
            BaseExportDefinition: 导出定义。

        Raises:
            ExportBizNotRegisteredError: 未注册（`50401`）。
        """
        definition = self._definitions.get(biz)
        if definition is None:
            raise ExportBizNotRegisteredError(f"导出业务未注册：{biz}")
        return definition

    def query_of(self, payload: ExportPayload) -> ExportQuery:
        """把导出意图解析为统一查询。

        Args:
            payload: 导出意图。

        Returns:
            ExportQuery: 导出查询。

        Raises:
            ParamError: `ids` 非法或排序方向非法（`10001`）。
        """
        order = payload.params.get("order") or "asc"
        if order not in EXPORT_ORDERS:
            raise ParamError(f"排序方向非法：{order}")
        params: ConcurrentStableDict[str, str] = ConcurrentStableDict(
            (key, value) for key, value in payload.params.items() if key not in ("kw", "status", "order_by", "order")
        )
        return ExportQuery(
            keyword=payload.params.get("kw") or None,
            status=payload.params.get("status") or None,
            ids=parse_ids(",".join(payload.ids)) if payload.ids else parse_ids(None),
            order_by=payload.params.get("order_by") or None,
            order=order,
            params=ConcurrentStableFrozenDict(dict(params)),
        )

    async def collect(
        self,
        session: DbSession,
        definition: BaseExportDefinition,
        query: ExportQuery,
        *,
        masker: BaseMasker,
        progress: ProgressCallback | None = None,
    ) -> tuple[ConcurrentStableList[ConcurrentStableDict[str, object]], int]:
        """分批取数并按字段声明脱敏。

        Args:
            session: 当前会话。
            definition: 导出定义。
            query: 导出查询。
            masker: 掩码器（按提交时固化的明文权限构造）。
            progress: 进度回调（可选）。

        Returns:
            tuple[ConcurrentStableList[ConcurrentStableDict[str, object]], int]: 行集与总条数。

        Raises:
            ExportRowLimitExceededError: 行数超过 `export.max_rows`（`50404`）。
        """
        total = await definition.count(session, query)
        if total > self._limits.max_rows:
            raise ExportRowLimitExceededError(f"导出行数超限（{total} > {self._limits.max_rows}）；请收窄筛选条件")
        rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
        offset = 0
        batch = self._limits.fetch_batch_size
        while offset < total:
            chunk = await definition.fetch(session, query, offset=offset, limit=batch)
            if not chunk:
                break
            for row in chunk:
                rows.add(row)
            offset += len(chunk)
            if progress is not None:
                await progress(min(offset, total), total)
            if offset > self._limits.max_rows:
                raise ExportRowLimitExceededError(f"导出行数超限（> {self._limits.max_rows}）；请收窄筛选条件")
        return mask_rows(rows, definition.masked_fields, masker), total

    async def render_excel(
        self,
        definition: BaseExportDefinition,
        rows: ConcurrentStableList[ConcurrentStableDict[str, object]],
    ) -> bytes:
        """把行集写成 xlsx 字节。

        Args:
            definition: 导出定义。
            rows: 已脱敏行集。

        Returns:
            bytes: xlsx 字节。
        """
        columns: ConcurrentStableList[ColumnSpec] = ConcurrentStableList(definition.columns)
        chunks: ConcurrentStableList[bytes] = ConcurrentStableList()
        async for chunk in self._excel_exporter.export(rows, columns=columns):
            chunks.add(chunk)
        return b"".join(chunks)

    def print_options(self, payload: ExportPayload) -> PrintOptions:
        """按意图构造渲染选项（取值非法回落缺省）。

        Args:
            payload: 导出意图。

        Returns:
            PrintOptions: 渲染选项。

        Raises:
            ParamError: 纸张 / 方向非法（`10001`）。
        """
        validate_print_options(paper=payload.paper, orientation=payload.orientation)
        return PrintOptions(
            paper=payload.paper,
            orientation=payload.orientation,
            tone=PRINT_TONES[0],
            watermark=payload.watermark[:_MAX_WATERMARK],
        )

    async def render_list_pdf(
        self,
        definition: BaseExportDefinition,
        payload: ExportPayload,
        rows: ConcurrentStableList[ConcurrentStableDict[str, object]],
    ) -> ExportArtifactData:
        """渲染列表 PDF（经打印出口落对象存储 + 限时取址）。

        Args:
            definition: 导出定义。
            payload: 导出意图。
            rows: 已脱敏行集。

        Returns:
            ExportArtifactData: 产物。
        """
        title = (payload.title or definition.title)[:_MAX_TITLE]
        columns: ConcurrentStableList[ColumnSpec] = ConcurrentStableList(definition.columns)
        result = await self._print_exporter.export_list(title, columns, rows, options=self.print_options(payload))
        return ExportArtifactData(
            object_key=result.object_key,
            file_name=result.file_name,
            size=result.size,
            content_type=result.content_type,
            url=result.url,
            expires_in=result.expires_in,
        )

    async def execute_and_store(
        self,
        session: DbSession,
        payload: ExportPayload,
        *,
        masker: BaseMasker,
        progress: ProgressCallback | None = None,
    ) -> tuple[ExportArtifactData, int]:
        """作业体：取数 → 脱敏 → 生成产物 → 落对象存储。

        Args:
            session: 当前会话。
            payload: 导出意图。
            masker: 掩码器（按固化的明文权限构造）。
            progress: 进度回调。

        Returns:
            tuple[ExportArtifactData, int]: 产物与总条数。
        """
        definition = self.definition(payload.biz)
        query = self.query_of(payload)
        rows, total = await self.collect(session, definition, query, masker=masker, progress=progress)
        if payload.kind == KIND_PDF:
            artifact = await self.render_list_pdf(definition, payload, rows)
            return artifact, total
        data = await self.render_excel(definition, rows)
        return await self._store_excel(definition, payload, data), total

    def excel_file_name(self, definition: BaseExportDefinition) -> str:
        """同步 / 异步 Excel 文件名（标题 + UTC 时间戳）。

        Args:
            definition: 导出定义。

        Returns:
            str: 文件名。
        """
        return f"{definition.title}_{datetime.now(UTC).strftime(_TIME_FORMAT)}.xlsx"

    async def presign(self, key: str) -> PresignedUrl:
        """为既存产物重新生成限时取址（状态端点复用）。

        Args:
            key: 产物对象 key。

        Returns:
            PresignedUrl: 预签名结果。
        """
        return await self._artifacts.presign(key, expires_in=self._limits.presign_ttl)

    async def _store_excel(
        self,
        definition: BaseExportDefinition,
        payload: ExportPayload,
        data: bytes,
    ) -> ExportArtifactData:
        """把 Excel 字节落对象存储并取址。"""
        token = secrets.token_urlsafe(18)
        key = build_export_object_key(payload.tenant_code, definition.biz, token, "xlsx")
        await self._artifacts.put(key, data, content_type=XLSX_CONTENT_TYPE)
        url = await self._artifacts.presign(key, expires_in=self._limits.presign_ttl)
        return ExportArtifactData(
            object_key=key,
            file_name=self.excel_file_name(definition),
            size=len(data),
            content_type=XLSX_CONTENT_TYPE,
            url=url.url,
            expires_in=url.expires_in,
        )


class ExportService(BaseFrameworkObject):
    """API 侧导出编排：阈值判定 / 同步执行 / 作业提交 / 状态查询。"""

    def __init__(
        self,
        *,
        executor: ExportExecutor,
        runner_factory: Callable[[], JobRunner],
        limits: ExportLimits,
    ) -> None:
        """初始化。

        Args:
            executor: 导出核心。
            runner_factory: 作业提交器工厂（零参调用返回 `JobRunner`）。
            limits: 生效参数。
        """
        self._executor = executor
        self._runner_factory = runner_factory
        self._limits = limits

    async def export_excel(
        self,
        *,
        payload: ExportPayload,
        uow: UnitOfWork,
        masker: BaseMasker,
        tenant_id: int | None,
    ) -> ExportOutcome:
        """列表导出 Excel（同步文件流 / 异步作业 / 0 行空结果）。

        Args:
            payload: 导出意图。
            uow: 请求级工作单元。
            masker: 请求期掩码器（同步分支直接使用）。
            tenant_id: 租户主键。

        Returns:
            ExportOutcome: 编排结果。
        """
        definition = self._executor.definition(payload.biz)
        query = self._executor.query_of(payload)
        session = cast("DbSession", uow.session)
        total = await definition.count(session, query)
        self._ensure_within_limit(total)
        if total == 0:
            return ExportOutcome(async_mode=False, empty=True, total=0)
        if total > self._limits.sync_max_rows:
            job_id = await self._submit(payload, uow=uow, tenant_id=tenant_id, total=total)
            return ExportOutcome(async_mode=True, empty=False, total=total, job_id=job_id)
        rows, _ = await self._executor.collect(session, definition, query, masker=masker)
        content = await self._executor.render_excel(definition, rows)
        return ExportOutcome(
            async_mode=False,
            empty=False,
            total=total,
            content=content,
            file_name=self._executor.excel_file_name(definition),
        )

    async def export_pdf(
        self,
        *,
        payload: ExportPayload,
        uow: UnitOfWork,
        masker: BaseMasker,
        tenant_id: int | None,
    ) -> ExportOutcome:
        """列表导出 PDF（同步产物 / 异步作业 / 0 行空结果）。

        Args:
            payload: 导出意图。
            uow: 请求级工作单元。
            masker: 请求期掩码器。
            tenant_id: 租户主键。

        Returns:
            ExportOutcome: 编排结果。
        """
        definition = self._executor.definition(payload.biz)
        query = self._executor.query_of(payload)
        session = cast("DbSession", uow.session)
        total = await definition.count(session, query)
        self._ensure_within_limit(total)
        if total == 0:
            return ExportOutcome(async_mode=False, empty=True, total=0)
        if total > self._limits.pdf_sync_max_docs:
            job_id = await self._submit(payload, uow=uow, tenant_id=tenant_id, total=total)
            return ExportOutcome(async_mode=True, empty=False, total=total, job_id=job_id)
        rows, _ = await self._executor.collect(session, definition, query, masker=masker)
        artifact = await self._executor.render_list_pdf(definition, payload, rows)
        return ExportOutcome(async_mode=False, empty=False, total=total, artifact=artifact)

    async def status(self, *, job_id: int, uow: UnitOfWork) -> ConcurrentStableDict[str, object]:
        """查询异步导出状态与产物（每次重新取址）。

        Args:
            job_id: 作业主键。
            uow: 请求级工作单元。

        Returns:
            ConcurrentStableDict[str, object]: 状态字段（API 侧映射为响应契约）。

        Raises:
            ExportJobNotFoundError: 作业不存在（`50402`）。
            ExportJobFailedError: 作业失败且无产物（`50405`）。
        """
        session = cast("DbSession", uow.session)
        statement = select(SysJob).where(SysJob.id == job_id, SysJob.job_type == JOB_TYPE)
        job = (await session.execute(statement)).scalars().first()
        if job is None:
            raise ExportJobNotFoundError(f"导出作业不存在：{job_id}")
        payload = ExportPayload.from_job_payload(_parse_json_object(job.payload))
        artifact = await self._artifact_of(job)
        return ConcurrentStableDict(
            {
                "job_id": int(job.id),
                "status": job.status,
                "kind": payload.kind,
                "biz": payload.biz,
                "total": int(job.progress_total or 0),
                "done": int(job.progress_done or 0),
                "artifact": artifact,
                "message": job.error,
            }
        )

    async def _artifact_of(self, job: object) -> ExportArtifactData | None:
        """从作业结果还原产物并重新取址（对象不存在时返回 None）。

        Args:
            job: `SysJob` 记录。

        Returns:
            ExportArtifactData | None: 产物或 None。
        """
        raw_result = getattr(job, "result", None)
        if not raw_result:
            return None
        result = _parse_json_object(str(raw_result))
        key = result.get("object_key")
        if not isinstance(key, str) or not key:
            return None
        url: str | None = None
        try:
            presigned = await self._executor.presign(key)
            url = presigned.url
        except Exception as exc:  # 取址失败不阻断状态查询（前端可重试）
            _LOGGER.warning("导出产物取址失败", object_key=key, error=str(exc))
        return ExportArtifactData(
            object_key=key,
            file_name=str(result.get("file_name") or ""),
            size=as_int(result.get("size")),
            content_type=str(result.get("content_type") or ""),
            url=url,
            expires_in=self._limits.presign_ttl if url else 0,
        )

    def _ensure_within_limit(self, total: int) -> None:
        """行数上限校验。

        Args:
            total: 总条数。

        Raises:
            ExportRowLimitExceededError: 超限（`50404`）。
        """
        if total > self._limits.max_rows:
            raise ExportRowLimitExceededError(f"导出行数超限（{total} > {self._limits.max_rows}）；请收窄筛选条件")

    async def _submit(
        self,
        payload: ExportPayload,
        *,
        uow: UnitOfWork,
        tenant_id: int | None,
        total: int,
    ) -> int:
        """提交异步导出作业。

        Args:
            payload: 导出意图。
            uow: 请求级工作单元。
            tenant_id: 租户主键。
            total: 总条数（写入进度总量）。

        Returns:
            int: 作业主键。
        """
        submission = JobSubmission(
            job_type=JOB_TYPE,
            payload=_with_total(payload.to_job_payload(), total),
            max_attempts=1,
        )
        session = cast("DbSession", uow.session)
        # 阈值判定读过库（隐式事务已开）：先结束只读事务，再开写事务提交作业，避免 begin 冲突
        in_transaction = getattr(session, "in_transaction", None)
        if callable(in_transaction) and in_transaction():
            await session.rollback()
        async with uow.begin():
            record = await self._runner_factory().submit(session, submission, tenant_id=tenant_id)
        return int(record.id)


def _with_total(payload: ConcurrentStableDict[str, object], total: int) -> ConcurrentStableDict[str, object]:
    """在负载里附加总条数（作业执行前即可展示进度总量）。

    Args:
        payload: 作业负载。
        total: 总条数。

    Returns:
        ConcurrentStableDict[str, object]: 新负载。
    """
    enriched: ConcurrentStableDict[str, object] = ConcurrentStableDict(dict(payload))
    enriched.set("total", total)
    return enriched


def _parse_json_object(raw: str) -> ConcurrentStableDict[str, object]:
    """解析 JSON 对象（非法 / 非对象回落空字典）。

    Args:
        raw: JSON 文本。

    Returns:
        ConcurrentStableDict[str, object]: 解析结果。
    """
    if not raw:
        return ConcurrentStableDict()
    parsed: object = None
    # 负载 / 结果解析失败按「无字段」处理（不是无声明降级：解析失败已在下方按空处理，无能力寻址语义）
    with contextlib.suppress(json.JSONDecodeError):
        parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        return ConcurrentStableDict()
    return ConcurrentStableDict(cast("dict[str, object]", parsed))


def _items(raw: object) -> ConcurrentStableList[object]:
    """把可迭代负载（JSON 数组 / 集合容器）统一为列表（字符串与映射不算）。

    Args:
        raw: 原始负载值。

    Returns:
        ConcurrentStableList[object]: 元素列表（不可迭代为空）。
    """
    items: ConcurrentStableList[object] = ConcurrentStableList()
    if isinstance(raw, str | bytes | dict) or not isinstance(raw, Iterable):
        return items
    for item in cast("Iterable[object]", raw):
        items.add(item)
    return items


def as_int(value: object, default: int = 0) -> int:
    """把 JSON 里的数值安全转为 int（非数值回落默认）。

    Args:
        value: 原始值。
        default: 回落值。

    Returns:
        int: 转换结果。
    """
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return default


def cleanup_targets(result: str | None) -> str | None:
    """从作业结果里取产物 key（清理用；无产物返回 None）。

    Args:
        result: `sys_job.result` 文本。

    Returns:
        str | None: 产物对象 key。
    """
    parsed = _parse_json_object(result or "")
    key = parsed.get("object_key")
    return key if isinstance(key, str) and key else None
