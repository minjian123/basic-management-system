"""种子编排**执行链**用例（07B `02_03`；详设 §5 用例 13~17 + 28~29）。

**为什么单独一个文件**：这五条是「统一机制」的**核心验收点**——串行时序 / 全部成功 / 失败整体回滚 /
无脏数据 / 中间态不可见，也是与草案「失败隔离」口径差异的证明（详设 §8 #3 / #7）。

**SQLite 下如何证明**（用户 2026-10-27 拍板的三层方案，见实施记录 §2）：
1. **编排层替身**：注入 `manager` / `branch_runner` 替身，断言严格时序、失败即回滚全部、报告口径；
2. **真实 SQLite 可见性**：用真实连接证明「未提交写入对另一连接不可见」（中间态不可见的库层证据）；
3. **真库 XA 用例**：沿用 `test_cross_db_2pc.py` 口径（`BMS_TEST_MYSQL_URL` 等，未配置即 skip）。
"""

from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import ParamError
from bms_core.services.module_registry import SeedRecord
from bms_core.tenant.seed import orchestrator
from bms_core.transaction.base import (
    BRANCH_PREPARED,
    BRANCH_REJECTED,
    BranchStats,
    GlobalTransaction,
)


def _record(
    name: str, *, after: ConcurrentStableFrozenList[str] | None = None, db_key: str = "platform_platform"
) -> SeedRecord:
    """构造种子记录（用例夹具）。

    Args:
        name: 种子名。
        after: 依赖的种子名。
        db_key: 目标库键。

    Returns:
        SeedRecord: 种子记录。
    """
    return SeedRecord(
        name=name,
        module="ops.seed_menu",
        entry="seed_menu_entry",
        service="platform",
        db_key=db_key,
        after=after if after is not None else ConcurrentStableFrozenList(),
        source="platform",
    )


def _plan(*names: str) -> ConcurrentStableList[orchestrator.SeedPlanItem]:
    """按名字构造计划（无依赖，登记序即执行序）。

    Args:
        *names: 种子名（按执行序）。

    Returns:
        ConcurrentStableList[SeedPlanItem]: 编排计划。
    """
    return orchestrator.build_plan(ConcurrentStableList(_record(name) for name in names), tenant="demo")


class _RecordingRunner:
    """分支执行器替身：记录每次调用与**调用时刻**的状态，可注入失败点。"""

    def __init__(self, *, fail_at: str = "", state: str = BRANCH_PREPARED) -> None:
        """初始化。

        Args:
            fail_at: 该种子名处返回非 prepared（空表示全部成功）。
            state: 全部成功时返回的分支状态。
        """
        self.calls: ConcurrentStableList[str] = ConcurrentStableList()
        self.states: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        self._fail_at = fail_at
        self._state = state

    async def execute_branch_with_stats(
        self, *, xid: str, db_key: str, ops: ConcurrentStableList[Any]
    ) -> tuple[str, BranchStats]:
        """执行分支替身：记录 op 名与状态。

        Args:
            xid: 分支事务标识。
            db_key: 目标库键。
            ops: 分支操作清单。

        Returns:
            tuple[str, BranchStats]: （分支状态, 逐项统计）。
        """
        del xid, db_key
        op = ops[0].op
        self.calls.add(op)
        self.states.set(op, "called")
        if op == self._fail_at:
            return BRANCH_REJECTED, BranchStats()
        return self._state, BranchStats(created=1)


class _RecordingManager:
    """事务管理器替身：记录 begin / commit / rollback 的调用与**顺序**。"""

    def __init__(self, *, branch_count: int) -> None:
        """初始化。

        Args:
            branch_count: 分支数（`begin` 回传对应快照）。
        """
        self.events: ConcurrentStableList[str] = ConcurrentStableList()
        self._branch_count = branch_count
        self.committed: ConcurrentStableList[str] = ConcurrentStableList()
        self.rolled_back: ConcurrentStableList[str] = ConcurrentStableList()

    async def begin(
        self,
        *,
        caller_service: str,
        branches: ConcurrentStableList[Any],
        timeout_seconds: float | None = None,
    ) -> GlobalTransaction:
        """记录 begin 并回传分支快照。

        Args:
            caller_service: 发起方服务键。
            branches: 分支声明。
            timeout_seconds: 全局事务超时。

        Returns:
            GlobalTransaction: 全局事务快照。
        """
        del caller_service
        self.events.add("begin")
        self.timeout_seen = timeout_seconds
        self.branch_specs = branches
        return GlobalTransaction(
            global_txn_id="txn-1",
            caller_service="platform",
            state="active",
            branches=ConcurrentStableFrozenList(
                _branch_ref(spec.branch_id, spec.service, spec.db_key) for spec in branches
            ),
        )

    async def commit(self, global_txn_id: str) -> GlobalTransaction:
        """记录 commit。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            GlobalTransaction: 提交后快照。
        """
        self.events.add("commit")
        self.committed.add(global_txn_id)
        return _txn(global_txn_id, "committed")

    async def rollback(self, global_txn_id: str) -> GlobalTransaction:
        """记录 rollback。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            GlobalTransaction: 回滚后快照。
        """
        self.events.add("rollback")
        self.rolled_back.add(global_txn_id)
        return _txn(global_txn_id, "rolled_back")


