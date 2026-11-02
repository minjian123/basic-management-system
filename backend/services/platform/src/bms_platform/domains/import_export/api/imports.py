"""导入接口：模板 / 执行 / 异步状态 / 错误明细（`/api/v1/imports`）。"""

from collections.abc import Callable
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, File, Header, Path, Response, UploadFile

from bms_core.api.base import BaseRouter, require_auth
from bms_core.api.deps import (
    get_audit_capturer,
    get_cache_region,
    get_config_source,
    get_idempotency_store,
    get_importer,
    get_object_storage,
    get_outbox_store,
    get_password_hasher,
    get_password_policy,
    get_permission_checker,
    get_rate_limiter,
    get_service_client,
    get_uow,
)
from bms_core.audit.base import AuditCapturer
from bms_core.cache.base import CacheRegion
from bms_core.config.base import BaseConfigSource
from bms_core.core.context import current_tenant, current_user_id
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.tenant import current_tenant_context, current_tenant_id_str
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.idempotency.base import IDEMPOTENCY_HEADER, IdempotencyStore
from bms_core.jobs.runner import JobRunner
from bms_core.outbox.base import BaseOutboxStore
from bms_core.password.base import BasePasswordPolicy
from bms_core.permission.base import BasePermissionChecker, require_permission
from bms_core.ratelimit.base import BaseRateLimiter, RateLimitRule, build_rate_limit_key
from bms_core.schemas.common import ApiResponse
from bms_core.security.base import BasePasswordHasher
from bms_core.servicecall.base import BaseServiceClient
from bms_core.storage.base import BaseObjectStorage
from bms_core.tenant_module.quota import TenantQuotaClient
from bms_core.transfer.definition import ImportDefinitionRegistry
from bms_core.transfer.importer import BaseImporter
from bms_core.transfer.limits import ImportLimits
from bms_core.transfer.openpyxl_io import XLSX_CONTENT_TYPE
from bms_core.transfer.source import ObjectStorageImportSourceStore
from bms_platform.domains.import_export.schemas.imports import ImportExecuteResult, ImportJobStatus
from bms_platform.domains.import_export.services.imports import ImportExecutor, ImportService

__all__ = ["build_import_router"]

UowDep = Annotated[UnitOfWork, Depends(get_uow)]
ImporterDep = Annotated[BaseImporter, Depends(get_importer)]
StorageDep = Annotated[BaseObjectStorage, Depends(get_object_storage)]
IdempotencyDep = Annotated[IdempotencyStore, Depends(get_idempotency_store)]
ConfigDep = Annotated[BaseConfigSource, Depends(get_config_source)]
CacheDep = Annotated[CacheRegion, Depends(get_cache_region)]
PermissionDep = Annotated[BasePermissionChecker, Depends(get_permission_checker)]
AuditDep = Annotated[AuditCapturer, Depends(get_audit_capturer)]
OutboxDep = Annotated[BaseOutboxStore, Depends(get_outbox_store)]
HasherDep = Annotated[BasePasswordHasher, Depends(get_password_hasher)]
PolicyDep = Annotated[BasePasswordPolicy, Depends(get_password_policy)]
ClientDep = Annotated[BaseServiceClient, Depends(get_service_client)]
LimiterDep = Annotated[BaseRateLimiter, Depends(get_rate_limiter)]
IdempotencyKeyHeader = Annotated[str | None, Header(alias=IDEMPOTENCY_HEADER)]
UploadBody = Annotated[UploadFile, File(description="Excel 文件（表单字段 file）")]
JobIdPath = Annotated[int, Path(gt=0, description="导入作业主键")]
TokenPath = Annotated[str, Path(min_length=1, description="错误明细 token")]

_REQUIRE_IMPORT = Depends(require_permission("import:execute"))


class _ImportDeps(BaseFrameworkObject):
    """一次请求的导入依赖集合（避免函数参数过多）。"""

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        importer: BaseImporter,
        storage: BaseObjectStorage,
        idempotency: IdempotencyStore,
        config: BaseConfigSource,
        cache: CacheRegion,
        permission: BasePermissionChecker,
        audit: AuditCapturer,
        outbox: BaseOutboxStore,
        hasher: BasePasswordHasher,
        policy: BasePasswordPolicy,
        client: BaseServiceClient,
        limiter: BaseRateLimiter,
        definitions_factory: Callable[..., ImportDefinitionRegistry],
        runner_factory: Callable[[], JobRunner],
    ) -> None:
        self.uow = uow
        self.importer = importer
        self.storage = storage
        self.idempotency = idempotency
        self.config = config
        self.cache = cache
        self.permission = permission
        self.audit = audit
        self.outbox = outbox
        self.hasher = hasher
        self.policy = policy
        self.client = client
        self.limiter = limiter
        self.definitions_factory = definitions_factory
        self.runner_factory = runner_factory


async def _service(deps: _ImportDeps) -> ImportService:
    """构造导入服务（按请求参数 / 插件装配）。"""
    limits = await ImportLimits.load(deps.config)
    definitions = deps.definitions_factory(
        hasher=deps.hasher,
        policy=deps.policy,
        outbox=deps.outbox,
        service_client=deps.client,
        audit=deps.audit,
        config=deps.config,
    )
    quota = TenantQuotaClient(
        deps.client,
        tenant_id=current_tenant_id_str(),
        tenant_code=current_tenant.get(),
    )
    executor = ImportExecutor(
        definitions=definitions,
        importer=deps.importer,
        limits=limits,
        config=deps.config,
        audit=deps.audit,
        quota=quota,
    )
    return ImportService(
        executor=executor,
        source_store=ObjectStorageImportSourceStore(deps.storage),
        idempotency=deps.idempotency,
        runner_factory=deps.runner_factory,
        cache=deps.cache,
        limits=limits,
        checker=deps.permission,
    )


