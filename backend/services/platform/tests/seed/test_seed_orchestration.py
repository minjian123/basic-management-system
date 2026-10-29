"""种子编排服务与内部端点用例（07B `02_03`；详设 §5 用例 13~17 / 24 / 28~29 的服务侧）。

**Kiwi 编号**：本批新增用例暂不标 `kiwi_id`，统一归 `05_01` 回填。

**覆盖面**：编排服务的装载 → 筛选 → 预检 → 计划 → dry-run → 结构前置 → 冲突预检 → 执行 → 退出码；
端点契约（入参 / 出参字段）；分支处理器注册（9 个 op）与统计探针登记。
"""

from typing import Any

import pytest

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import ParamError
from bms_core.services.module_registry import SeedRecord
from bms_core.transaction.base import BranchHandlerRegistry
from bms_platform.domains.platform_registry.schemas.seed_orchestration import (
    SeedOrchestrationRequestSchema,
    SeedOrchestrationResultSchema,
)
from bms_platform.domains.platform_registry.services.seed_orchestration import (
    EXIT_OK,
    EXIT_PRECHECK,
    SeedOrchestrationRequest,
    SeedOrchestrationResult,
    SeedOrchestrationService,
)
from bms_platform.services import seed_branch_handlers
from bms_platform.services.seed_branch_handlers import SEED_OPS, register_seed_handlers, register_seed_stats


class _StubManager:
    """事务管理器替身：记录 begin / commit / rollback。"""

    def __init__(self) -> None:
        """初始化。"""
        self.events: ConcurrentStableList[str] = ConcurrentStableList()

    async def begin(self, **kwargs: Any) -> Any:
        """记录 begin 并回传分支快照。

        Args:
            **kwargs: 含 `branches`。

        Returns:
            Any: 全局事务快照。
        """
        from bms_core.transaction.base import BranchRef, GlobalTransaction

        self.events.add("begin")
        branches = kwargs["branches"]
        return GlobalTransaction(
            global_txn_id="t-1",
            caller_service="platform",
            state="active",
            branches=ConcurrentStableFrozenList(
                BranchRef(
                    branch_id=spec.branch_id,
                    service=spec.service,
                    db_key=spec.db_key,
                    xid=f"t-1|{spec.branch_id}",
                    state="active",
                )
                for spec in branches
            ),
        )

    async def commit(self, global_txn_id: str) -> Any:
        """记录 commit。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            Any: 快照。
        """
        from bms_core.transaction.base import GlobalTransaction

        self.events.add("commit")
        return GlobalTransaction(global_txn_id=global_txn_id, caller_service="platform", state="committed")

    async def rollback(self, global_txn_id: str) -> Any:
        """记录 rollback。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            Any: 快照。
        """
        from bms_core.transaction.base import GlobalTransaction

        self.events.add("rollback")
        return GlobalTransaction(global_txn_id=global_txn_id, caller_service="platform", state="rolled_back")


class _StubRunner:
    """分支执行器替身：全部 prepared。"""

    def __init__(self, *, state: str = "prepared") -> None:
        """初始化。

        Args:
            state: 分支返回状态。
        """
        self.calls: ConcurrentStableList[str] = ConcurrentStableList()
        self._state = state

    async def execute_branch_with_stats(self, *, xid: str, db_key: str, ops: Any) -> tuple[str, Any]:
        """执行分支替身。

        Args:
            xid: 分支事务标识。
            db_key: 目标库键。
            ops: 分支操作清单。

        Returns:
            tuple[str, Any]: （分支状态, 统计）。
        """
        from bms_core.transaction.base import BranchStats

        del xid, db_key
        self.calls.add(ops[0].op)
        return self._state, BranchStats()


def _service(*, manager: Any = None, runner: Any = None, engines: Any = None) -> SeedOrchestrationService:
    """构造编排服务（注入替身）。

    Args:
        manager: 事务管理器。
        runner: 分支执行器。
        engines: 引擎注册表（None 表示跳过冲突预检）。

    Returns:
        SeedOrchestrationService: 服务实例。
    """
    return SeedOrchestrationService(
        caller_service="platform",
        manager=manager if manager is not None else _StubManager(),
        participant=runner if runner is not None else _StubRunner(),
        engines=engines,
    )


# ---- 装载与 dry-run（用例 1~3 / 19 服务侧）----


async def test_orchestrate_dry_run_returns_planned_reports() -> None:
    """用例 19：`dry_run` 只做装载 + 排序 + 预检，返回 `planned` 报告且**不开启事务**。"""
    manager = _StubManager()
    result = await _service(manager=manager).orchestrate(SeedOrchestrationRequest(dry_run=True))
    assert result.exit_code == 0
    assert result.reports
    assert all(report.status == "planned" for report in result.reports)
    assert list(manager.events) == []