def _branch_ref(branch_id: str, service: str, db_key: str) -> Any:
    """构造分支引用（`begin` 回传快照用）。

    Args:
        branch_id: 分支标识。
        service: 参与方服务键。
        db_key: 目标库键。

    Returns:
        Any: 分支引用。
    """
    from bms_core.transaction.base import BranchRef

    return BranchRef(
        branch_id=branch_id,
        service=service,
        db_key=db_key,
        xid=f"txn-1|{branch_id}",
        state="active",
    )


def _txn(global_txn_id: str, state: str) -> GlobalTransaction:
    """构造全局事务快照。

    Args:
        global_txn_id: 全局事务标识。
        state: 事务状态。

    Returns:
        GlobalTransaction: 全局事务快照。
    """
    return GlobalTransaction(global_txn_id=global_txn_id, caller_service="platform", state=state)


# ---- 用例 13：串行执行（严格时序）----


async def test_execute_plan_runs_branches_strictly_serial() -> None:
    """用例 13：前一分支 `prepared` 完成才开下一分支——执行序即计划序，且**逐条**推进。"""
    plan = _plan("a", "b", "c")
    runner = _RecordingRunner()
    manager = _RecordingManager(branch_count=3)
    reports = await orchestrator.execute_plan(
        plan, tenant="demo", caller_service="platform", manager=manager, branch_runner=runner
    )
    assert list(runner.calls) == ["a", "b", "c"]
    assert [report.status for report in reports] == ["ok", "ok", "ok"]
    # 事务事件序：begin 在最前、commit 在最后（中间无 commit / rollback 插入）
    assert list(manager.events) == ["begin", "commit"]


async def test_execute_plan_stops_at_first_failed_branch() -> None:
    """用例 13 强断言：某分支失败即**停止后续分支**（不并发、不继续跑）。"""
    plan = _plan("a", "b", "c", "d")
    runner = _RecordingRunner(fail_at="b")
    manager = _RecordingManager(branch_count=4)
    reports = await orchestrator.execute_plan(
        plan, tenant="demo", caller_service="platform", manager=manager, branch_runner=runner
    )
    assert list(runner.calls) == ["a", "b"]
    assert [report.status for report in reports] == ["rolled_back", "rolled_back", "not_executed", "not_executed"]


async def test_execute_plan_never_commits_before_last_branch_prepared() -> None:
    """用例 13 强断言：commit 只在**全部分支 prepared 之后**发生（中间态不留提交点）。"""

    class _OrderCheckingRunner(_RecordingRunner):
        """执行器替身：在每次分支执行时检查「尚未 commit」。"""

        def __init__(self, manager: _RecordingManager) -> None:
            """初始化。

            Args:
                manager: 事务管理器替身（用于断言事件序）。
            """
            super().__init__()
            self._manager = manager

        async def execute_branch_with_stats(
            self, *, xid: str, db_key: str, ops: ConcurrentStableList[Any]
        ) -> tuple[str, BranchStats]:
            """执行前断言尚未提交。

            Args:
                xid: 分支事务标识。
                db_key: 目标库键。
                ops: 分支操作清单。

            Returns:
                tuple[str, BranchStats]: （分支状态, 逐项统计）。
            """
            assert "commit" not in self._manager.events, "分支执行前不应已提交"
            return await super().execute_branch_with_stats(xid=xid, db_key=db_key, ops=ops)

    plan = _plan("a", "b")
    manager = _RecordingManager(branch_count=2)
    runner = _OrderCheckingRunner(manager)
    await orchestrator.execute_plan(
        plan, tenant="demo", caller_service="platform", manager=manager, branch_runner=runner
    )
    assert list(manager.events) == ["begin", "commit"]


