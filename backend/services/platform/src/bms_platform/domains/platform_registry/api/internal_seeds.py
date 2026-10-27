"""种子编排内部端点（07B `02_03`）：`/api/v1/platform/internal/seeds`（服务间调用，不经网关）。

- **用途**：部署初始化时由 CLI（`ops.seed_platform`）触发，在 platform 服务进程内统一执行
  全部种子（平台 + 产品同构声明），一个 XA 全局事务内串行 prepare、统一提交或整体回滚；
- **鉴权**：双模 `require_auth_or_service`——服务身份或登录态（与既有内部端点同口径）；
- **不是目录出口**：本端点面向「编排执行」，与目录 / 管理面判据不同（架构 38 §9）。
"""

from typing import Annotated, cast

from fastapi import Depends, Request

from bms_core.api.base import AuthContext, BaseRouter, require_auth_or_service
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.keys import PLATFORM_SERVICE_KEY
from bms_core.db.registry import EngineRegistry
from bms_core.schemas.common import ApiResponse
from bms_core.transaction.base import get_transaction_manager, get_transaction_participant
from bms_platform.domains.platform_registry.schemas.seed_orchestration import (
    SeedOrchestrationRequestSchema,
    SeedOrchestrationResultSchema,
)
from bms_platform.domains.platform_registry.services.seed_orchestration import (
    SeedOrchestrationRequest,
    SeedOrchestrationService,
)
from bms_platform.services.seed_branch_handlers import register_seed_stats

router = BaseRouter(
    key="platform_internal_seeds",
    prefix="/platform/internal/seeds",
    tags=["platform-internal"],
    dependencies=[Depends(require_auth_or_service)],
)

ContextDep = Annotated[AuthContext, Depends(require_auth_or_service)]


@router.post("/orchestrate")
async def orchestrate_seeds(
    payload: SeedOrchestrationRequestSchema,
    context: ContextDep,
    request: Request,
) -> ApiResponse:
    """统一执行全部种子（一个 XA 全局事务；串行 prepare、统一提交 / 整体回滚）。

    **依赖注入**（2026-10-27 修复）：事务管理器 / 参与方 / 引擎注册表在此（有请求上下文）
    从应用 state 解析后注入服务——服务层拿不到 `Request`，故不在编排器内零参调用基座取用器。

    Args:
        payload: 编排请求（租户 / 筛选 / dry-run / 超时）。
        context: 入站身份（服务身份或登录态）。
        request: 请求对象（取应用 state 中的事务与引擎依赖）。

    Returns:
        ApiResponse: 编排结果（退出码 + 逐项报告 + 错误 / 冲突明细）。

    Raises:
        ParamError: 参数非法（筛选引用了不存在的种子）。
    """
    del context
    participant = get_transaction_participant(request)
    # 统计探针（详设 §3.10）：分支内前后快照采集，须在参与方实例上登记后才会生效。
    register_seed_stats(participant)
    service = SeedOrchestrationService(
        caller_service=PLATFORM_SERVICE_KEY,
        manager=get_transaction_manager(request),
        participant=participant,
        engines=cast("EngineRegistry", request.app.state.engine_registry),
    )
    result = await service.orchestrate(
        SeedOrchestrationRequest(
            tenant=payload.tenant,
            only=ConcurrentStableList(payload.only),
            skip=ConcurrentStableList(payload.skip),
            require=ConcurrentStableList(payload.require),
            dry_run=payload.dry_run,
            timeout_seconds=payload.timeout_seconds,
        )
    )
    reports: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    for report in result.reports:
        row: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        row.set("name", report.name)
        row.set("source", report.source)
        row.set("status", report.status)
        row.set("created", report.created)
        row.set("updated", report.updated)
        row.set("skipped", report.skipped)
        row.set("conflicts", report.conflicts)
        row.set("note", report.note)
        reports.add(row)
    return ApiResponse(
        data=SeedOrchestrationResultSchema(
            exitCode=result.exit_code,
            reports=reports,
            errors=ConcurrentStableList(result.errors),
            conflicts=ConcurrentStableList(result.conflicts),
            warnings=ConcurrentStableList(result.warnings),
        )
    )
