"""种子统一编排器（07B `02_03`）：一套装载 + 一个 XA 全局事务。

**核心口径**（用户拍板）：平台种子与产品种子走同一套装载注册机制，由平台统一编排，
在**一个 XA 全局事务**内**串行**执行、统一提交或整体回滚——既杜绝「产品 A 执行到一半、
产品 B 读到半成品」，也杜绝「A 成功、B 失败后 A 无法回滚留下脏数据」。

流程：冲突预检（事务外）→ 拓扑排序 → 派生分支 → 串行 execute_branch → 统一 commit / 整体 rollback。

**分支粒度**：每种子一个 XA 分支；**严格串行**——前一分支 `prepared` 完成才开下一分支，
同一时刻只有一个分支在执行，无并发干扰、无互锁。

**入口契约**：沿用既有分支处理器范式 `async def entry(session, args) -> None`
（`bms_core.transaction.base::BranchHandler`），不新增第二套执行范式。
"""

import hashlib
from dataclasses import dataclass
from dataclasses import field as dataclass_field

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import ParamError
from bms_core.core.logging import get_logger
from bms_core.services.module_registry import SeedRecord
from bms_core.transaction.base import (
    BRANCH_PREPARED,
    MAX_BRANCH_ID_LENGTH,
    BranchOp,
    BranchSpec,
    GlobalTransaction,
    get_transaction_manager,
)

__all__ = [
    "EXIT_CONFLICT",
    "EXIT_EXECUTE",
    "EXIT_OK",
    "EXIT_PRECHECK",
    "EXIT_USAGE",
    "SeedPlanItem",
    "SeedReport",
    "branch_id_of",
    "detect_cycles",
    "expand_db_key",
    "precheck_seeds",
    "select_seeds",
    "topological_order",
]

EXIT_OK = 0
"""全部成功（含 skipped）。"""

EXIT_CONFLICT = 1
"""数据冲突（预检发现异值，未进入事务）。"""

EXIT_EXECUTE = 2
"""执行失败（分支 rejected / 抛异常 / commit 失败 / 超时），已整体回滚。"""

EXIT_PRECHECK = 3
"""编排前置错误（重名 / 环 / 依赖缺失 / 前缀违规 / 入口不可解析）。"""

EXIT_USAGE = 64
"""参数错误（`EX_USAGE`；避开 argparse 缺省的 2，防与「执行失败」混淆）。"""

DEFAULT_TIMEOUT_SECONDS = 300.0
"""全局事务超时（秒）：防长锁窗口挂死。"""


@dataclass
class SeedPlanItem:
    """编排计划中的一项（一个种子 + 其派生分支）。"""

    record: SeedRecord
    """种子记录（声明）。"""

    branch_id: str
    """XA 分支标识（种子名哈希前 16 位）。"""

    db_key: str
    """展开后的目标库键。"""


@dataclass
class SeedReport:
    """逐项执行报告（一项一种子）。"""

    name: str
    """种子名。"""

    source: str
    """来源（`platform` / 产品键）。"""

    status: str = "pending"
    """状态（`pending` / `ok` / `skipped` / `rolled_back` / `failed` / `not_executed`）。"""

    created: int = 0
    """新建行数（编排器执行前后对比采集）。"""

    updated: int = 0
    """更新行数。"""

    skipped: int = 0
    """跳过行数。"""

    conflicts: int = 0
    """冲突行数（预检阶段已列出明细）。"""

    note: str = ""
    """说明（失败原因 / 跳过理由）。"""


@dataclass
class PrecheckResult:
    """预检结果（事务外）。"""

    errors: ConcurrentStableList[str] = dataclass_field(default_factory=lambda: ConcurrentStableList())
    """前置错误（重名 / 环 / 依赖 / 前缀 / 入口）。"""

    conflicts: ConcurrentStableList[str] = dataclass_field(default_factory=lambda: ConcurrentStableList())
    """数据冲突明细（键 + 现有值 + 期望值）。"""

    warnings: ConcurrentStableList[str] = dataclass_field(default_factory=lambda: ConcurrentStableList())
    """警示（不阻断）。"""