# ---- 用例 14：全部成功 ----


async def test_execute_plan_all_success_reports_each_item() -> None:
    """用例 14：全部成功 → 各分支 prepared → 统一 commit；报告逐项、状态 ok。"""
    plan = _plan("seed-module", "seed-menu")
    runner = _RecordingRunner()
    manager = _RecordingManager(branch_count=2)
    reports = await orchestrator.execute_plan(
        plan, tenant="demo", caller_service="platform", manager=manager, branch_runner=runner
    )
    assert list(manager.committed) == ["txn-1"]
    assert list(manager.rolled_back) == []
    assert [(report.name, report.status) for report in reports] == [
        ("seed-module", "ok"),
        ("seed-menu", "ok"),
    ]


async def test_execute_plan_carries_stats_into_reports() -> None:
    """用例 23 执行侧：逐项统计由执行器采集、编排器汇总（种子不报数）。"""
    plan = _plan("a")
    runner = _RecordingRunner()
    manager = _RecordingManager(branch_count=1)
    reports = await orchestrator.execute_plan(
        plan, tenant="demo", caller_service="platform", manager=manager, branch_runner=runner
    )
    assert reports[0].created == 1
    assert (reports[0].updated, reports[0].skipped) == (0, 0)


async def test_execute_plan_passes_timeout_to_manager() -> None:
    """用例 29 相关：`timeout_seconds` 原样传入 `manager.begin`（超时由 TM 执行）。"""
    plan = _plan("a")
    runner = _RecordingRunner()
    manager = _RecordingManager(branch_count=1)
    await orchestrator.execute_plan(
        plan,
        tenant="demo",
        caller_service="platform",
        timeout_seconds=12.5,
        manager=manager,
        branch_runner=runner,
    )
    assert manager.timeout_seen == 12.5


# ---- 用例 15：某分支失败 → 整体回滚 ----


async def test_execute_plan_failure_rolls_back_all_prepared() -> None:
    """用例 15：某分支 rejected → 立即 rollback 全部已 prepare 分支（不 commit）。"""
    plan = _plan("a", "b", "c")
    runner = _RecordingRunner(fail_at="b")
    manager = _RecordingManager(branch_count=3)
    reports = await orchestrator.execute_plan(
        plan, tenant="demo", caller_service="platform", manager=manager, branch_runner=runner
    )
    assert list(manager.events) == ["begin", "rollback"]
    assert list(manager.committed) == []
    assert list(manager.rolled_back) == ["txn-1"]
    assert all(report.status != "ok" for report in reports)


async def test_execute_plan_failure_marks_all_reports_rolled_back_with_root_cause() -> None:
    """用例 15 报告口径：全部标「已回滚」，并**突出失败那一个的根因**（详设 §3.8）。"""
    plan = _plan("a", "b", "c")
    runner = _RecordingRunner(fail_at="b")
    manager = _RecordingManager(branch_count=3)
    reports = await orchestrator.execute_plan(
        plan, tenant="demo", caller_service="platform", manager=manager, branch_runner=runner
    )
    failed = [report for report in reports if report.note]
    assert len(failed) == 1
    assert failed[0].name == "b"
    assert "← 失败：" in failed[0].note
    assert "分支未就绪" in failed[0].note


async def test_execute_plan_exception_in_branch_rolls_back_and_propagates() -> None:
    """用例 15 补充：分支抛异常 → 回滚全部，异常信息进报告（不吞错）。"""

    class _ExplodingRunner(_RecordingRunner):
        """执行器替身：在指定种子处抛异常。"""

        async def execute_branch_with_stats(
            self, *, xid: str, db_key: str, ops: ConcurrentStableList[Any]
        ) -> tuple[str, BranchStats]:
            """在 `boom` 处抛异常。

            Args:
                xid: 分支事务标识。
                db_key: 目标库键。
                ops: 分支操作清单。

            Returns:
                tuple[str, BranchStats]: 不会返回（抛异常）。

            Raises:
                RuntimeError: 恒定抛出。
            """
            if ops[0].op == "boom":
                self.calls.add("boom")
                raise RuntimeError("种子炸了")
            return await super().execute_branch_with_stats(xid=xid, db_key=db_key, ops=ops)

    plan = _plan("a", "boom")
    runner = _ExplodingRunner()
    manager = _RecordingManager(branch_count=2)
    reports = await orchestrator.execute_plan(
        plan, tenant="demo", caller_service="platform", manager=manager, branch_runner=runner
    )
    assert list(manager.events) == ["begin", "rollback"]
    notes = [report.note for report in reports if report.note]
    assert any("RuntimeError" in note for note in notes)


