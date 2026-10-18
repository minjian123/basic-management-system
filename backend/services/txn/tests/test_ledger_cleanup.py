"""账本保留期清理用例（强一致专项 05_07；Kiwi 2271；详设 §3.5）。

覆盖：超期终态删除（主记录 + 分支级联）/ 未超期保留 / **非终态一律不动** / 台账超期删除 /
批量上限 / `--dry-run` 只统计不删 / 指标上报 / 子命令入口与分派。
"""

from __future__ import annotations

import argparse
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from sqlalchemy import Table, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.transaction.base import TXN_ACTIVE
from bms_txn.models.ledger import GlobalTxn, GlobalTxnBranch, GlobalTxnRecovery
from bms_txn.repositories.ledger import (
    GlobalTxnBranchRepository,
    GlobalTxnRecoveryRepository,
    GlobalTxnRepository,
)
from bms_txn.services.ledger_cleanup import METRIC_CLEANED, CleanupStats, LedgerCleanup
from tests_support.metrics import RecordingMetrics

pytestmark = [pytest.mark.kiwi_id(2271)]

SessionMaker = async_sessionmaker[AsyncSession]
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
"""固定「当前时间」（用例注入，避免依赖真实时钟）。"""

RETENTION = 30
"""保留期（天）。"""


class _LedgerEngine:
    """内存 SQLite 账本（进入建三表、退出释放引擎）。"""

    def __init__(self) -> None:
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )

    async def __aenter__(self) -> SessionMaker:
        """建表并返回会话工厂。"""
        async with self.engine.begin() as connection:
            for model in (GlobalTxn, GlobalTxnBranch, GlobalTxnRecovery):
                await connection.run_sync(cast("Table", model.__table__).create, checkfirst=True)
        return async_sessionmaker(self.engine, expire_on_commit=False)

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """释放引擎。"""
        del exc_type, exc, traceback
        await self.engine.dispose()


@pytest.fixture
async def ledger() -> AsyncIterator[SessionMaker]:
    """账本会话工厂（内存 SQLite，三表）。"""
    async with _LedgerEngine() as factory:
        yield factory


def _cleanup(
    factory: SessionMaker, *, retention: int = RETENTION, metrics: RecordingMetrics | None = None
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
    factory: SessionMaker,
    *,
    global_txn_id: str,
    state: str,
    age_days: int,
    branches: int = 2,
    recovery_age_days: int | None = None,
) -> None:
    """造一条全局事务（含分支）与可选处置台账；`age_days` 为「距今多少天」。"""
    session = factory()
    uow = DbUnitOfWork(session)
    txns = GlobalTxnRepository(session)
    repo_branches = GlobalTxnBranchRepository(session)
    recoveries = GlobalTxnRecoveryRepository(session)
    stamp = NOW - timedelta(days=age_days)
    async with uow.begin():
        row = await txns.create(
            global_txn_id=global_txn_id,
            caller_service="platform",
            state=state,
            deadline_at=stamp,
            decided_at=None,
        )
        row.updated_at = stamp
        for index in range(branches):
            branch = await repo_branches.create(
                global_txn_id=global_txn_id,
                branch_id=f"b{index}",
                service="platform",
                db_key="platform",
                xid=f"{global_txn_id}|b{index}",
                state="committed",
            )
            branch.updated_at = stamp
        if recovery_age_days is not None:
            await recoveries.create(
                global_txn_id=global_txn_id,
                branch_id=None,
                detected_at=NOW - timedelta(days=recovery_age_days),
                hung_seconds=None,
                action="drive_commit",
                actor="recoverer",
                handler=None,
                conclusion="ok",
            )
        await txns.flush()
        # `updated_at` 由 ORM 事件在写入时置为真实时钟 ⇒ 用裸 SQL 回填「距今 N 天」（绕开事件）
        await session.execute(
            text("UPDATE txn_global SET updated_at = :stamp WHERE global_txn_id = :gid"),
            {"stamp": stamp.replace(tzinfo=None), "gid": global_txn_id},
        )
        await session.execute(
            text("UPDATE txn_global_branch SET updated_at = :stamp WHERE global_txn_id = :gid"),
            {"stamp": stamp.replace(tzinfo=None), "gid": global_txn_id},
        )
    await session.close()


async def _counts(factory: SessionMaker) -> tuple[int, int, int]:
    """取三表行数（主记录 / 分支 / 台账）。"""
    session = factory()
    try:
        txns = GlobalTxnRepository(session)
        repo_branches = GlobalTxnBranchRepository(session)
        recoveries = GlobalTxnRecoveryRepository(session)
        async with DbUnitOfWork(session).begin():
            txn_rows = await txns.list_unsettled(limit=100)
            terminal_rows = await txns.list_terminal_before(cutoff=NOW + timedelta(days=1), limit=100)
            branch_rows: ConcurrentStableList[object] = ConcurrentStableList()
            for row in ConcurrentStableList([*txn_rows, *terminal_rows]):
                for branch in await repo_branches.list_by_txn(row.global_txn_id):
                    branch_rows.add(branch)
            recovery_rows = await recoveries.list_before(cutoff=NOW + timedelta(days=1), limit=100)
        return len(txn_rows) + len(terminal_rows), len(branch_rows), len(recovery_rows)
    finally:
        await session.close()


