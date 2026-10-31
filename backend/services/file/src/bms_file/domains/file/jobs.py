"""文件域内建作业：孤儿回收（`file.cleanup_orphans`，`BaseJobHandler` 具体实现样例）。

- 驱动方式由「内置任务 → file 内部端点」改为「作业中心提交 + 本服务 worker 执行」；
- 扫描 / 清理 / 置 `orphan` 仍全在 file 域（自有租户库 + 对象存储），作业中心不跨库写；
- 进度：以「扫描数」为总量、「回收数」为完成量上报；结果摘要返回扫描 / 回收 / 失败条数。
"""

from __future__ import annotations

from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.core.plugin import resolve_plugin
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_core.jobs.client import build_service_client
from bms_core.jobs.plugins import ensure_job_plugins
from bms_core.metrics.null import NullMetrics
from bms_core.outbox.store import SqlOutboxStore
from bms_core.servicecall.base import BaseServiceClient
from bms_core.servicecall.null import NullServiceClient
from bms_core.storage.base import BaseMultipartUpload, BaseObjectStorage
from bms_core.tenant_module.quota import TenantQuotaClient
from bms_file.domains.file.services.file import FileService

__all__ = ["CleanupOrphansJob"]


class CleanupOrphansJob(BaseJobHandler):
    """回收超期未完成的上传（扫描 → 清分片 → 置 `orphan` → 发事件）。"""

    job_type = "file.cleanup_orphans"
    description = "回收超期上传分片与孤儿记录（file 域）"

    def __init__(
        self,
        *,
        storage: BaseObjectStorage | None = None,
        multipart: BaseMultipartUpload | None = None,
        service_client: BaseServiceClient | None = None,
    ) -> None:
        """初始化（能力实现可注入；缺省按配置解析，便于单测与排障）。

        Args:
            storage: 对象存储（None 按配置解析）。
            multipart: 分片上传（None 按配置解析）。
            service_client: 服务间调用客户端（None 按配置解析；未启用用空实现）。
        """
        self._storage = storage
        self._multipart = multipart
        self._service_client = service_client

    async def run(self, ctx: JobContext) -> JobResult:
        """执行孤儿回收并按扫描 / 回收数量上报进度。

        Args:
            ctx: 作业执行上下文。

        Returns:
            JobResult: 成功带扫描 / 回收 / 失败条数；异常由执行器统一转失败。
        """
        client = self._service_client if self._service_client is not None else _service_client()
        async with ctx.session() as session:
            service = FileService(
                uow=DbUnitOfWork(session),
                storage=self._storage if self._storage is not None else _storage(),
                multipart=self._multipart if self._multipart is not None else _multipart(),
                config=None,
                quota=TenantQuotaClient(
                    client,
                    tenant_id=None if ctx.tenant_id is None else str(ctx.tenant_id),
                    tenant_code=None,
                ),
                outbox=SqlOutboxStore(),
                audit=None,
                metrics=NullMetrics(),
            )
            result = await service.cleanup_orphans()
        await ctx.report_progress(result.orphaned, result.scanned)
        return JobResult.success(
            ConcurrentStableDict(
                {
                    "scanned": result.scanned,
                    "orphaned": result.orphaned,
                    "failed": result.failed,
                }
            ),
            message=f"孤儿回收完成：扫描 {result.scanned} / 回收 {result.orphaned} / 失败 {result.failed}",
        )


def _service_client() -> BaseServiceClient:
    """解析服务间调用客户端；未启用时用空实现（孤儿回收本身不依赖下游）。

    Returns:
        BaseServiceClient: 调用客户端。
    """
    try:
        return build_service_client()
    except ServiceUnavailableError:
        return NullServiceClient()


def _storage() -> BaseObjectStorage:
    """解析对象存储实现（worker 进程按需装配插件）。

    Returns:
        BaseObjectStorage: 对象存储实例。
    """
    settings = get_settings()
    ensure_job_plugins(settings)
    return cast(
        "BaseObjectStorage",
        resolve_plugin(
            "object_storage", settings.storage.provider, expected_version=BaseObjectStorage.contract_version
        ),
    )


def _multipart() -> BaseMultipartUpload:
    """解析分片上传实现（worker 进程按需装配插件）。

    Returns:
        BaseMultipartUpload: 分片上传实例。
    """
    settings = get_settings()
    ensure_job_plugins(settings)
    return cast(
        "BaseMultipartUpload",
        resolve_plugin(
            "multipart_upload",
            settings.multipart_upload.provider,
            expected_version=BaseMultipartUpload.contract_version,
        ),
    )