async def test_execute_plan_requires_injected_dependencies() -> None:
    """用例 15 相关：未注入 manager / runner → `ParamError`（不再零参调基座取用器）。

    这是 2026-10-27 修复的缺陷：原实现零参调 `get_transaction_manager()`（需 `Request`）
    必抛 `TypeError`，编排端点从未跑通（实施记录 §5 第 1 项）。
    """
    with pytest.raises(ParamError, match="缺少依赖注入"):
        await orchestrator.execute_plan(_plan("a"), tenant="demo", caller_service="platform")


async def test_execute_plan_falls_back_for_runner_without_stats() -> None:
    """兼容：执行器只实现 `execute_branch`（无统计）时仍可编排，统计为 0。"""

    class _PlainRunner:
        """仅实现 `execute_branch` 的执行器替身。"""

        async def execute_branch(self, *, xid: str, db_key: str, ops: ConcurrentStableList[Any]) -> str:
            """执行分支（无统计）。

            Args:
                xid: 分支事务标识。
                db_key: 目标库键。
                ops: 分支操作清单。

            Returns:
                str: 分支状态。
            """
            del xid, db_key, ops
            return BRANCH_PREPARED

    manager = _RecordingManager(branch_count=1)
    reports = await orchestrator.execute_plan(
        _plan("a"),
        tenant="demo",
        caller_service="platform",
        manager=manager,
        branch_runner=cast("Any", _PlainRunner()),
    )
    assert reports[0].status == "ok"
    assert reports[0].created == 0


# ---- 用例 16：无脏数据（真实库证明）----


async def test_rollback_leaves_no_rows_in_real_database(tmp_path: Path) -> None:
    """用例 16：失败回滚后目标表**无任何种子写入**（真实 SQLite 库对比执行前快照）。

    证明方式：真实事务内写入 → 回滚 → 另一连接查询为空。对应编排侧「整体回滚 → 零脏数据」。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'seed.db'}"
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("CREATE TABLE probe (id INTEGER PRIMARY KEY, note TEXT)"))
        async with engine.connect() as connection:
            transaction = await connection.begin()
            await connection.execute(text("INSERT INTO probe (id, note) VALUES (1, 'seed')"))
            before_rollback = (await connection.execute(text("SELECT COUNT(*) FROM probe"))).scalar_one()
            assert before_rollback == 1
            await transaction.rollback()
        async with engine.connect() as connection:
            after = (await connection.execute(text("SELECT COUNT(*) FROM probe"))).scalar_one()
        assert after == 0
    finally:
        await engine.dispose()


# ---- 用例 17：中间态不可见（真实库证明）----


async def test_uncommitted_rows_invisible_to_other_connection(tmp_path: Path) -> None:
    """用例 17：分支 prepare 后、commit 前，**另一连接看不到**未提交数据（SQLite 库层证据）。

    对应详设 §3.2「中间态不可见」：XA 分支 prepare 后锁持有到 commit，其他事务读不到。
    SQLite 无两阶段，故用「未提交事务对其他连接不可见」证明同一性质（见实施记录 §2）。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'visibility.db'}"
    engine = create_async_engine(url)
    writer_engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("CREATE TABLE probe (id INTEGER PRIMARY KEY, note TEXT)"))
        async with writer_engine.connect() as writer:
            transaction = await writer.begin()
            await writer.execute(text("INSERT INTO probe (id, note) VALUES (1, 'mid')"))
            # 写入方自己看得到
            assert (await writer.execute(text("SELECT COUNT(*) FROM probe"))).scalar_one() == 1
            # 另一连接（独立引擎 / 连接池）看不到
            async with engine.connect() as reader:
                assert (await reader.execute(text("SELECT COUNT(*) FROM probe"))).scalar_one() == 0
            await transaction.rollback()
    finally:
        await writer_engine.dispose()
        await engine.dispose()