async def test_deletes_expired_terminal_with_branches(ledger: SessionMaker) -> None:
    """超期终态：主记录与**其全部分支**一并就地物理删除；台账按 `detected_at` 同批清理。"""
    await _seed(ledger, global_txn_id="g-old", state="committed", age_days=31, recovery_age_days=31)
    metrics = RecordingMetrics()
    cleanup, session = _cleanup(ledger, metrics=metrics)
    try:
        stats = await cleanup.run_once(now=NOW)
    finally:
        await session.close()

    assert stats == CleanupStats(globals=1, branches=2, recoveries=1)
    assert stats.total == 4  # 1 主记录 + 2 分支 + 1 台账
    assert await _counts(ledger) == (0, 0, 0)
    assert list(metrics.counter_values(METRIC_CLEANED)) == [1.0, 2.0, 1.0]
    assert list(metrics.labels_of(METRIC_CLEANED)) == [{"scope": "global"}, {"scope": "branch"}, {"scope": "recovery"}]


async def test_keeps_recent_and_in_flight(ledger: SessionMaker) -> None:
    """未超期终态保留；**非终态（在途）主记录与分支一律不动**（即使已远超保留期）。

    处置台账按**自身** `detected_at` 判定（与父事务是否终态无关）——在途事务的历史台账超期即清。
    """
    await _seed(ledger, global_txn_id="g-recent", state="committed", age_days=1)
    await _seed(ledger, global_txn_id="g-active", state=TXN_ACTIVE, age_days=90, recovery_age_days=90)
    metrics = RecordingMetrics()
    cleanup, session = _cleanup(ledger, metrics=metrics)
    try:
        stats = await cleanup.run_once(now=NOW)
    finally:
        await session.close()

    assert stats == CleanupStats(globals=0, branches=0, recoveries=1)  # 只清超期台账
    rows, branches, recoveries = await _counts(ledger)
    assert (rows, branches, recoveries) == (2, 4, 0)
    # 计数为 0 的对象不上报（只报台账）
    assert list(metrics.labels_of(METRIC_CLEANED)) == [{"scope": "recovery"}]


async def test_dry_run_counts_without_deleting(ledger: SessionMaker) -> None:
    """`--dry-run`：只统计（含将删分支数）不删除。"""
    await _seed(ledger, global_txn_id="g-old", state="rolled_back", age_days=45, branches=3, recovery_age_days=45)
    cleanup, session = _cleanup(ledger)
    try:
        stats = await cleanup.run_once(now=NOW, dry_run=True)
    finally:
        await session.close()

    assert stats == CleanupStats(globals=1, branches=3, recoveries=1)
    assert await _counts(ledger) == (1, 3, 1)  # 未删


async def test_batch_limit_bounds_single_round(ledger: SessionMaker) -> None:
    """批量上限：单轮最多清理 `batch_limit` 笔（避免长事务）。"""
    for index in range(3):
        await _seed(ledger, global_txn_id=f"g-{index}", state="committed", age_days=31, branches=1)
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
        stats = await cleanup.run_once(now=NOW)
    finally:
        await session.close()

    assert stats.globals == 2
    rows, _branches, _recoveries = await _counts(ledger)
    assert rows == 1  # 余 1 笔留待下一轮


async def test_no_metrics_export_is_noop(ledger: SessionMaker) -> None:
    """无指标出口（None）时不报错、不上报（缺省部署口径）。"""
    await _seed(ledger, global_txn_id="g-old", state="committed", age_days=31)
    cleanup, session = _cleanup(ledger)
    try:
        stats = await cleanup.run_once(now=NOW)
    finally:
        await session.close()

    assert stats.globals == 1


async def test_cleanup_uses_current_time_by_default(ledger: SessionMaker) -> None:
    """未注入 `now` 时取系统时钟（用例时间远早于当前，故不清理）。"""
    await _seed(ledger, global_txn_id="g-now", state="committed", age_days=1)
    cleanup, session = _cleanup(ledger, retention=3650)
    try:
        stats = await cleanup.run_once()
    finally:
        await session.close()

    assert stats == CleanupStats()


def test_cleanup_stats_total() -> None:
    """统计值对象：`total` 为三项之和（缺省全 0）。"""
    assert CleanupStats().total == 0
    assert CleanupStats(globals=1, branches=2, recoveries=3).total == 6


async def test_cleanup_command_prints_stats(
    monkeypatch: pytest.MonkeyPatch, ledger: SessionMaker, capsys: pytest.CaptureFixture[str]
) -> None:
    """运维子命令：`--dry-run` 输出「将删除」统计（口径同服务内清理）。"""
    from contextlib import AbstractAsyncContextManager

    from bms_core.db.session import DbSession
    from ops import txn_recovery as ops_module

    await _seed(ledger, global_txn_id="g-old", state="committed", age_days=31, branches=2)

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
    args = argparse.Namespace(retention_days=RETENTION, limit=200, dry_run=True, db_key="platform")

    assert await ops_module._cleanup(args) == 0  # pyright: ignore[reportPrivateUsage]
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "主记录 1 / 分支 2 / 台账 0" in out
    assert await _counts(ledger) == (1, 2, 0)  # dry-run 未删


def test_main_dispatches_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    """入口分派：`cleanup` 子命令走清理实现（返回其退出码）。"""
    from ops import txn_recovery as ops_module

    async def _fake(_args: object) -> int:
        return 0

    monkeypatch.setattr(ops_module, "_cleanup", _fake)
    assert ops_module.main(ConcurrentStableList(["cleanup", "--dry-run"])) == 0
