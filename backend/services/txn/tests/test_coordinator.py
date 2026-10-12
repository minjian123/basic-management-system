"""TM 协调器与恢复器用例（强一致专项 05_07；Kiwi 2271）。

- **提交决定点唯一权威**：决定点前失败一律回滚；决定点后只提交、不再回滚（`rollback` 幂等吸收）；
- 分支状态核验：非全票 `prepared` ⇒ 回滚全部分支（不提交任何分支）；
- 幂等与可重入：重复 `commit` / `rollback` 不改变终态、不重复驱动；
- 恢复器：非终态事务按决定点驱动；**到期未提交** ⇒ 置回滚；**仅 leader** 执行。
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ParamError, TransactionUnavailableError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.lock.memory import MemoryDistributedLock
from bms_core.transaction.base import (
    BRANCH_PREPARED,
    TXN_ACTIVE,
    TXN_COMMITTED,
    TXN_COMMITTING,
    TXN_ROLLED_BACK,
    TXN_ROLLING_BACK,
    BranchSpec,
    build_branch_xid,
)
from bms_txn.models.ledger import GlobalTxn, GlobalTxnBranch, GlobalTxnRecovery
from bms_txn.repositories.ledger import (
    GlobalTxnBranchRepository,
    GlobalTxnRecoveryRepository,
    GlobalTxnRepository,
)
from bms_txn.services.coordinator import TransactionCoordinator
from bms_txn.services.driver import BranchDriver, UnavailableBranchDriver
from bms_txn.services.recovery import TransactionRecovery

pytestmark = [pytest.mark.kiwi_id(2271)]


class FakeDriver(BranchDriver):
    """分支驱动替身：按 `xid` 给出核验结果并记录驱动调用。"""

    def __init__(self, states: ConcurrentStableDict[str, str] | None = None) -> None:
        """初始化。

        Args:
            states: `xid → 核验结果`（缺省全 `prepared`）。
        """
        self.states: ConcurrentStableDict[str, str] = states if states is not None else ConcurrentStableDict[str, str]()
        self.committed: ConcurrentStableList[str] = ConcurrentStableList()
        self.rolled_back: ConcurrentStableList[str] = ConcurrentStableList()

    async def verify(self, *, service: str, db_key: str, xid: str) -> str:
        """核验分支（缺省 `prepared`）。"""
        del service, db_key
        return self.states.get(xid, BRANCH_PREPARED)

    async def commit(self, *, service: str, db_key: str, xid: str) -> str:
        """提交分支并记录。"""
        del service, db_key
        self.committed.add(xid)
        return "committed"

    async def rollback(self, *, service: str, db_key: str, xid: str) -> str:
        """回滚分支并记录。"""
        del service, db_key
        self.rolled_back.add(xid)
        return "rolled_back"


@pytest.fixture
async def uow() -> AsyncIterator[DbUnitOfWork]:
    """内存 SQLite 工作单元（建账本三表）。

    Yields:
        DbUnitOfWork: 工作单元。
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as connection:
        tables: tuple[Table, ...] = (
            cast("Table", GlobalTxn.__table__),
            cast("Table", GlobalTxnBranch.__table__),
            cast("Table", GlobalTxnRecovery.__table__),
        )
        for table in tables:
            await connection.run_sync(table.create, checkfirst=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    try:
        yield DbUnitOfWork(session)
    finally:
        await session.close()
        await engine.dispose()


def _coordinator(uow: DbUnitOfWork, driver: BranchDriver) -> TransactionCoordinator:
    """按给定工作单元与驱动构造协调器。"""
    return TransactionCoordinator(
        GlobalTxnRepository(uow.session),
        GlobalTxnBranchRepository(uow.session),
        uow,
        driver,
        deadline_seconds=300.0,
    )


def _specs() -> tuple[BranchSpec, ...]:
    """两个分支声明（平台库 + 租户库）。"""
    return (
        BranchSpec(branch_id="p1", service="platform", db_key="platform"),
        BranchSpec(branch_id="m1", service="org", db_key="tenant_demo"),
    )


async def test_begin_allocates_xids_and_activates(uow: DbUnitOfWork) -> None:
    """开启：落账本 `active`、分配分支 `xid`（`gtrid|bqual`）、返回快照。"""
    coordinator = _coordinator(uow, FakeDriver())
    snapshot = await coordinator.begin(caller_service="platform", branches=_specs())

    assert snapshot.state == TXN_ACTIVE
    assert snapshot.caller_service == "platform"
    assert [ref.branch_id for ref in snapshot.branches] == ["p1", "m1"]
    assert snapshot.branches[0].xid == build_branch_xid(snapshot.global_txn_id, "p1")
    assert snapshot.branches[0].state == "active"


async def test_begin_rejects_duplicate_branch(uow: DbUnitOfWork) -> None:
    """开启：分支标识重复即拒（`10001`）；空分支清单即拒。"""
    coordinator = _coordinator(uow, FakeDriver())
    duplicated = (
        BranchSpec(branch_id="p1", service="platform", db_key="platform"),
        BranchSpec(branch_id="p1", service="org", db_key="tenant_demo"),
    )
    with pytest.raises(ParamError):
        await coordinator.begin(caller_service="platform", branches=duplicated)
    with pytest.raises(ParamError):
        await coordinator.begin(caller_service="platform", branches=())


async def test_commit_all_prepared_commits_every_branch(uow: DbUnitOfWork) -> None:
    """决定点：全票 `prepared` ⇒ 落 `committing` 并逐分支提交至 `committed`。"""
    driver = FakeDriver()
    coordinator = _coordinator(uow, driver)
    started = await coordinator.begin(caller_service="platform", branches=_specs())

    result = await coordinator.commit(started.global_txn_id)

    assert result.state == TXN_COMMITTED
    assert result.decided_at is not None
    assert sorted(driver.committed) == sorted(ref.xid for ref in started.branches)
    assert driver.rolled_back == []


async def test_commit_rejects_when_a_branch_not_prepared(uow: DbUnitOfWork) -> None:
    """决定点前：任一分支未 `prepared` ⇒ 全部分支回滚、**无任何提交**。"""
    driver = FakeDriver()
    coordinator = _coordinator(uow, driver)
    started = await coordinator.begin(caller_service="platform", branches=_specs())
    driver.states.set(started.branches[1].xid, "rejected")

    result = await coordinator.commit(started.global_txn_id)

    assert result.state == TXN_ROLLED_BACK
    assert result.decided_at is None
    assert driver.committed == []
    assert sorted(driver.rolled_back) == sorted(ref.xid for ref in started.branches)


async def test_rollback_before_decision_rolls_back(uow: DbUnitOfWork) -> None:
    """决定点前主动回滚：全部分支回滚至 `rolled_back`。"""
    driver = FakeDriver()
    coordinator = _coordinator(uow, driver)
    started = await coordinator.begin(caller_service="platform", branches=_specs())

    result = await coordinator.rollback(started.global_txn_id)

    assert result.state == TXN_ROLLED_BACK
    assert sorted(driver.rolled_back) == sorted(ref.xid for ref in started.branches)
    assert driver.committed == []


async def test_rollback_after_decision_is_absorbed(uow: DbUnitOfWork) -> None:
    """决定点之后回滚请求**被幂等吸收**：只提交、不再回滚。"""
    driver = FakeDriver()
    coordinator = _coordinator(uow, driver)
    started = await coordinator.begin(caller_service="platform", branches=_specs())
    await coordinator.commit(started.global_txn_id)
    driver.committed.clear()

    result = await coordinator.rollback(started.global_txn_id)

    assert result.state == TXN_COMMITTED
    assert driver.rolled_back == []


async def test_commit_and_rollback_are_idempotent(uow: DbUnitOfWork) -> None:
    """终态后重复驱动不改变终态、不重复提交。"""
    driver = FakeDriver()
    coordinator = _coordinator(uow, driver)
    started = await coordinator.begin(caller_service="platform", branches=_specs())
    await coordinator.commit(started.global_txn_id)
    driver.committed.clear()

    again = await coordinator.commit(started.global_txn_id)

    assert again.state == TXN_COMMITTED
    assert driver.committed == []


async def test_status_unknown_transaction_rejected(uow: DbUnitOfWork) -> None:
    """未知全局事务查询即拒（`10001`）。"""
    coordinator = _coordinator(uow, FakeDriver())
    with pytest.raises(ParamError):
        await coordinator.status("not-exists")


async def test_driver_failure_keeps_draft_and_marks_error(uow: DbUnitOfWork) -> None:
    """驱动失败：分支保持未确认并记录失败原因与重试次数（由恢复器重驱动）。"""

    class FailingDriver(FakeDriver):
        """提交恒定失败的驱动替身。"""

        async def commit(self, *, service: str, db_key: str, xid: str) -> str:
            """恒定抛错（模拟参与方不可达）。"""
            del service, db_key, xid
            raise RuntimeError("参与方不可达")

    driver = FailingDriver()
    coordinator = _coordinator(uow, driver)
    started = await coordinator.begin(caller_service="platform", branches=_specs())

    result = await coordinator.commit(started.global_txn_id)

    assert result.state == TXN_COMMITTED
    assert all(ref.state != "committed" for ref in result.branches)
    branches = GlobalTxnBranchRepository(uow.session)
    async with uow.begin():
        rows = await branches.list_by_txn(started.global_txn_id)
    assert all(row.retry_count == 1 for row in rows)
    assert all(row.last_error == "参与方不可达" for row in rows)


async def test_unavailable_driver_rejects_explicitly() -> None:
    """缺省驱动**明确拒绝**（不静默成功）。"""
    driver = UnavailableBranchDriver()
    with pytest.raises(TransactionUnavailableError):
        await driver.commit(service="platform", db_key="platform", xid="x1")


async def test_recovery_drives_committing_transaction(uow: DbUnitOfWork) -> None:
    """恢复器：`committing` 事务被驱动至 `committed`（决定点后只提交）。"""
    driver = FakeDriver()
    coordinator = _coordinator(uow, driver)
    started = await coordinator.begin(caller_service="platform", branches=_specs())
    # 人为把账本置为 committing（模拟「决定点已落、驱动中断」）
    txns = GlobalTxnRepository(uow.session)
    async with uow.begin():
        row = await txns.get_by_global_txn_id(started.global_txn_id)
        assert row is not None
        row.state = "committing"
        row.decided_at = datetime.now(UTC)
        await txns.flush()

    recovery = _recovery(uow, coordinator)
    handled = await recovery.run_once()

    assert handled == 1
    assert (await coordinator.status(started.global_txn_id)).state == TXN_COMMITTED
    assert sorted(driver.committed) == sorted(ref.xid for ref in started.branches)
    async with uow.begin():
        logs = await GlobalTxnRecoveryRepository(uow.session).list_recent()
    assert [log.action for log in logs] == ["drive_commit"]


async def test_recovery_rolls_back_expired_transaction(uow: DbUnitOfWork) -> None:
    """恢复器：**到期未提交**的 `active` 事务 ⇒ 置回滚（详设 §6）。"""
    driver = FakeDriver()
    coordinator = _coordinator(uow, driver)
    started = await coordinator.begin(caller_service="platform", branches=_specs())
    txns = GlobalTxnRepository(uow.session)
    async with uow.begin():
        row = await txns.get_by_global_txn_id(started.global_txn_id)
        assert row is not None
        row.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
        await txns.flush()

    recovery = _recovery(uow, coordinator)
    await recovery.run_once()

    assert (await coordinator.status(started.global_txn_id)).state == TXN_ROLLED_BACK
    assert driver.committed == []


async def test_recovery_requires_leadership(uow: DbUnitOfWork) -> None:
    """恢复器单飞：非 leader（锁已被占用）不执行扫描。"""
    driver = FakeDriver()
    coordinator = _coordinator(uow, driver)
    await coordinator.begin(caller_service="platform", branches=_specs())

    lock = MemoryDistributedLock()
    token = await lock.acquire("bms:global:lock:txn:leader", ttl=30, wait=0)
    assert token is not None
    recovery = _recovery(uow, coordinator, lock=lock)

    assert await recovery.run_as_leader() == 0
    await lock.release("bms:global:lock:txn:leader", token)


async def test_recovery_as_leader_executes_scan(uow: DbUnitOfWork) -> None:
    """取得 leader 身份（锁空闲）时执行单轮扫描；无在途事务返回 0。"""
    assert await _recovery(uow, _coordinator(uow, FakeDriver())).is_leader() is True
    assert await _recovery(uow, _coordinator(uow, FakeDriver())).run_as_leader() == 0


async def test_recovery_rolls_back_rolling_back_transaction(uow: DbUnitOfWork) -> None:
    """决定点前的 `rolling_back` 事务：未到期仍驱动回滚（续行至终态）。"""
    driver = FakeDriver()
    coordinator = _coordinator(uow, driver)
    started = await coordinator.begin(caller_service="platform", branches=_specs())
    txns = GlobalTxnRepository(uow.session)
    async with uow.begin():
        row = await txns.get_by_global_txn_id(started.global_txn_id)
        assert row is not None
        row.state = TXN_ROLLING_BACK
        row.deadline_at = datetime.now(UTC) + timedelta(seconds=300)
        await txns.flush()

    recovery = _recovery(uow, coordinator)

    assert await recovery.run_once() == 1
    assert (await coordinator.status(started.global_txn_id)).state == TXN_ROLLED_BACK
    assert driver.committed == []


async def test_recovery_skips_unknown_state_row(uow: DbUnitOfWork, monkeypatch: pytest.MonkeyPatch) -> None:
    """非终态查询返回协议外状态行：跳过不驱动；已终态行亦被过滤。"""
    driver = FakeDriver()
    coordinator = _coordinator(uow, driver)
    unknown = await coordinator.begin(caller_service="platform", branches=_specs())
    terminal = await coordinator.begin(caller_service="platform", branches=_specs())

    async def _rows(self: GlobalTxnRepository, *, limit: int = 200) -> ConcurrentStableList[GlobalTxn]:
        del limit
        rows: ConcurrentStableList[GlobalTxn] = ConcurrentStableList()
        unknown_row = await self.get_by_global_txn_id(unknown.global_txn_id)
        assert unknown_row is not None
        unknown_row.deadline_at = datetime.now(UTC) + timedelta(seconds=300)
        unknown_row.state = "protocol_unknown"
        rows.add(unknown_row)
        terminal_row = await self.get_by_global_txn_id(terminal.global_txn_id)
        assert terminal_row is not None
        terminal_row.state = TXN_COMMITTED
        rows.add(terminal_row)
        return rows

    monkeypatch.setattr(GlobalTxnRepository, "list_unsettled", _rows)
    recovery = _recovery(uow, coordinator)

    assert await recovery.run_once() == 0
    assert driver.committed == [] and driver.rolled_back == []


async def test_recovery_record_tolerates_missing_transaction(uow: DbUnitOfWork) -> None:
    """处置台账落库：事务记录缺失时结论为「事务记录缺失」（不阻断台账写入）。"""
    recovery = _recovery(uow, _coordinator(uow, FakeDriver()))

    await recovery._record("missing-txn", None, "drive_commit", datetime.now(UTC))  # pyright: ignore[reportPrivateUsage]

    async with uow.begin():
        logs = await GlobalTxnRecoveryRepository(uow.session).list_recent()
    assert [log.conclusion for log in logs] == ["事务记录缺失"]


class FailingVerifyDriver(FakeDriver):
    """核验恒定失败的驱动替身（模拟参与方不可达）。"""

    async def verify(self, *, service: str, db_key: str, xid: str) -> str:
        """恒定抛错。"""
        del service, db_key, xid
        raise RuntimeError("核验不可达")


async def test_verify_failure_rolls_back_and_records_error(uow: DbUnitOfWork) -> None:
    """决定点前核验失败：按否决处理（记失败原因）⇒ 全部分支回滚、无任何提交。"""
    driver = FailingVerifyDriver()
    coordinator = _coordinator(uow, driver)
    started = await coordinator.begin(caller_service="platform", branches=_specs())

    result = await coordinator.commit(started.global_txn_id)

    assert result.state == TXN_ROLLED_BACK
    assert driver.committed == []
    branches = GlobalTxnBranchRepository(uow.session)
    async with uow.begin():
        rows = await branches.list_by_txn(started.global_txn_id)
    assert all(row.retry_count == 1 for row in rows)
    assert all(row.last_error == "核验不可达" for row in rows)


async def test_rollback_in_committing_state_is_absorbed(uow: DbUnitOfWork) -> None:
    """决定点已落（`committing`）时的回滚请求：只提交、不再回滚（幂等吸收）。"""
    driver = FakeDriver()
    coordinator = _coordinator(uow, driver)
    started = await coordinator.begin(caller_service="platform", branches=_specs())
    txns = GlobalTxnRepository(uow.session)
    async with uow.begin():
        row = await txns.get_by_global_txn_id(started.global_txn_id)
        assert row is not None
        row.state = TXN_COMMITTING
        row.decided_at = datetime.now(UTC)
        await txns.flush()

    result = await coordinator.rollback(started.global_txn_id)

    assert result.state == TXN_COMMITTED
    assert driver.rolled_back == []


async def test_internal_helpers_edge_cases(uow: DbUnitOfWork) -> None:
    """内部辅助：事务缺失即拒；终态不再决定；分支缺失 / 同态跳过；驱动跳过已终态分支。"""
    coordinator = _coordinator(uow, FakeDriver())

    with pytest.raises(ParamError):
        await coordinator.commit("not-exists")

    started = await coordinator.begin(caller_service="platform", branches=_specs())
    gid = started.global_txn_id
    await coordinator.commit(gid)

    with pytest.raises(ParamError):
        await coordinator._decide("not-exists", TXN_COMMITTING)  # pyright: ignore[reportPrivateUsage]
    await coordinator._decide(gid, TXN_COMMITTING)  # pyright: ignore[reportPrivateUsage] - 终态：直接返回
    await coordinator._set_branch_state(gid, "missing", BRANCH_PREPARED)  # pyright: ignore[reportPrivateUsage]
    await coordinator._set_branch_state(gid, "p1", "committed")  # pyright: ignore[reportPrivateUsage] - 同态跳过
    await coordinator._record_branch_error(gid, "missing", "x")  # pyright: ignore[reportPrivateUsage]
    await coordinator._drive(gid, commit=True)  # pyright: ignore[reportPrivateUsage] - 全部分支已终态：跳过
    assert (await coordinator.status(gid)).state == TXN_COMMITTED


async def test_ledger_repository_queries(uow: DbUnitOfWork) -> None:
    """账本仓储：启发式终态 / 到期 `active` / 未确认分支 / 处置台账落库。"""
    coordinator = _coordinator(uow, FakeDriver())
    heuristic = await coordinator.begin(caller_service="platform", branches=_specs())
    expired = await coordinator.begin(caller_service="platform", branches=_specs())

    txns = GlobalTxnRepository(uow.session)
    branches = GlobalTxnBranchRepository(uow.session)
    recoveries = GlobalTxnRecoveryRepository(uow.session)

    async with uow.begin():
        heuristic_row = await txns.get_by_global_txn_id(heuristic.global_txn_id)
        assert heuristic_row is not None
        heuristic_row.state = "heuristic_commit"
        expired_row = await txns.get_by_global_txn_id(expired.global_txn_id)
        assert expired_row is not None
        expired_row.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
        await txns.flush()
        await recoveries.flush()

    async with uow.begin():
        heuristic_rows = await txns.list_heuristic()
        expired_rows = await txns.list_expired_active(now=datetime.now(UTC))
        unsettled = await branches.list_unsettled()
    assert [item.global_txn_id for item in heuristic_rows] == [heuristic.global_txn_id]
    assert [item.global_txn_id for item in expired_rows] == [expired.global_txn_id]
    assert [item.branch_id for item in unsettled] == ["p1", "m1", "p1", "m1"]


def _recovery(uow: DbUnitOfWork, coordinator: TransactionCoordinator, *, lock: Any = None) -> TransactionRecovery:
    """构造恢复器（缺省内存锁）。"""
    return TransactionRecovery(
        coordinator,
        GlobalTxnRepository(uow.session),
        GlobalTxnBranchRepository(uow.session),
        GlobalTxnRecoveryRepository(uow.session),
        uow,
        lock if lock is not None else MemoryDistributedLock(),
        leader_lock_key="bms:global:lock:txn:leader",
    )