async def _rate_limit(deps: _ImportDeps) -> None:
    """用户维度限流（默认 10 次/分钟）。"""
    user_id = current_user_id.get()
    if user_id is None:
        return
    limits = await ImportLimits.load(deps.config)
    key = build_rate_limit_key(dimension="user", target=str(user_id), tenant=current_tenant.get())
    await deps.limiter.require(key, RateLimitRule(limit=limits.rate_limit, window=limits.rate_limit_window))


def _disposition(filename: str) -> str:
    """RFC 5987 下载文件名。"""
    return f"attachment; filename*=UTF-8''{quote(filename)}"


def build_import_router(
    *,
    definitions_factory: Callable[..., ImportDefinitionRegistry],
    runner_factory: Callable[[], JobRunner],
) -> BaseRouter:
    """构造导入业务路由。

    Args:
        definitions_factory: 导入定义装配函数（服务根注入）。
        runner_factory: 作业提交器工厂（服务根注入）。

    Returns:
        BaseRouter: `/imports` 路由。
    """
    router = BaseRouter(
        key="import_export",
        prefix="/imports",
        tags=["import"],
        dependencies=[Depends(require_auth)],
    )

    def deps_of(
        uow: UowDep,
        importer: ImporterDep,
        storage: StorageDep,
        idempotency: IdempotencyDep,
        config: ConfigDep,
        cache: CacheDep,
        permission: PermissionDep,
        audit: AuditDep,
        outbox: OutboxDep,
        hasher: HasherDep,
        policy: PolicyDep,
        client: ClientDep,
        limiter: LimiterDep,
    ) -> _ImportDeps:
        """收集请求依赖。"""
        return _ImportDeps(
            uow=uow,
            importer=importer,
            storage=storage,
            idempotency=idempotency,
            config=config,
            cache=cache,
            permission=permission,
            audit=audit,
            outbox=outbox,
            hasher=hasher,
            policy=policy,
            client=client,
            limiter=limiter,
            definitions_factory=definitions_factory,
            runner_factory=runner_factory,
        )

    @router.get("/{biz}/template", dependencies=[_REQUIRE_IMPORT])
    async def download_template(biz: str, deps: Annotated[_ImportDeps, Depends(deps_of)]) -> Response:
        """下载导入模板（xlsx 文件流）。

        Args:
            biz: 业务标识（users / roles）。
            deps: 请求依赖。

        Returns:
            Response: xlsx 文件流。
        """
        await _rate_limit(deps)
        content, filename = (await _service(deps)).template(biz)
        return Response(
            content=content,
            media_type=XLSX_CONTENT_TYPE,
            headers={"Content-Disposition": _disposition(filename)},
        )

    @router.post("/{biz}/execute", dependencies=[_REQUIRE_IMPORT])
    async def execute_import(
        biz: str,
        deps: Annotated[_ImportDeps, Depends(deps_of)],
        file: UploadBody,
        idem_key: IdempotencyKeyHeader = None,
    ) -> ApiResponse[ImportExecuteResult]:
        """执行导入（multipart xlsx + Idempotency-Key）。

        Args:
            biz: 业务标识。
            deps: 请求依赖。
            file: 上传文件。
            idem_key: 幂等键请求头。

        Returns:
            ApiResponse: 执行结果（同步汇总 / 异步 job_id / 幂等命中）。
        """
        await _rate_limit(deps)
        content = await file.read()
        tenant = current_tenant_context()
        result = await (await _service(deps)).execute(
            biz=biz,
            data=content,
            file_name=file.filename or "import.xlsx",
            idem_key=idem_key,
            uow=deps.uow,
            tenant_id=tenant.tenant_id,
            tenant_code=tenant.code,
            actor=current_user_id.get(),
            db_key=tenant.db_key,
        )
        return ApiResponse.ok(result)

    @router.get("/{biz}/jobs/{job_id}", dependencies=[_REQUIRE_IMPORT])
    async def get_import_job(
        biz: str,
        job_id: JobIdPath,
        deps: Annotated[_ImportDeps, Depends(deps_of)],
    ) -> ApiResponse[ImportJobStatus]:
        """异步导入状态 / 进度 / 汇总 / 前 N 条错误。

        Args:
            biz: 业务标识。
            job_id: 作业主键。
            deps: 请求依赖。

        Returns:
            ApiResponse: 状态。
        """
        await _rate_limit(deps)
        status = await (await _service(deps)).status(biz=biz, job_id=job_id, uow=deps.uow)
        return ApiResponse.ok(status)

    @router.get("/{biz}/error-report/{token}", dependencies=[_REQUIRE_IMPORT])
    async def download_error_report(
        biz: str,
        token: TokenPath,
        deps: Annotated[_ImportDeps, Depends(deps_of)],
    ) -> Response:
        """下载错误明细 xlsx（按首次结果生成，限时有效）。

        Args:
            biz: 业务标识。
            token: 错误明细 token。
            deps: 请求依赖。

        Returns:
            Response: xlsx 文件流。
        """
        await _rate_limit(deps)
        tenant = current_tenant_context()
        content, filename = await (await _service(deps)).error_report(
            biz=biz, token=token, uow=deps.uow, tenant_code=tenant.code
        )
        return Response(
            content=content,
            media_type=XLSX_CONTENT_TYPE,
            headers={"Content-Disposition": _disposition(filename)},
        )

    return router