async def test_orchestrate_dry_run_reports_use_injected_source() -> None:
    """用例 24：dry-run 报告的「来源」取装载期注入的 `source`（不是名字首段）。"""
    result = await _service().orchestrate(SeedOrchestrationRequest(dry_run=True))
    assert {report.source for report in result.reports} == {"platform"}


async def test_orchestrate_precheck_error_returns_exit_3() -> None:
    """用例 4/8/9 服务侧：前置错误 → 退出码 3，不进事务。"""
    manager = _StubManager()
    # 用 --only 引用不存在的种子触发 ParamError（参数错误，由端点转 HTTP 400）
    with pytest.raises(ParamError):
        await _service(manager=manager).orchestrate(
            SeedOrchestrationRequest(only=ConcurrentStableFrozenList(["ghost"]), dry_run=True)
        )
    assert list(manager.events) == []


async def test_orchestrate_seed_declaration_errors_return_exit_3() -> None:
    """用例 4/8/9 服务侧：种子声明不自洽（缺执行服务 / 目标库）→ 退出码 3，不进事务。

    与上一条的分工：那条测的是 `select_seeds` 的参数错误（`ParamError`），这条测
    `precheck_seeds` 汇总出的**声明类**前置错误（服务侧编排的首个拒绝分支）。
    """
    from bms_core.services.module_registry import SeedRecord, register_seed_records, reset_seed_records

    register_seed_records(
        (SeedRecord(name="seed-broken", module="bms_platform.seeds.broken", entry="seed_broken"),),
    )
    manager = _StubManager()
    try:
        result = await _service(manager=manager).orchestrate(
            SeedOrchestrationRequest(only=ConcurrentStableFrozenList(["seed-broken"]), dry_run=True)
        )
    finally:
        reset_seed_records()
    assert result.exit_code == EXIT_PRECHECK
    assert any("service" in item for item in result.errors)
    assert any("db_key" in item for item in result.errors)
    assert list(manager.events) == []


# ---- 用例 14：全部成功 ----


async def test_orchestrate_all_success_returns_exit_0() -> None:
    """用例 14 服务侧：全部 prepared → 退出码 0，报告逐项、状态 ok。"""
    manager = _StubManager()
    result = await _service(manager=manager).orchestrate(
        SeedOrchestrationRequest(only=ConcurrentStableFrozenList(["seed-module"]))
    )
    assert result.exit_code == 0
    assert [report.status for report in result.reports] == ["ok"]
    assert list(manager.events) == ["begin", "commit"]


# ---- 用例 15 / 12：探针在记录装载后按声明登记 ----


class _StatsRunner(_StubRunner):
    """分支执行器替身（同时具备探针登记能力）。"""

    def __init__(self) -> None:
        """初始化登记表。"""
        super().__init__()
        self.registered: ConcurrentStableDict[str, Any] = ConcurrentStableDict()

    def register_stats_probe(self, op: str, probe: Any) -> None:
        """记录探针。

        Args:
            op: 操作名。
            probe: 探针。
        """
        self.registered.set(op, probe)


async def test_orchestrate_registers_probes_after_loading_product_records() -> None:
    """用例 15：探针在 `_load_records()` 之后登记——产品种子同样能被登记。"""
    from bms_core.services.module_registry import SeedRecord, register_seed_records, reset_seed_records

    register_seed_records(
        (
            SeedRecord(
                name="demo-admin-codes",
                module="bms_platform.seeds.demo",
                entry="seed_demo",
                service="platform",
                db_key="platform_platform",
                tables=ConcurrentStableFrozenDict({"sys_business": "code"}),
            ),
        ),
    )
    runner = _StatsRunner()
    try:
        result = await _service(runner=runner).orchestrate(
            SeedOrchestrationRequest(only=ConcurrentStableFrozenList(["seed-module", "demo-admin-codes"]), dry_run=True)
        )
    finally:
        reset_seed_records()
    assert set(runner.registered) == {"seed-module", "demo-admin-codes"}, list(result.errors)
    assert list(result.warnings) == []


