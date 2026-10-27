"""种子编排服务（07B `02_03`）：在 platform 服务进程内统一执行全部种子。

**为什么在服务内**：XA 分支执行需要「引擎注册表 + 分支处理器注册表 + 事务参与方」三件套，
这些由应用装配提供；CLI 进程没有这些上下文。故编排入口落本服务，CLI 只做触发与报告渲染。

**核心口径**：一套装载（平台 + 产品同构声明）+ 一个 XA 全局事务（串行 prepare、统一提交 / 整体回滚）。
"""

from dataclasses import dataclass
from dataclasses import field as dataclass_field

from bms_core.core.concurrent import (
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.config import get_settings
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseDataContract
from bms_core.registry.products import load_product_manifests
from bms_core.services.module_registry import seed_catalog_view
from bms_core.tenant.seed.orchestrator import (
    DEFAULT_TIMEOUT_SECONDS,
    SeedReport,
    build_plan,
    ensure_structure,
    execute_plan,
    precheck_seeds,
    select_seeds,
)

__all__ = ["SeedOrchestrationRequest", "SeedOrchestrationResult", "SeedOrchestrationService"]


@dataclass
class SeedOrchestrationRequest(BaseDataContract):
    """编排请求（内部端点入参）。"""

    tenant: str = ""
    """目标租户（展开 `db_key` 占位）；空串取 `[platform_tenant].code`。"""

    only: ConcurrentStableFrozenList[str] = dataclass_field(default_factory=lambda: ConcurrentStableFrozenList())
    """只执行这些种子（空表示不限制）。"""

    skip: ConcurrentStableFrozenList[str] = dataclass_field(default_factory=lambda: ConcurrentStableFrozenList())
    """跳过这些种子。"""

    require: ConcurrentStableFrozenList[str] = dataclass_field(default_factory=lambda: ConcurrentStableFrozenList())
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


class SeedOrchestrationService:
    """种子统一编排服务（平台进程内）。"""

    def __init__(self, *, caller_service: str) -> None:
        """初始化。

        Args:
            caller_service: 发起方服务键（写进 XA 全局事务，供 TM 审计）。
        """
        self._caller = caller_service
        self._logger = get_logger("bms")

    def _load_records(self) -> ConcurrentStableList:
        """装载全部种子声明（本仓 `deploy/registry/*.toml` + 配置注入的产品清单）。

        Returns:
            ConcurrentStableList: 种子记录合并视图。
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
        selected = select_seeds(
            records,
            only=ConcurrentStableList(request.only),
            skip=ConcurrentStableList(request.skip),
            require=ConcurrentStableList(request.require),
        )
        precheck = precheck_seeds(selected)
        if precheck.errors:
            self._logger.error("seed_precheck_failed", count=len(precheck.errors))
            return SeedOrchestrationResult(
                exit_code=3,
                errors=ConcurrentStableFrozenList(precheck.errors),
                warnings=ConcurrentStableFrozenList(precheck.warnings),
            )
        plan = build_plan(selected, tenant=tenant)
        if request.dry_run:
            self._logger.info("seed_dry_run", count=len(plan), tenant=tenant)
            return SeedOrchestrationResult(
                exit_code=0,
                reports=ConcurrentStableFrozenList(
                    SeedReport(name=item.record.name, source=item.record.name.split("-", 1)[0], status="planned")
                    for item in plan
                ),
                warnings=ConcurrentStableFrozenList(precheck.warnings),
            )
        # 结构前置阶段（07B `02_03`）：种子依赖表结构就绪，先幂等建表再播种。
        # 失败即中止，不进事务（退出码 3：编排前置错误）。
        structure_errors = await ensure_structure(plan, tenant=tenant)
        if structure_errors:
            self._logger.error("seed_structure_failed", count=len(structure_errors))
            return SeedOrchestrationResult(
                exit_code=3,
                errors=ConcurrentStableFrozenList(structure_errors),
                warnings=ConcurrentStableFrozenList(precheck.warnings),
            )
        reports = await execute_plan(
            plan,
            tenant=tenant,
            caller_service=self._caller,
            timeout_seconds=request.timeout_seconds,
        )
        exit_code = 0 if all(report.status in ("ok", "skipped") for report in reports) else 2
        return SeedOrchestrationResult(
            exit_code=exit_code,
            reports=reports,
            warnings=ConcurrentStableFrozenList(precheck.warnings),
        )