def branch_id_of(name: str) -> str:
    """取种子名派生的 XA 分支标识（`sha1(name)[:16]`）。

    **为什么用哈希**：`branch_id` 上限 `MAX_BRANCH_ID_LENGTH`（16 字符），种子名可能超长；
    哈希保证长度合规且稳定。报告与日志仍用种子名，不用分支标识。

    Args:
        name: 种子名。

    Returns:
        str: 分支标识（16 位十六进制）。
    """
    return hashlib.sha1(name.encode("utf-8")).hexdigest()[:MAX_BRANCH_ID_LENGTH]


def expand_db_key(db_key: str, *, tenant: str) -> str:
    """展开 `db_key` 中的租户占位。

    Args:
        db_key: 声明中的库键（可能含租户占位）。
        tenant: 目标租户码。

    Returns:
        str: 展开后的库键。
    """
    return db_key.replace("{" + "tenant" + "}", tenant)


def select_seeds(
    records: ConcurrentStableList[SeedRecord],
    *,
    only: ConcurrentStableList[str],
    skip: ConcurrentStableList[str],
    require: ConcurrentStableList[str],
) -> ConcurrentStableList[SeedRecord]:
    """按 `--only` / `--skip` / `--require` 筛选执行集合。

    `--only` **不自动补依赖**（显式优于隐式）；`--require` 的目标若不在集合内即拒（约束须可兑现）。

    Args:
        records: 全部种子记录。
        only: 只执行这些（空表示不限制）。
        skip: 跳过这些。
        require: 必须在本批之前完成（空表示无人工强制）。

    Returns:
        ConcurrentStableList[SeedRecord]: 执行集合（保持登记序）。

    Raises:
        ParamError: `--only` / `--skip` / `--require` 引用了不存在的种子名。
    """
    names = ConcurrentStableList(record.name for record in records)
    for label, group in (("--only", only), ("--skip", skip), ("--require", require)):
        for name in group:
            if name not in names:
                raise ParamError(f"{label} 引用了不存在的种子：{name}")
    selected = ConcurrentStableList(
        record for record in records if (not only or record.name in only) and record.name not in skip
    )
    for name in require:
        if name not in [record.name for record in selected]:
            raise ParamError(f"--require 的目标不在执行集合内：{name}")
    return selected


def detect_cycles(records: ConcurrentStableList[SeedRecord]) -> ConcurrentStableList[str]:
    """检测 `after` 依赖环。

    Args:
        records: 种子记录。

    Returns:
        ConcurrentStableList[str]: 环上的种子名（空表示无环）。
    """
    graph: ConcurrentStableDict[str, ConcurrentStableList[str]] = ConcurrentStableDict()
    known = {record.name for record in records}
    for record in records:
        graph.set(record.name, ConcurrentStableList(item for item in record.after if item in known))
    visiting: ConcurrentStableDict[str, bool] = ConcurrentStableDict()
    visited: ConcurrentStableDict[str, bool] = ConcurrentStableDict()
    path: ConcurrentStableList[str] = ConcurrentStableList()
    cycle: ConcurrentStableList[str] = ConcurrentStableList()

    def _walk(node: str) -> bool:
        """深度优先：命中回边即记录环并短路。

        Args:
            node: 当前节点。

        Returns:
            bool: 发现环为 True。
        """
        if visiting.get(node):
            start = path.index(node) if node in path else 0
            cycle.update(path[start:])
            return True
        if visited.get(node):
            return False
        visiting.set(node, True)
        path.add(node)
        for dep in graph.get(node) or ConcurrentStableList():
            if _walk(dep):
                return True
        path.remove(node)
        visiting.set(node, False)
        visited.set(node, True)
        return False

    for record in records:
        if _walk(record.name):
            break
    return cycle


def topological_order(records: ConcurrentStableList[SeedRecord]) -> ConcurrentStableList[SeedRecord]:
    """按 `after` 拓扑排序（同层按登记序稳定）。

    Args:
        records: 种子记录（已确认无环）。

    Returns:
        ConcurrentStableList[SeedRecord]: 执行顺序。
    """
    remaining = ConcurrentStableList(records)
    ordered: ConcurrentStableList[SeedRecord] = ConcurrentStableList()
    done: ConcurrentStableDict[str, bool] = ConcurrentStableDict()
    known = {record.name for record in records}
    while remaining:
        progressed = False
        for record in list(remaining):
            deps = [item for item in record.after if item in known]
            if all(done.get(dep) for dep in deps):
                ordered.add(record)
                done.set(record.name, True)
                remaining.remove(record)
                progressed = True
        if not progressed:
            break
    return ordered


