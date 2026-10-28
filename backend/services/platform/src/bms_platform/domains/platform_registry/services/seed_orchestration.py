"""种子编排服务（07B `02_03`）：在 platform 服务进程内统一执行全部种子。

**为什么在服务内**：XA 分支执行需要「引擎注册表 + 分支处理器注册表 + 事务参与方」三件套，
这些由应用装配提供；CLI 进程没有这些上下文。故编排入口落本服务，CLI 只做触发与报告渲染。

**核心口径**：一套装载（平台 + 产品同构声明）+ 一个 XA 全局事务（串行 prepare、统一提交 / 整体回滚）。
"""

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any, Protocol, cast

from bms_core.core.concurrent import (
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.config import get_settings
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseDataContract, BaseFrameworkObject
from bms_core.registry.products import load_product_manifests
from bms_core.services.module_registry import SeedRecord, seed_catalog_view
from bms_core.tenant.seed.orchestrator import (
    DEFAULT_TIMEOUT_SECONDS,
    EXIT_CONFLICT,
    EXIT_EXECUTE,
    EXIT_OK,
    EXIT_PRECHECK,
    SeedBranchRunner,
    SeedReport,
    SeedTransactionManager,
    build_plan,
    ensure_structure,
    execute_plan,
    precheck_conflicts,
    precheck_seeds,
    select_seeds,
)
from bms_platform.services.seed_branch_handlers import register_seed_stats

__all__ = ["SeedOrchestrationRequest", "SeedOrchestrationResult", "SeedOrchestrationService", "SyncEngineProvider"]


class SyncEngineProvider(Protocol):
    """同步引擎提供者（冲突预检只读查库用；生产为 `EngineRegistry`）。"""

    async def get_sync(self, db_key: str, *, read_only: bool = False) -> Any:
        """取同步引擎。

        Args:
            db_key: 数据源键。
            read_only: 是否只读。

        Returns:
            Any: 同步引擎。
        """
        ...


@dataclass
class SeedOrchestrationRequest(BaseDataContract):
    """编排请求（内部端点入参）。"""

    tenant: str = ""
    """目标租户（展开 `db_key` 占位）；空串取 `[platform_tenant].code`。"""

    only: ConcurrentStableList[str] = dataclass_field(default_factory=lambda: ConcurrentStableList())
    """只执行这些种子（空表示不限制）。"""

    skip: ConcurrentStableList[str] = dataclass_field(default_factory=lambda: ConcurrentStableList())
    """跳过这些种子。"""

    require: ConcurrentStableList[str] = dataclass_field(default_factory=lambda: ConcurrentStableList())
    """人工强制前置（这些种子必须在本批之前完成）。"""

    dry_run: bool = False
    """只做装载 + 排序 + 冲突预检，不开事务不执行。"""

    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    """全局事务超时。"""


@dataclass
class SeedOrchestrationResult(BaseDataContract):
    """编排结果（内部端点出参）。"""

    exit_code: int = 0
    """退出码（0 / 1 / 2 / 3 / 64）。"""

    reports: ConcurrentStableFrozenList[SeedReport] = dataclass_field(
        default_factory=lambda: ConcurrentStableFrozenList()
    )
    """逐项报告。"""

    errors: ConcurrentStableFrozenList[str] = dataclass_field(default_factory=lambda: ConcurrentStableFrozenList())
    """前置错误（退出码 3 时）。"""

    conflicts: ConcurrentStableFrozenList[str] = dataclass_field(default_factory=lambda: ConcurrentStableFrozenList())
    """数据冲突明细（退出码 1 时）。"""

    warnings: ConcurrentStableFrozenList[str] = dataclass_field(default_factory=lambda: ConcurrentStableFrozenList())
    """警示。"""


class SeedOrchestrationService(BaseFrameworkObject):
    """种子统一编排服务（平台进程内）。

    继承 `BaseFrameworkObject`（与本域其他服务一致）：本服务不绑定单一仓储（跨多个库与
    种子实现），只承载编排流程，故不用 `BaseService`（那个包装仓储 CRUD）。
    """

    def __init__(
        self,
        *,
        caller_service: str,
        manager: object | None = None,
        participant: object | None = None,
        engines: object | None = None,
    ) -> None:
        """初始化。

        **依赖注入**（2026-10-27 修复）：事务管理器 / 参与方 / 引擎注册表由调用方（端点层，
        有请求上下文）注入——基座取用器需 FastAPI `Request`，服务层拿不到，故不能在此零参调用。

        Args:
            caller_service: 发起方服务键（写进 XA 全局事务，供 TM 审计）。
            manager: 事务管理器（缺省由端点注入）。
            participant: 事务参与方（缺省由端点注入）。
            engines: 引擎注册表（冲突预检只读查库用；缺省由端点注入）。
        """
        self._caller = caller_service
        self._manager: SeedTransactionManager | None = cast("SeedTransactionManager | None", manager)
        self._participant: SeedBranchRunner | None = cast("SeedBranchRunner | None", participant)
        self._engines: SyncEngineProvider | None = cast("SyncEngineProvider | None", engines)
        self._logger = get_logger("bms")

    def _load_records(self) -> ConcurrentStableList[SeedRecord]:
        """装载全部种子声明（本仓 `deploy/registry/*.toml` + 配置注入的产品清单）。

        Returns:
            ConcurrentStableList[SeedRecord]: 种子记录合并视图。
        """
        load_product_manifests(get_settings().registry.product_manifests)
        return ConcurrentStableList(seed_catalog_view())

    async def orchestrate(self, request: SeedOrchestrationRequest) -> SeedOrchestrationResult:
        """执行编排：预检 → 排序 → 一个 XA 全局事务内串行执行 → 统一提交 / 整体回滚。

        Args:
            request: 编排请求。

        Returns:
            SeedOrchestrationResult: 编排结果（含逐项报告与退出码）。

        Raises:
            ParamError: 参数非法（`--only` / `--skip` / `--require` 引用不存在的种子）。
        """
        tenant = request.tenant or get_settings().platform_tenant.code
        records = self._load_records()
        require = ConcurrentStableList(request.require)
        selected = select_seeds(
            records,
            only=ConcurrentStableList(request.only),
            skip=ConcurrentStableList(request.skip),
            require=require,
        )
        precheck = precheck_seeds(selected)
        if precheck.errors:
            self._logger.error("seed_precheck_failed", count=len(precheck.errors))
            return SeedOrchestrationResult(
                exit_code=EXIT_PRECHECK,
                errors=ConcurrentStableFrozenList(precheck.errors),
                warnings=ConcurrentStableFrozenList(precheck.warnings),
            )
        # 统计探针（07B `03_03`）：取种子声明的目标表，须在记录装载后、执行前登记。
        warnings = ConcurrentStableList(precheck.warnings)
        if self._participant is not None:
            warnings.update(register_seed_stats(self._participant, selected))
        plan = build_plan(selected, tenant=tenant, require=require)
        if request.dry_run:
            self._logger.info("seed_dry_run", count=len(plan), tenant=tenant)
            return SeedOrchestrationResult(
                exit_code=EXIT_OK,
                reports=ConcurrentStableFrozenList(
                    SeedReport(name=item.record.name, source=item.record.source, status="planned") for item in plan
                ),
                warnings=ConcurrentStableFrozenList(warnings),
            )
        # 结构前置阶段（07B `02_03`）：种子依赖表结构就绪，先幂等建表再播种。
        # 失败即中止，不进事务（退出码 3：编排前置错误）。
        structure_errors = await ensure_structure(plan, tenant=tenant)
        if structure_errors:
            self._logger.error("seed_structure_failed", count=len(structure_errors))
            return SeedOrchestrationResult(
                exit_code=EXIT_PRECHECK,
                errors=ConcurrentStableFrozenList(structure_errors),
                warnings=ConcurrentStableFrozenList(warnings),
            )
        # 数据冲突预检（详设 §3.5）：结构就绪之后、事务之前只读比对，一次看全全部冲突。
        if self._engines is not None:
            conflicts = await precheck_conflicts(plan, engines=self._engines)
            if conflicts:
                self._logger.error("seed_conflicts_found", count=len(conflicts))
                return SeedOrchestrationResult(
                    exit_code=EXIT_CONFLICT,
                    conflicts=ConcurrentStableFrozenList(conflicts),
                    warnings=ConcurrentStableFrozenList(warnings),
                )
        reports = await execute_plan(
            plan,
            tenant=tenant,
            caller_service=self._caller,
            timeout_seconds=request.timeout_seconds,
            branch_runner=self._participant,
            manager=self._manager,
        )
        exit_code = EXIT_OK if all(report.status in ("ok", "skipped") for report in reports) else EXIT_EXECUTE
        return SeedOrchestrationResult(
            exit_code=exit_code,
            reports=reports,
            warnings=ConcurrentStableFrozenList(warnings),
        )
