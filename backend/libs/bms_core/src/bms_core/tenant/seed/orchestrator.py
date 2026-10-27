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
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any, Protocol, cast

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import ParamError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseDataContract
from bms_core.services.module_registry import SeedRecord
from bms_core.tenant.seed.contract import ExpectedRow
from bms_core.transaction.base import (
    BRANCH_PREPARED,
    MAX_BRANCH_ID_LENGTH,
    BranchOp,
    BranchSpec,
    BranchStats,
    GlobalTransaction,
)

__all__ = [
    "EXIT_CONFLICT",
    "EXIT_EXECUTE",
    "EXIT_OK",
    "EXIT_PRECHECK",
    "EXIT_USAGE",
    "ExpectedRow",
    "SeedPlanItem",
    "SeedReport",
    "branch_id_of",
    "detect_cycles",
    "expand_db_key",
    "expected_rows_of",
    "precheck_conflicts",
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


class SeedBranchRunner(Protocol):
    """分支执行器契约（编排器只需这两个方法；生产为 `XaTransactionParticipant`）。"""

    async def execute_branch_with_stats(
        self, *, xid: str, db_key: str, ops: ConcurrentStableList[BranchOp]
    ) -> tuple[str, BranchStats]:
        """执行分支并返回逐项统计。

        Args:
            xid: 分支事务标识。
            db_key: 目标库键。
            ops: 分支操作清单。

        Returns:
            tuple[str, BranchStats]: （分支状态, 逐项统计）。
        """
        ...


class SeedTransactionManager(Protocol):
    """事务管理器契约（编排器只需这三步；生产为 `XaTransactionManager`）。"""

    async def begin(
        self,
        *,
        caller_service: str,
        branches: ConcurrentStableList[BranchSpec],
        timeout_seconds: float | None = None,
    ) -> GlobalTransaction:
        """开启全局事务。

        Args:
            caller_service: 发起方服务键。
            branches: 分支声明。
            timeout_seconds: 全局提交截止（秒）。

        Returns:
            GlobalTransaction: 全局事务快照。
        """
        ...

    async def commit(self, global_txn_id: str) -> GlobalTransaction:
        """请求提交。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            GlobalTransaction: 提交后的快照。
        """
        ...

    async def rollback(self, global_txn_id: str) -> GlobalTransaction:
        """请求回滚。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            GlobalTransaction: 回滚后的快照。
        """
        ...


@dataclass
class SeedPlanItem(BaseDataContract):
    """编排计划中的一项（一个种子 + 其派生分支）。"""

    record: SeedRecord
    """种子记录（声明）。"""

    branch_id: str
    """XA 分支标识（种子名哈希前 16 位）。"""

    db_key: str
    """展开后的目标库键。"""


@dataclass
class SeedReport(BaseDataContract):
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
class PrecheckResult(BaseDataContract):
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
    selected_names = ConcurrentStableList(record.name for record in selected)
    for name in require:
        if name not in selected_names:
            raise ParamError(f"--require 的目标不在执行集合内：{name}")
    # 强制前置的依赖闭包必须可兑现（详设 §3.6.5）：require 项的 after 依赖若不在本批，
    # 提升后仍无法保证「在本批全部之前完成」，故直接拒绝而非静默降级。
    for name in require:
        record = next(item for item in selected if item.name == name)
        for dependency in record.after:
            if dependency not in selected_names:
                raise ParamError(
                    f"--require 的目标 {name} 依赖的种子不在执行集合内：{dependency}"
                    f"（强制前置须可兑现，请一并 --only 选中或去掉 --skip）"
                )
    return selected


def require_closure(
    records: ConcurrentStableList[SeedRecord], require: ConcurrentStableList[str]
) -> ConcurrentStableFrozenList[str]:
    """展开 `--require` 的依赖闭包（含被 require 项自身的传递依赖）。

    强制前置项要「在本批全部之前完成」，其自身依赖也必须同在该组内，否则优先级会压过依赖正确性。

    Args:
        records: 执行集合（已筛选）。
        require: 被 require 的种子名。

    Returns:
        ConcurrentStableFrozenList[str]: 强制前置组的种子名（含传递依赖）。
    """
    by_name = {record.name: record for record in records}
    closure: ConcurrentStableList[str] = ConcurrentStableList()
    pending: ConcurrentStableList[str] = ConcurrentStableList(require)
    while pending:
        name = pending.pop(0)
        if name in closure or name not in by_name:
            continue
        closure.add(name)
        for dependency in by_name[name].after:
            if dependency not in closure:
                pending.add(dependency)
    return ConcurrentStableFrozenList(closure)


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


def _module_exists(dotted: str) -> bool:
    """判断点分模块是否存在（顶层包不存在即 False，不抛错）。

    Args:
        dotted: 点分模块路径。

    Returns:
        bool: 存在返回 True。
    """
    import importlib.util

    top = dotted.split(".")[0]
    try:
        return importlib.util.find_spec(top) is not None
    except ModuleNotFoundError:
        return False


def expected_rows_of(record: SeedRecord) -> ConcurrentStableList[ExpectedRow]:
    """取某个种子的期望行（实现模块**可选**暴露 `expected_rows()`）。

    Args:
        record: 种子记录。

    Returns:
        ConcurrentStableList[ExpectedRow]: 期望行（未实现 / 不可导入时为空列表）。
    """
    import importlib

    # 模块不可导入 = 该种子不提供期望行（**能力探测**，不是吞异常降级）：入口可解析性已由
    # `precheck_seeds` 在事务外校验并报错，故这里只判存在性、不捕获导入期异常。
    if not _module_exists(record.module):
        return ConcurrentStableList()
    module = importlib.import_module(record.module)
    factory = getattr(module, "expected_rows", None)
    if not callable(factory):
        return ConcurrentStableList()
    rows: object = factory()
    return ConcurrentStableList(cast("Iterable[ExpectedRow]", rows))


def _compare_row(existing: object, expected: ExpectedRow) -> ConcurrentStableList[str]:
    """比对现有行与期望值，返回不一致的字段明细。

    Args:
        existing: 数据库现有行（ORM 行或同构对象）。
        expected: 期望行。

    Returns:
        ConcurrentStableList[str]: 不一致明细（空表示全部一致）。
    """
    diffs: ConcurrentStableList[str] = ConcurrentStableList()
    for column, want in expected.values.items():
        actual = getattr(existing, column, None)
        if actual != want:
            diffs.add(f"{column}：现有 {actual!r} / 期望 {want!r}")
    return diffs


async def precheck_conflicts(
    plan: ConcurrentStableList[SeedPlanItem],
    *,
    engines: object,
) -> ConcurrentStableList[str]:
    """事务**外**的数据冲突预检（详设 §3.5）：按 `tables` 声明只读比对目标表。

    **为什么在事务外**：快速失败、一次看全、不浪费 XA 开销。**为什么在结构前置之后**：
    表须先就绪才能查（故调用点在 `ensure_structure` 之后、`TM.begin()` 之前）。

    Args:
        plan: 编排计划（已展开库键）。
        engines: 同步引擎提供者（具备 `get_sync(db_key)`；生产为 `EngineRegistry`）。

    Returns:
        ConcurrentStableList[str]: 冲突明细（空表示无冲突）。
    """
    import asyncio

    conflicts: ConcurrentStableList[str] = ConcurrentStableList()
    for item in plan:
        rows = expected_rows_of(item.record)
        if not rows:
            continue
        engine = await engines.get_sync(item.db_key)  # type: ignore[attr-defined]
        for expected in rows:
            found = await asyncio.to_thread(_fetch_row, engine, expected)
            if found is None:
                continue
            diffs = _compare_row(found, expected)
            if diffs:
                key_text = "、".join(f"{column}={value!r}" for column, value in expected.key.items())
                conflicts.add(
                    f"种子 {item.record.name}：{expected.table}（{key_text}）与声明不一致 → {'；'.join(diffs)}"
                )
    return conflicts


def _fetch_row(engine: Any, expected: ExpectedRow) -> Any:
    """按期望行的自然键查目标表（同步；供 `asyncio.to_thread` 调用）。

    Args:
        engine: 同步引擎。
        expected: 期望行。

    Returns:
        Any: 命中的行（无行 / 表未登记时 None）。
    """
    from sqlalchemy import select

    table = _table_for(expected.table)
    if table is None:
        return None
    statement = select(table)
    for column, value in expected.key.items():
        if column in table.c:
            statement = statement.where(table.c[column] == value)
    with engine.connect() as connection:
        return connection.execute(statement).first()


def _table_for(table_name: str) -> Any:
    """按真实表名取目标表对象。

    说明：声明 `tables` 段是「**逻辑名 → 自然键列**」（如 `module = "module_key"`），供统计口径用；
    `expected_rows()` 给出的 `table` 是**真实表名**（如 `sys_module`），故这里直接按元数据解析，
    不经 `tables` 段。两者分工：声明段给统计、期望行给预检。

    Args:
        table_name: 真实表名。

    Returns:
        Any: SQLAlchemy 表对象（未登记时 None）。
    """
    from bms_core.models.base import Base

    return Base.metadata.tables.get(table_name)


def build_plan(
    records: ConcurrentStableList[SeedRecord],
    *,
    tenant: str,
    require: ConcurrentStableList[str] | None = None,
) -> ConcurrentStableList[SeedPlanItem]:
    """派生编排计划：排序 + 每种子一分支。

    **`--require` 排序口径**（详设 §3.6.5，Q12）：强制前置组（require 项 + 其传递依赖）排在
    常规组之前，两组**各自**按 `after` 拓扑排序——优先级不压过依赖正确性。

    Args:
        records: 已筛选的执行集合（无环）。
        tenant: 目标租户（展开 `db_key` 占位）。
        require: 人工强制前置的种子名（空表示无强制）。

    Returns:
        ConcurrentStableList[SeedPlanItem]: 按执行顺序的计划项。
    """
    forced = require_closure(records, require or ConcurrentStableList())
    if forced:
        front = ConcurrentStableList(record for record in records if record.name in forced)
        rest = ConcurrentStableList(record for record in records if record.name not in forced)
        ordered = ConcurrentStableList((*topological_order(front), *topological_order(rest)))
    else:
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
    """取种子来源（`platform` 或产品键）。

    **来源是装载期事实**：由 `products.py` 按清单 `product_key` 注入 `record.source`。
    原实现按种子名首段推断，会把 `seed-module` 误判为 `seed`（详设 §8 #25）。
    未注入时回退 `platform`（仅旧清单 / 单测构造的记录会如此）。

    Args:
        record: 种子记录。

    Returns:
        str: 来源标识。
    """
    return record.source or "platform"


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
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    payload.set("tenant", tenant)
    payload.set("db_key", item.db_key)
    frozen: ConcurrentStableFrozenDict[str, object] = ConcurrentStableFrozenDict(payload)
    op = BranchOp(op=item.record.op or item.record.name, args=frozen)
    return ConcurrentStableFrozenList((op,))


async def execute_plan(
    plan: ConcurrentStableList[SeedPlanItem],
    *,
    tenant: str,
    caller_service: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    branch_runner: SeedBranchRunner | None = None,
    manager: SeedTransactionManager | None = None,
) -> ConcurrentStableFrozenList[SeedReport]:
    """在**一个 XA 全局事务**内串行执行全部种子，统一提交或整体回滚。

    **串行约束**：前一分支 `prepared` 完成才开下一分支（同一时刻只有一个分支在执行）。
    任一分支未达 `prepared` → 立即 `rollback` 全部已 prepare 分支，**零脏数据**。

    **依赖注入（2026-10-27 修复）**：`manager` / `branch_runner` 由调用方注入——基座取用器
    （`get_transaction_manager` / `get_transaction_participant`）需 FastAPI `Request`，编排器
    在服务层被调用时没有请求上下文，故不能在此零参调用（原实现必抛 `TypeError`，编排端点从未跑通）。

    Args:
        plan: 编排计划（按执行顺序）。
        tenant: 目标租户。
        caller_service: 发起方服务键。
        timeout_seconds: 全局事务超时。
        branch_runner: 分支执行器（参与方；须具备 `execute_branch_with_stats`）。
        manager: 事务管理器（须具备 `begin` / `commit` / `rollback`）。

    Returns:
        ConcurrentStableFrozenList[SeedReport]: 逐项报告（失败时全部标「已回滚」）。

    Raises:
        ParamError: 未注入 `manager` 或 `branch_runner`（编排器不自行解析依赖）。
        Exception: 分支执行异常（已回滚后原样抛出，由调用方转退出码）。
    """
    if manager is None or branch_runner is None:
        raise ParamError("编排执行缺少依赖注入：须由调用方提供事务管理器与分支执行器")
    logger = get_logger("bms")
    reports: ConcurrentStableList[SeedReport] = ConcurrentStableList(
        SeedReport(name=item.record.name, source=_source_of(item.record)) for item in plan
    )
    if not plan:
        return ConcurrentStableFrozenList(reports)
    specs = build_branch_specs(plan)
    txn: GlobalTransaction = await manager.begin(
        caller_service=caller_service, branches=specs, timeout_seconds=timeout_seconds
    )
    xid_of: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for branch in txn.branches:
        xid_of.set(branch.branch_id, branch.xid)
    failed_index: int = -1
    failure_note: str = ""
    try:
        for index, item in enumerate(plan):
            ops = build_branch_ops(item, tenant=tenant)
            state, stats = await _run_branch(
                branch_runner,
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
            reports[index].created = stats.created
            reports[index].updated = stats.updated
            reports[index].skipped = stats.skipped
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


async def _run_branch(
    runner: SeedBranchRunner, *, xid: str, db_key: str, ops: ConcurrentStableFrozenList[BranchOp]
) -> tuple[str, BranchStats]:
    """调用分支执行器执行一个分支（带逐项统计）。

    **兼容**：执行器只实现 `execute_branch`（无统计能力，如既有参与方替身）时仍可编排，
    统计按 0 处理——不因「拿不到统计」而让整批种子失败。

    Args:
        runner: 分支执行器（优先 `execute_branch_with_stats`，回退 `execute_branch`）。
        xid: 分支事务标识。
        db_key: 目标库键。
        ops: 分支操作清单。

    Returns:
        tuple[str, BranchStats]: （分支状态, 逐项统计）。

    Raises:
        ParamError: 执行器两个方法都没有。
    """
    payload = ConcurrentStableList(ops)
    with_stats = getattr(runner, "execute_branch_with_stats", None)
    if with_stats is not None:
        outcome: tuple[str, BranchStats] = await with_stats(xid=xid, db_key=db_key, ops=payload)
        return str(outcome[0]), outcome[1]
    plain = getattr(runner, "execute_branch", None)
    if plain is not None:
        raw_state: str = await plain(xid=xid, db_key=db_key, ops=payload)
        return str(raw_state), BranchStats()
    raise ParamError("分支执行器既未实现 execute_branch_with_stats，也未实现 execute_branch")


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


async def ensure_structure(
    plan: ConcurrentStableList[SeedPlanItem],
    *,
    tenant: str,
) -> ConcurrentStableList[str]:
    """**结构前置阶段**（07B `02_03`）：种子执行前确保目标库表结构就绪。

    **为什么必须在种子之前**：种子写的是具体表（`sys_business` / `sys_menu` / …），
    表不存在时种子直接失败。故编排在 `TM.begin()` **之前**先做幂等建表。

    **只建表、不跑迁移**（拍板）：当前阶段迁移脚本已清空（`06_05`），建表是唯一落地路径；
    迁移机制保留，等需要「既有库在线升级」时再接（开放项）。

    Args:
        plan: 编排计划（取涉及的库键）。
        tenant: 目标租户（展开库键占位）。

    Returns:
        ConcurrentStableList[str]: 错误明细（空表示结构就绪）。
    """
    from bms_core.core.config import get_settings
    from bms_core.db.bootstrap import ensure_unit_schema

    del plan, tenant  # 建表按「单元 × 数据源 × 租户」矩阵，不逐种子推导
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    try:
        created = await ensure_unit_schema(get_settings())
    except Exception as exc:  # 建表失败即中止，不进种子
        errors.add(f"结构就绪失败：{type(exc).__name__}: {exc}")
        return errors
    if created:
        get_logger("bms").info("seed_structure_ready", tables=len(created))
    return errors
