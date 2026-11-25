"""账本保留期清理用例（强一致专项 05_07；Kiwi 2271；详设 §3.5）。

覆盖：超期终态删除（主记录 + 分支级联）/ 未超期保留 / **非终态一律不动** / 台账超期删除 /
批量上限 / `--dry-run` 只统计不删 / 指标上报 / 子命令入口与分派。
"""

from __future__ import annotations

import argparse
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import Table, insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db.gate import LazyGatedSession, db_access_gate
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.testing.transaction import _sqlite_autocommit, gate_for_engine  # pyright: ignore[reportPrivateUsage]
from bms_core.transaction.base import TXN_ACTIVE
from bms_txn.domains.txn.models.ledger import GlobalTxn, GlobalTxnBranch, GlobalTxnRecovery
from bms_txn.domains.txn.repositories.ledger import (
    GlobalTxnBranchRepository,
    GlobalTxnRecoveryRepository,
    GlobalTxnRepository,
)
from bms_txn.domains.txn.services.ledger_cleanup import METRIC_CLEANED, CleanupStats, LedgerCleanup
from tests_support.metrics import RecordingMetrics
from tests_support.shared_access import shared_engine, shared_platform_url

pytestmark = [pytest.mark.kiwi_id(2271)]

SessionMaker = async_sessionmaker[AsyncSession]
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
"""固定「当前时间」（用例注入，避免依赖真实时钟）。"""

RETENTION = 30
"""保留期（天）。"""


def _gated(engine: AsyncEngine) -> AsyncSession:
    """把引擎包成操作级写门会话（每次写操作取写门、写完即放）。

    Args:
        engine: 目标库引擎。

    Returns:
        AsyncSession: 门代理会话。
    """
    gate_name = gate_for_engine(engine)
    maker: async_sessionmaker[AsyncSession] = async_sessionmaker(_sqlite_autocommit(engine), expire_on_commit=False)
    raw = maker()
    if gate_name is None:  # pragma: no cover - 共享平台库必然命中门名
        return raw
    return cast("AsyncSession", LazyGatedSession(lambda: db_access_gate(gate_name, read_only=False), raw, bind=engine))


@pytest.fixture
def caller() -> str:
    """每例一个唯一发起方服务键（清理按它收口，事务标识也带它作前缀）。

    Returns:
        str: 发起方服务键。
    """
    return f"svc-{uuid4().hex[:10]}"


class _LedgerEngine:
    """内存 SQLite 账本（进入建三表、退出释放引擎）。"""

    def __init__(self) -> None:
        # 账本三表归属登记在平台库：共用共享平台库（建表幂等）
        self.engine = shared_engine(shared_platform_url())

    async def __aenter__(self) -> Callable[[], AsyncSession]:
        """建表并返回会话工厂（每次调用开一个门代理会话）。"""
        async with self.engine.begin() as connection:
            for model in (GlobalTxn, GlobalTxnBranch, GlobalTxnRecovery):
                await connection.run_sync(cast("Table", model.__table__).create, checkfirst=True)
        return lambda: _gated(self.engine)

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """释放引擎。"""
        del exc_type, exc, traceback
        await self.engine.dispose()


@pytest.fixture
async def ledger() -> AsyncIterator[Callable[[], AsyncSession]]:
    """账本会话工厂（内存 SQLite，三表）。"""
    async with _LedgerEngine() as factory:
        yield factory


def _cleanup(
    factory: Callable[[], AsyncSession], *, retention: int = RETENTION, metrics: RecordingMetrics | None = None
) -> tuple[LedgerCleanup, AsyncSession]:
    """构造清理器与仓储集合（同一会话）。

    Returns:
        tuple: (`LedgerCleanup`, 会话) 二元组 —— 会话由调用方关闭。
    """
    session = factory()
    cleanup = LedgerCleanup(
        GlobalTxnRepository(session),
        GlobalTxnBranchRepository(session),
        GlobalTxnRecoveryRepository(session),
        DbUnitOfWork(session),
        retention_days=retention,
        metrics=metrics,
    )
    return cleanup, session