def precheck_seeds(records: ConcurrentStableList[SeedRecord]) -> PrecheckResult:
    """事务**外**的前置校验：重名 / 环 / 依赖缺失 / 字段缺失 / 入口可解析。

    **为什么在事务外**：快速失败、一次看全、不浪费 XA 开销（详设 §3.5）。
    数据冲突（异值）另由 `precheck_conflicts` 承担（需连库）。

    Args:
        records: 全部种子记录（合并视图）。

    Returns:
        PrecheckResult: 前置错误与警示。
    """
    result = PrecheckResult()
    known = {record.name for record in records}
    seen: ConcurrentStableDict[str, SeedRecord] = ConcurrentStableDict()
    for record in records:
        existing = seen.get(record.name)
        if existing is not None:
            if existing != record:
                result.errors.add(f"种子重名且声明不一致：{record.name}")
            continue
        seen.set(record.name, record)
        if not record.service:
            result.errors.add(f"种子 {record.name}：缺少执行服务声明（service）")
        if not record.db_key:
            result.errors.add(f"种子 {record.name}：缺少分支目标库声明（db_key）")
        for dep in record.after:
            if dep not in known:
                result.errors.add(f"种子 {record.name}：依赖的种子不存在（after → {dep}）")
    cycle = detect_cycles(records)
    if cycle:
        result.errors.add(f"种子依赖成环：{' → '.join(cycle)}")
    return result


def build_plan(
    records: ConcurrentStableList[SeedRecord],
    *,
    tenant: str,
) -> ConcurrentStableList[SeedPlanItem]:
    """派生编排计划：排序 + 每种子一分支。

    Args:
        records: 已筛选的执行集合（无环）。
        tenant: 目标租户（展开 `db_key` 占位）。

    Returns:
        ConcurrentStableList[SeedPlanItem]: 按执行顺序的计划项。
    """
    ordered = topological_order(records)
    plan: ConcurrentStableList[SeedPlanItem] = ConcurrentStableList()
    for record in ordered:
        plan.add(
            SeedPlanItem(
                record=record,
                branch_id=branch_id_of(record.name),
                db_key=expand_db_key(record.db_key, tenant=tenant),
            )
        )
    return plan


def _source_of(record: SeedRecord) -> str:
    """推断种子来源（`platform` 或产品键）。

    Args:
        record: 种子记录。

    Returns:
        str: 来源标识。
    """
    return record.name.split("-", 1)[0] if "-" in record.name else "platform"


def build_branch_specs(plan: ConcurrentStableList[SeedPlanItem]) -> ConcurrentStableList[BranchSpec]:
    """按计划派生 XA 分支声明（每种子一分支）。

    Args:
        plan: 编排计划。

    Returns:
        ConcurrentStableList[BranchSpec]: 分支声明（顺序与计划一致）。
    """
    return ConcurrentStableList(
        BranchSpec(branch_id=item.branch_id, service=item.record.service, db_key=item.db_key) for item in plan
    )


def build_branch_ops(item: SeedPlanItem, *, tenant: str) -> ConcurrentStableFrozenList[BranchOp]:
    """构造单个种子的分支操作清单（一个 op = 一个种子）。

    Args:
        item: 计划项。
        tenant: 目标租户。

    Returns:
        ConcurrentStableFrozenList[BranchOp]: 分支操作（`op` 缺省取种子名）。
    """
    args: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    args.set("tenant", tenant)
    args.set("db_key", item.db_key)
    return ConcurrentStableFrozenList((BranchOp(op=item.record.op or item.record.name, args=args),))