async def test_orchestrate_unknown_probe_table_warns_in_report() -> None:
    """用例 14：声明了未知表名时记警示到编排报告，不阻断编排。"""
    from bms_core.services.module_registry import SeedRecord, register_seed_records, reset_seed_records

    register_seed_records(
        (
            SeedRecord(
                name="seed-ghost-table",
                module="bms_platform.seeds.demo",
                entry="seed_demo",
                service="platform",
                db_key="platform_platform",
                tables=ConcurrentStableFrozenDict({"no_such_table": "id"}),
            ),
        ),
    )
    runner = _StatsRunner()
    try:
        result = await _service(runner=runner).orchestrate(
            SeedOrchestrationRequest(only=ConcurrentStableFrozenList(["seed-ghost-table"]), dry_run=True)
        )
    finally:
        reset_seed_records()
    assert dict(runner.registered) == {}
    assert any("no_such_table" in item for item in result.warnings)


# ---- 用例 15：失败整体回滚 ----


async def test_orchestrate_branch_rejected_returns_exit_2() -> None:
    """用例 15 服务侧：分支 rejected → 退出码 2，已整体回滚。"""
    manager = _StubManager()
    result = await _service(manager=manager, runner=_StubRunner(state="rejected")).orchestrate(
        SeedOrchestrationRequest(only=ConcurrentStableFrozenList(["seed-module"]))
    )
    assert result.exit_code == 2
    assert list(manager.events) == ["begin", "rollback"]
    assert result.reports[0].status == "rolled_back"


# ---- 用例 5/26：冲突预检 ----


async def test_orchestrate_conflicts_return_exit_1() -> None:
    """用例 5 服务侧：预检发现数据冲突 → 退出码 1，列出冲突明细，**不进事务**。"""
    from bms_core.tenant.seed import orchestrator

    async def _fake_conflicts(_plan: Any, *, engines: Any) -> ConcurrentStableList[str]:
        """替身：恒定返回一条冲突。

        Args:
            _plan: 计划（忽略）。
            engines: 引擎（忽略）。

        Returns:
            ConcurrentStableList[str]: 冲突明细。
        """
        del engines
        return ConcurrentStableList(["种子 seed-menu：sys_business（code='mdm'）与声明不一致 → name"])

    original = orchestrator.precheck_conflicts
    import bms_platform.domains.platform_registry.services.seed_orchestration as module

    module.precheck_conflicts = _fake_conflicts  # type: ignore[attr-defined]
    manager = _StubManager()
    try:
        result = await _service(manager=manager, engines=object()).orchestrate(
            SeedOrchestrationRequest(only=ConcurrentStableFrozenList(["seed-module"]))
        )
    finally:
        module.precheck_conflicts = original  # type: ignore[attr-defined]
    assert result.exit_code == 1
    assert len(result.conflicts) == 1
    assert list(manager.events) == []


async def test_orchestrate_engines_without_conflicts_executes() -> None:
    """用例 5 服务侧：注入引擎且**无冲突** → 冲突分支不停，继续进事务执行（退出码 0）。"""
    from bms_core.tenant.seed import orchestrator

    async def _no_conflicts(_plan: Any, *, engines: Any) -> ConcurrentStableList[str]:
        """替身：无冲突。

        Args:
            _plan: 计划（忽略）。
            engines: 引擎（忽略）。

        Returns:
            ConcurrentStableList[str]: 空冲突集。
        """
        del engines
        return ConcurrentStableList()

    original = orchestrator.precheck_conflicts
    import bms_platform.domains.platform_registry.services.seed_orchestration as module

    module.precheck_conflicts = _no_conflicts  # type: ignore[attr-defined]
    manager = _StubManager()
    try:
        result = await _service(manager=manager, engines=object()).orchestrate(
            SeedOrchestrationRequest(only=ConcurrentStableFrozenList(["seed-module"]))
        )
    finally:
        module.precheck_conflicts = original  # type: ignore[attr-defined]
    assert result.exit_code == EXIT_OK
    assert list(manager.events) == ["begin", "commit"]


# ---- 用例 20/21：筛选与强制前置 ----


async def test_orchestrate_respects_only_filter() -> None:
    """用例 20 服务侧：`--only` 只执行指定项。"""
    result = await _service().orchestrate(
        SeedOrchestrationRequest(only=ConcurrentStableFrozenList(["seed-module", "seed-tables"]), dry_run=True)
    )
    assert [report.name for report in result.reports] == ["seed-module", "seed-tables"]


async def test_orchestrate_require_moves_seed_first() -> None:
    """用例 21 服务侧：`--require` 把种子提到最前（其依赖一并提升）。"""
    result = await _service().orchestrate(
        SeedOrchestrationRequest(require=ConcurrentStableFrozenList(["seed-menu"]), dry_run=True)
    )
    names = [report.name for report in result.reports]
    assert names.index("seed-menu") < names.index("seed-tables")