async def _seed(
    factory: Callable[[], AsyncSession],
    *,
    caller: str,
    global_txn_id: str,
    state: str,
    age_days: int,
    branches: int = 2,
    recovery_age_days: int | None = None,
) -> None:
    """造一条全局事务（含分支）与可选处置台账；`age_days` 为「距今多少天」。"""
    # 造数走 SQLAlchemy Core：**不建 ORM 对象**，`created_at` / `updated_at` 由这里显式指定。
    # 走 ORM 对象的话 `before_insert` 事件会把 `updated_at` 覆盖成真实时钟；而「先 ORM 插入、
    # 再裸 SQL 回填时间」会在共享库的门代理会话上留下版本不一致（StaleDataError）。
    # 标识按用例前缀化：共享库里固定 `g-old` 会撞唯一键
    global_txn_id = f"{caller}-{global_txn_id}"
    session = factory()
    stamp = (NOW - timedelta(days=age_days)).replace(tzinfo=None)
    try:
        await session.execute(
            insert(GlobalTxn).values(
                global_txn_id=global_txn_id,
                caller_service=caller,
                state=state,
                deadline_at=stamp,
                decided_at=None,
                created_at=stamp,
                updated_at=stamp,
            )
        )
        for index in range(branches):
            await session.execute(
                insert(GlobalTxnBranch).values(
                    global_txn_id=global_txn_id,
                    branch_id=f"b{index}",
                    service="platform",
                    db_key="platform",
                    xid=f"{global_txn_id}|b{index}",
                    state="committed",
                    created_at=stamp,
                    updated_at=stamp,
                )
            )
        if recovery_age_days is not None:
            detected = (NOW - timedelta(days=recovery_age_days)).replace(tzinfo=None)
            await session.execute(
                insert(GlobalTxnRecovery).values(
                    global_txn_id=global_txn_id,
                    caller_service=caller,
                    branch_id=None,
                    detected_at=detected,
                    hung_seconds=None,
                    action="drive_commit",
                    actor="recoverer",
                    handler=None,
                    conclusion="ok",
                    created_at=detected,
                    updated_at=detected,
                )
            )
        await session.commit()
    finally:
        await session.close()


async def _counts(factory: Callable[[], AsyncSession], caller: str) -> tuple[int, int, int]:
    """取三表行数（主记录 / 分支 / 台账）。"""
    session = factory()
    try:
        txns = GlobalTxnRepository(session)
        repo_branches = GlobalTxnBranchRepository(session)
        recoveries = GlobalTxnRecoveryRepository(session)
        async with DbUnitOfWork(session).begin():
            scope = ConcurrentStableList([caller])
            txn_rows = await txns.list_unsettled(limit=100, caller_services=scope)
            terminal_rows = await txns.list_terminal_before(
                cutoff=NOW + timedelta(days=1), limit=100, caller_services=scope
            )
            branch_rows: ConcurrentStableList[object] = ConcurrentStableList()
            for row in ConcurrentStableList([*txn_rows, *terminal_rows]):
                for branch in await repo_branches.list_by_txn(row.global_txn_id):
                    branch_rows.add(branch)
            recovery_rows = await recoveries.list_before(
                cutoff=NOW + timedelta(days=1), limit=100, caller_services=scope
            )
        return len(txn_rows) + len(terminal_rows), len(branch_rows), len(recovery_rows)
    finally:
        await session.close()


async def test_deletes_expired_terminal_with_branches(ledger: Callable[[], AsyncSession], caller: str) -> None:
    """超期终态：主记录与**其全部分支**一并就地物理删除；台账按 `detected_at` 同批清理。"""
    await _seed(ledger, caller=caller, global_txn_id="g-old", state="committed", age_days=31, recovery_age_days=31)
    metrics = RecordingMetrics()
    cleanup, session = _cleanup(ledger, metrics=metrics)
    try:
        stats = await cleanup.run_once(now=NOW, caller_services=ConcurrentStableList([caller]))
    finally:
        await session.close()

    assert stats == CleanupStats(globals=1, branches=2, recoveries=1)
    assert stats.total == 4  # 1 主记录 + 2 分支 + 1 台账
    assert await _counts(ledger, caller) == (0, 0, 0)
    assert list(metrics.counter_values(METRIC_CLEANED)) == [1.0, 2.0, 1.0]
    assert list(metrics.labels_of(METRIC_CLEANED)) == [{"scope": "global"}, {"scope": "branch"}, {"scope": "recovery"}]


async def test_keeps_recent_and_in_flight(ledger: Callable[[], AsyncSession], caller: str) -> None:
    """未超期终态保留；**非终态（在途）主记录与分支一律不动**（即使已远超保留期）。

    处置台账按**自身** `detected_at` 判定（与父事务是否终态无关）——在途事务的历史台账超期即清。
    """
    await _seed(ledger, caller=caller, global_txn_id="g-recent", state="committed", age_days=1)
    await _seed(ledger, caller=caller, global_txn_id="g-active", state=TXN_ACTIVE, age_days=90, recovery_age_days=90)
    metrics = RecordingMetrics()
    cleanup, session = _cleanup(ledger, metrics=metrics)
    try:
        stats = await cleanup.run_once(now=NOW, caller_services=ConcurrentStableList([caller]))
    finally:
        await session.close()

    assert stats == CleanupStats(globals=0, branches=0, recoveries=1)  # 只清超期台账
    rows, branches, recoveries = await _counts(ledger, caller)
    assert (rows, branches, recoveries) == (2, 4, 0)
    # 计数为 0 的对象不上报（只报台账）
    assert list(metrics.labels_of(METRIC_CLEANED)) == [{"scope": "recovery"}]