async def execute_plan(
    plan: ConcurrentStableList[SeedPlanItem],
    *,
    tenant: str,
    caller_service: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    branch_runner: object | None = None,
) -> ConcurrentStableFrozenList[SeedReport]:
    """在**一个 XA 全局事务**内串行执行全部种子，统一提交或整体回滚。

    **串行约束**：前一分支 `prepared` 完成才开下一分支（同一时刻只有一个分支在执行）。
    任一分支未达 `prepared` → 立即 `rollback` 全部已 prepare 分支，**零脏数据**。

    Args:
        plan: 编排计划（按执行顺序）。
        tenant: 目标租户。
        caller_service: 发起方服务键。
        timeout_seconds: 全局事务超时。
        branch_runner: 分支执行器（测试注入用；缺省取基座事务参与方）。

    Returns:
        ConcurrentStableFrozenList[SeedReport]: 逐项报告（失败时全部标「已回滚」）。

    Raises:
        Exception: 分支执行异常（已回滚后原样抛出，由调用方转退出码）。
    """
    logger = get_logger("bms")
    reports: ConcurrentStableList[SeedReport] = ConcurrentStableList(
        SeedReport(name=item.record.name, source=_source_of(item.record)) for item in plan
    )
    if not plan:
        return ConcurrentStableFrozenList(reports)
    manager = get_transaction_manager()
    specs = build_branch_specs(plan)
    txn: GlobalTransaction = await manager.begin(
        caller_service=caller_service, branches=specs, timeout_seconds=timeout_seconds
    )
    runner = branch_runner if branch_runner is not None else _default_branch_runner()
    xid_of: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for branch in txn.branches:
        xid_of.set(branch.branch_id, branch.xid)
    failed_index: int = -1
    failure_note: str = ""
    try:
        for index, item in enumerate(plan):
            ops = build_branch_ops(item, tenant=tenant)
            state = await _run_branch(
                runner,
                xid=xid_of.get(item.branch_id) or "",
                db_key=item.db_key,
                ops=ops,
            )
            if state != BRANCH_PREPARED:
                failed_index = index
                failure_note = f"分支未就绪（{state}）"
                logger.error("seed_branch_rejected", seed=item.record.name, state=state)
                break
            reports[index].status = "prepared"
        if failed_index >= 0:
            await manager.rollback(txn.global_txn_id)
            return _rolled_back(reports, failed_index=failed_index, note=failure_note)
        await manager.commit(txn.global_txn_id)
    except Exception as exc:
        logger.error("seed_orchestration_failed", detail=f"{type(exc).__name__}: {exc}")
        await manager.rollback(txn.global_txn_id)
        return _rolled_back(reports, failed_index=_first_unfinished(reports), note=f"{type(exc).__name__}: {exc}")
    for report in reports:
        report.status = "ok"
    return ConcurrentStableFrozenList(reports)


def _default_branch_runner() -> object:
    """取基座事务参与方（缺省分支执行器）。

    Returns:
        object: 事务参与方（具备 `execute_branch`）。
    """
    from bms_core.transaction.base import get_transaction_participant

    return get_transaction_participant()


async def _run_branch(runner: object, *, xid: str, db_key: str, ops: object) -> str:
    """调用分支执行器执行一个分支。

    Args:
        runner: 分支执行器。
        xid: 分支事务标识。
        db_key: 目标库键。
        ops: 分支操作清单。

    Returns:
        str: 分支状态。
    """
    execute = runner.execute_branch
    state = await execute(xid=xid, db_key=db_key, ops=ops)
    return str(state)


def _first_unfinished(reports: ConcurrentStableList[SeedReport]) -> int:
    """取第一个未完成的报告下标（异常定位用）。

    Args:
        reports: 报告列表。

    Returns:
        int: 下标（全部完成返回 -1）。
    """
    for index, report in enumerate(reports):
        if report.status == "prepared":
            continue
        return index
    return -1


def _rolled_back(
    reports: ConcurrentStableList[SeedReport], *, failed_index: int, note: str
) -> ConcurrentStableFrozenList[SeedReport]:
    """把报告整体标记为「已回滚」，并突出失败项根因（详设 §3.8）。

    Args:
        reports: 报告列表。
        failed_index: 失败项下标（-1 表示未定位）。
        note: 失败原因。

    Returns:
        ConcurrentStableFrozenList[SeedReport]: 标记后的报告。
    """
    for index, report in enumerate(reports):
        if report.status == "prepared":
            report.status = "rolled_back"
        elif report.status == "pending":
            report.status = "not_executed"
        if index == failed_index:
            report.status = "rolled_back"
            report.note = f"← 失败：{note}"
    return ConcurrentStableFrozenList(reports)