# ---- 端点契约（用例 24：--json 结构可解析）----


def test_request_schema_defaults() -> None:
    """端点入参缺省值（租户空串取配置、不筛选、非 dry-run、超时 300s）。"""
    schema = SeedOrchestrationRequestSchema()
    assert schema.tenant == ""
    assert (schema.only, schema.skip, schema.require) == ([], [], [])
    assert schema.dry_run is False
    assert schema.timeout_seconds == 300.0


def test_result_schema_fields() -> None:
    """端点出参字段齐全（`exitCode` 驼峰，与 CLI 读取口径一致）。"""
    row: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    row.set("name", "x")
    schema = SeedOrchestrationResultSchema(
        exitCode=2,
        reports=ConcurrentStableList([row]),
        errors=ConcurrentStableList(["e"]),
        conflicts=ConcurrentStableList(["c"]),
    )
    payload = schema.model_dump()
    assert payload["exitCode"] == 2
    assert set(payload) == {"exitCode", "reports", "errors", "conflicts", "warnings"}


def test_result_dataclass_defaults() -> None:
    """服务出参缺省值。"""
    result = SeedOrchestrationResult()
    assert result.exit_code == 0
    assert list(result.reports) == []
    assert list(result.errors) == []


# ---- 分支处理器注册（9 个 op）----


def test_seed_ops_cover_platform_declaration() -> None:
    """9 个平台种子 op 与 `platform.toml` 的 `name` 一一对应。"""
    assert SEED_OPS == (
        "seed-module",
        "seed-tables",
        "seed-menu",
        "seed-tenant",
        "seed-config",
        "seed-platform-role",
        "seed-platform-grant",
        "seed-rbac-role",
        "seed-rbac-grant",
    )


def test_register_seed_handlers_is_idempotent() -> None:
    """注册幂等：重复注册不抛错（已登记即跳过）。"""
    registry = BranchHandlerRegistry()
    register_seed_handlers(registry)
    first = list(registry.ops())
    register_seed_handlers(registry)
    assert list(registry.ops()) == first
    assert set(SEED_OPS) <= set(first)


def test_register_seed_handlers_preserves_existing() -> None:
    """已登记的同名 op 不被覆盖（防隐式覆盖）。"""

    async def _sentinel(_session: Any, _args: Any) -> None:
        """哨兵处理器。"""
        return None

    registry = BranchHandlerRegistry()
    registry.register("seed-module", _sentinel)
    register_seed_handlers(registry)
    assert registry.resolve("seed-module") is _sentinel


def _seed_record(name: str, **tables: str) -> SeedRecord:
    """构造只带统计声明的种子记录。

    Args:
        name: 种子名。
        **tables: 目标表声明（真实表名 = 自然键）。

    Returns:
        SeedRecord: 种子记录。
    """
    return SeedRecord(
        name=name,
        module="demo.seeds",
        entry="seed",
        service="platform",
        db_key="platform_platform",
        tables=ConcurrentStableFrozenDict(tables),
    )


async def test_orchestrate_without_participant_skips_stats() -> None:
    """无分支执行方（`participant=None`）：编排照常返回，不登记统计探针（07B `03_03` 分支补齐）。"""
    service = SeedOrchestrationService(
        caller_service="platform",
        manager=_StubManager(),
        participant=None,
        engines=None,
    )

    result = await service.orchestrate(SeedOrchestrationRequest(dry_run=True))

    assert result.exit_code == 0
    assert result.reports


def test_register_seed_stats_skips_participant_without_method() -> None:
    """占位参与方（无 `register_stats_probe`）时静默跳过，不抛错。"""
    assert list(register_seed_stats(object(), [_seed_record("seed-menu", sys_business="code")])) == []


def test_register_seed_stats_registers_probes() -> None:
    """有 `register_stats_probe` 的参与方按记录收到探针。"""
    registered: ConcurrentStableDict[str, Any] = ConcurrentStableDict()

    class _Participant:
        """参与方替身。"""

        def register_stats_probe(self, op: str, probe: Any) -> None:
            """记录探针。

            Args:
                op: 操作名。
                probe: 探针。
            """
            registered.set(op, probe)

    warnings = register_seed_stats(
        _Participant(),
        [_seed_record(name, sys_module="module_key") for name in SEED_OPS],
    )
    assert set(registered) == set(SEED_OPS)
    assert list(warnings) == []


def test_seed_branch_handlers_exports() -> None:
    """模块导出面（排障与用例断言用）。"""
    assert set(seed_branch_handlers.__all__) == {"SEED_OPS", "register_seed_handlers", "register_seed_stats"}