async def test_dry_run_counts_without_deleting(ledger: Callable[[], AsyncSession], caller: str) -> None:
    """`--dry-run`：只统计（含将删分支数）不删除。"""
    await _seed(
        ledger, caller=caller, global_txn_id="g-old", state="rolled_back", age_days=45, branches=3, recovery_age_days=45
    )
    cleanup, session = _cleanup(ledger)
    try:
        stats = await cleanup.run_once(now=NOW, dry_run=True, caller_services=ConcurrentStableList([caller]))
    finally:
        await session.close()

    assert stats == CleanupStats(globals=1, branches=3, recoveries=1)
    assert await _counts(ledger, caller) == (1, 3, 1)  # 未删


async def test_batch_limit_bounds_single_round(ledger: Callable[[], AsyncSession], caller: str) -> None:
    """批量上限：单轮最多清理 `batch_limit` 笔（避免长事务）。"""
    for index in range(3):
        await _seed(ledger, caller=caller, global_txn_id=f"g-{index}", state="committed", age_days=31, branches=1)
    cleanup, session = _cleanup(ledger)
    try:
        cleanup = LedgerCleanup(
            GlobalTxnRepository(session),
            GlobalTxnBranchRepository(session),
            GlobalTxnRecoveryRepository(session),
            DbUnitOfWork(session),
            retention_days=RETENTION,
            batch_limit=2,
        )
        stats = await cleanup.run_once(now=NOW, caller_services=ConcurrentStableList([caller]))
    finally:
        await session.close()

    assert stats.globals == 2
    rows, _branches, _recoveries = await _counts(ledger, caller)
    assert rows == 1  # 余 1 笔留待下一轮


async def test_no_metrics_export_is_noop(ledger: Callable[[], AsyncSession], caller: str) -> None:
    """无指标出口（None）时不报错、不上报（缺省部署口径）。"""
    await _seed(ledger, caller=caller, global_txn_id="g-old", state="committed", age_days=31)
    cleanup, session = _cleanup(ledger)
    try:
        stats = await cleanup.run_once(now=NOW, caller_services=ConcurrentStableList([caller]))
    finally:
        await session.close()

    assert stats.globals == 1


async def test_cleanup_uses_current_time_by_default(ledger: Callable[[], AsyncSession], caller: str) -> None:
    """未注入 `now` 时取系统时钟（用例时间远早于当前，故不清理）。"""
    await _seed(ledger, caller=caller, global_txn_id="g-now", state="committed", age_days=1)
    cleanup, session = _cleanup(ledger, retention=3650)
    try:
        stats = await cleanup.run_once(caller_services=ConcurrentStableList([caller]))
    finally:
        await session.close()

    assert stats == CleanupStats()


def test_cleanup_stats_total() -> None:
    """统计值对象：`total` 为三项之和（缺省全 0）。"""
    assert CleanupStats().total == 0
    assert CleanupStats(globals=1, branches=2, recoveries=3).total == 6


async def test_cleanup_command_prints_stats(
    monkeypatch: pytest.MonkeyPatch,
    ledger: Callable[[], AsyncSession],
    capsys: pytest.CaptureFixture[str],
    caller: str,
) -> None:
    """运维子命令：`--dry-run` 输出「将删除」统计（口径同服务内清理）。"""
    from contextlib import AbstractAsyncContextManager

    from bms_core.db.session import DbSession
    from ops import txn_recovery as ops_module

    await _seed(ledger, caller=caller, global_txn_id="g-old", state="committed", age_days=31, branches=2)

    class _Scope:
        """会话作用域替身（yield 账本会话）。"""

        def __init__(self) -> None:
            self._session = ledger()

        async def __aenter__(self) -> DbSession:
            """返回会话。"""
            return self._session

        async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
            """关闭会话。"""
            del exc_type, exc, traceback
            await self._session.close()

    def _scope_factory(*_args: object, **_kwargs: object) -> AbstractAsyncContextManager[DbSession]:
        return _Scope()

    monkeypatch.setattr(ops_module, "session_scope", _scope_factory)
    args = argparse.Namespace(
        retention_days=RETENTION, limit=200, dry_run=True, db_key="platform", caller_service=[caller]
    )

    assert await ops_module._cleanup(args) == 0  # pyright: ignore[reportPrivateUsage]
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "主记录 1 / 分支 2 / 台账 0" in out
    assert await _counts(ledger, caller) == (1, 2, 0)  # dry-run 未删


def test_main_dispatches_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    """入口分派：`cleanup` 子命令走清理实现（返回其退出码）。"""
    from ops import txn_recovery as ops_module

    async def _fake(_args: object) -> int:
        return 0

    monkeypatch.setattr(ops_module, "_cleanup", _fake)
    assert ops_module.main(ConcurrentStableList(["cleanup", "--dry-run"])) == 0