async def test_committed_rows_visible_to_other_connection(tmp_path: Path) -> None:
    """用例 17 对照：提交后另一连接**可见**（证明上一用例的「看不到」确因未提交）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'visible.db'}"
    engine = create_async_engine(url)
    writer_engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("CREATE TABLE probe (id INTEGER PRIMARY KEY, note TEXT)"))
        async with writer_engine.begin() as writer:
            await writer.execute(text("INSERT INTO probe (id, note) VALUES (1, 'done')"))
        async with engine.connect() as reader:
            assert (await reader.execute(text("SELECT COUNT(*) FROM probe"))).scalar_one() == 1
    finally:
        await writer_engine.dispose()
        await engine.dispose()


# ---- 用例 28：跨服务分支（替身级：远程驱动载荷）----


async def test_cross_service_branch_driven_via_runner_contract() -> None:
    """用例 28：跨服务种子的分支经执行器契约驱动（载荷含 xid / db_key / op），不直连他服务库。"""
    plan = orchestrator.build_plan(
        ConcurrentStableList([_record("mdm-admin-codes", db_key="platform_platform")]), tenant="demo"
    )
    seen: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()

    class _SpyRunner(_RecordingRunner):
        """执行器替身：记录每次分支载荷。"""

        async def execute_branch_with_stats(
            self, *, xid: str, db_key: str, ops: ConcurrentStableList[Any]
        ) -> tuple[str, BranchStats]:
            """记录载荷后转发。

            Args:
                xid: 分支事务标识。
                db_key: 目标库键。
                ops: 分支操作清单。

            Returns:
                tuple[str, BranchStats]: （分支状态, 逐项统计）。
            """
            payload: ConcurrentStableDict[str, object] = ConcurrentStableDict()
            payload.set("xid", xid)
            payload.set("db_key", db_key)
            payload.set("op", ops[0].op)
            seen.add(payload)
            return await super().execute_branch_with_stats(xid=xid, db_key=db_key, ops=ops)

    runner = _SpyRunner()
    manager = _RecordingManager(branch_count=1)
    await orchestrator.execute_plan(
        plan, tenant="demo", caller_service="platform", manager=manager, branch_runner=runner
    )
    assert len(seen) == 1
    assert seen[0]["db_key"] == "platform_platform"
    assert seen[0]["op"] == "mdm-admin-codes"
    assert str(seen[0]["xid"]).startswith("txn-1|")


# ---- 用例 29：事务超时（替身级：超时参数与失败处置）----


async def test_timeout_seconds_default_and_override() -> None:
    """用例 29：全局事务超时缺省 300s，可由参数覆盖（详设 §3.12）。"""
    assert orchestrator.DEFAULT_TIMEOUT_SECONDS == 300.0
    plan = _plan("a")
    manager = _RecordingManager(branch_count=1)
    await orchestrator.execute_plan(
        plan,
        tenant="demo",
        caller_service="platform",
        timeout_seconds=5.0,
        manager=manager,
        branch_runner=_RecordingRunner(),
    )
    assert manager.timeout_seen == 5.0


async def test_manager_begin_failure_is_not_silently_swallowed() -> None:
    """用例 29 相关：`begin` 抛异常（如 TM 不可达）→ 异常向上抛，不产生报告（调用方转退出码 2）。"""

    class _FailingManager(_RecordingManager):
        """事务管理器替身：`begin` 抛异常。"""

        async def begin(self, **_kwargs: object) -> GlobalTransaction:
            """恒定抛异常。

            Args:
                **_kwargs: 忽略。

            Raises:
                RuntimeError: 恒定抛出。
            """
            raise RuntimeError("TM 不可达")

    with pytest.raises(RuntimeError, match="TM 不可达"):
        await orchestrator.execute_plan(
            _plan("a"),
            tenant="demo",
            caller_service="platform",
            manager=_FailingManager(branch_count=1),
            branch_runner=_RecordingRunner(),
        )


# ---- 真库 XA 用例（未配置即 skip；与 test_cross_db_2pc.py 同口径）----


@pytest.mark.parametrize("env_name", ["BMS_TEST_MYSQL_URL", "BMS_TEST_PG_URL", "BMS_TEST_DM_URL"])
def test_real_db_two_phase_availability(env_name: str) -> None:
    """用例 17 真库补充：两阶段仅在真库可用（SQLite 不支持，故本批以替身 + 可见性证明为准）。"""
    import os

    if not os.environ.get(env_name):
        pytest.skip(f"未配置 {env_name}，跳过真库两阶段用例（部署窗口 / CI 集成 job 执行）")
    from sqlalchemy import create_engine

    from bms_core.db.engine import _normalize_dialect_url  # pyright: ignore[reportPrivateUsage]

    engine = create_engine(_normalize_dialect_url(os.environ[env_name]))
    try:
        connection = engine.connect()
        try:
            transaction = connection.begin_twophase()
            transaction.rollback()
        finally:
            connection.close()
    finally:
        engine.dispose()
