"""TM 端到端真库用例（强一致专项 05_07；Kiwi 2271；标记 `integration` + `dialect_*`）。

**真 XA 分支执行器**（`XaTransactionParticipant`，分支专用同步引擎，覆盖 MySQL / PostgreSQL）+ **TM 协调器**
（真实账本）+ 崩溃注入 + 幂等重放——详设 §7「跨服务 2PC」与「崩溃注入（决定点前 / 后）」的可自动化形态：

- **全票提交**：两库分支均 `prepared` ⇒ 决定点后全员 `XA_COMMIT` 生效（两库可见同一业务写入）；
- **单分支否决**：任一分支未 `prepared`（载荷 `op` 未登记）⇒ 全量回滚，**两侧无变更**；
- **崩溃注入（决定点前）**：账本置 `preparing` + 两库悬挂分支 ⇒ 恢复器驱动**全量回滚**；
- **崩溃注入（决定点后）**：账本置 `committing`（决定点已落）+ 两库悬挂分支 ⇒ 恢复器驱动**全量提交**；
- **幂等重放**：重复驱动不改变终态、不重复提交（已确认分支按账本状态跳过）。

未配置 `BMS_TEST_MYSQL_URL` / `BMS_TEST_PG_URL`（任一）即跳过；探针表用例内建删，失败路径先清悬挂分支。
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from sqlalchemy import Engine, Table, create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.db.engine import _normalize_dialect_url  # pyright: ignore[reportPrivateUsage]
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.transaction.base import (
    BRANCH_PREPARED,
    TXN_COMMITTING,
    TXN_PREPARING,
    BranchHandlerRegistry,
    BranchOp,
    BranchSpec,
)
from bms_core.transaction.xa import XaTransactionParticipant
from bms_txn.domains.txn.models.ledger import GlobalTxn, GlobalTxnBranch, GlobalTxnRecovery
from bms_txn.domains.txn.repositories.ledger import (
    GlobalTxnBranchRepository,
    GlobalTxnRecoveryRepository,
    GlobalTxnRepository,
)
from bms_txn.domains.txn.services.coordinator import TransactionCoordinator
from bms_txn.domains.txn.services.driver import BranchDriver
from bms_txn.domains.txn.services.recovery import TransactionRecovery

pytestmark = [pytest.mark.integration, pytest.mark.kiwi_id(2271)]

_PROBE_TABLE = "bms_it_tm_probe"
"""跨服务两阶段探针表（两库各建删一次；用例内建删）。"""

_OP_INSERT = "it.probe.insert"
"""已登记的分支 `op`：写入探针行。"""

_DB_MYSQL = "mysql"
_DB_PG = "pg"

SessionMaker = async_sessionmaker[AsyncSession]


class _SyncEngines:
    """同步引擎提供者替身：按不透明库键取真库同步引擎（`SyncEngineProvider` 结构契约）。"""

    def __init__(self, mapping: ConcurrentStableDict[str, Engine]) -> None:
        """初始化。

        Args:
            mapping: 库键 → 同步引擎。
        """
        self._mapping = mapping

    async def get_sync(self, db_key: str = "platform", *, read_only: bool = False) -> Engine:
        """取同步引擎。

        Args:
            db_key: 库键（本用例即方言键 `mysql` / `pg`）。
            read_only: 只读标记（本用例不使用）。

        Returns:
            Engine: 真库同步引擎。
        """
        del read_only
        return self._mapping[db_key]


class _InProcessBranchDriver(BranchDriver):
    """TM 分支驱动：**进程内**直连参与方（同一套分支执行器，不经 HTTP），并记录驱动次数。"""

    def __init__(self, participant: XaTransactionParticipant) -> None:
        """初始化。

        Args:
            participant: 参与方分支执行器（真库 XA）。
        """
        self._participant = participant
        self.committed: ConcurrentStableList[str] = ConcurrentStableList()
        self.rolled_back: ConcurrentStableList[str] = ConcurrentStableList()

    async def verify(self, *, service: str, db_key: str, xid: str) -> str:
        """核验分支状态（数据库侧悬挂列举为准）。"""
        del service
        return await self._participant.branch_state(xid=xid, db_key=db_key)

    async def commit(self, *, service: str, db_key: str, xid: str) -> str:
        """提交分支（`XA_COMMIT`）。"""
        del service
        self.committed.add(xid)
        return await self._participant.commit_branch(xid=xid, db_key=db_key)

    async def rollback(self, *, service: str, db_key: str, xid: str) -> str:
        """回滚分支（`XA_ROLLBACK`）。"""
        del service
        self.rolled_back.add(xid)
        return await self._participant.rollback_branch(xid=xid, db_key=db_key)


async def _insert_handler(session: object, args: ConcurrentStableDict[str, object]) -> None:
    """分支业务处理器：把载荷写进**本分支连接所在库**的探针表（只调服务层口径：单条 INSERT）。

    Args:
        session: 分支会话（绑定该分支两阶段事务的连接）。
        args: 分支载荷（`id` / `note`）。
    """
    statement = text(f"INSERT INTO {_PROBE_TABLE} (id, note) VALUES (:i, :n)")
    await cast("Any", session).execute(statement, {"i": int(cast("int", args["id"])), "n": str(args["note"])})


def _probe_specs() -> ConcurrentStableList[BranchSpec]:
    """两分支声明（不透明库键 `mysql` / `pg`）。"""
    return ConcurrentStableList(
        (
            BranchSpec(branch_id="mysql-branch", service="platform", db_key=_DB_MYSQL),
            BranchSpec(branch_id="pg-branch", service="org", db_key=_DB_PG),
        )
    )


def _payload(note: str, probe_id: int) -> ConcurrentStableFrozenDict[str, object]:
    """分支载荷（写哪一行、写什么）。"""
    return ConcurrentStableFrozenDict[str, object]({"id": probe_id, "note": note})


def _create_probe(engine: Engine) -> None:
    """建探针表（幂等；顺带把元数据锁等待收敛为 60s——悬挂分支在场时把卡死降级为可诊断失败）。"""
    with engine.begin() as connection:
        if engine.dialect.name in ("mysql",):
            connection.execute(text("SET SESSION lock_wait_timeout = 60"))
        connection.execute(text(f"DROP TABLE IF EXISTS {_PROBE_TABLE}"))
        connection.execute(text(f"CREATE TABLE {_PROBE_TABLE} (id INT PRIMARY KEY, note VARCHAR(64))"))


def _drop_probe(engine: Engine) -> None:
    """删探针表（幂等）。"""
    with engine.begin() as connection:
        if engine.dialect.name in ("mysql",):
            connection.execute(text("SET SESSION lock_wait_timeout = 60"))
        connection.execute(text(f"DROP TABLE IF EXISTS {_PROBE_TABLE}"))


def _notes(engine: Engine) -> ConcurrentStableList[str]:
    """读探针表全部 `note`（按 id 升序）。"""
    with engine.connect() as connection:
        rows = connection.execute(text(f"SELECT note FROM {_PROBE_TABLE} ORDER BY id")).fetchall()
    return ConcurrentStableList(str(row[0]) for row in rows)


@pytest.fixture(scope="module")
def db_urls() -> Iterator[ConcurrentStableDict[str, str]]:
    """两库同步连接串（任一未配置即跳过整个模块）。"""
    required = {_DB_MYSQL: "BMS_TEST_MYSQL_URL", _DB_PG: "BMS_TEST_PG_URL"}
    missing = [env for env in required.values() if not os.environ.get(env)]
    if missing:
        pytest.skip(f"未配置 {' / '.join(missing)}，跳过 TM 端到端真库用例")
    urls: ConcurrentStableDict[str, str] = ConcurrentStableDict({key: os.environ[env] for key, env in required.items()})
    yield urls


@pytest.fixture(scope="module")
def engines(db_urls: ConcurrentStableDict[str, str]) -> Iterator[ConcurrentStableDict[str, Engine]]:
    """两库同步引擎（用例模块内共用；结束释放）。"""
    built: ConcurrentStableDict[str, Engine] = ConcurrentStableDict(
        {key: create_engine(_normalize_dialect_url(url)) for key, url in db_urls.items()}
    )
    yield built
    for engine in built.values():
        engine.dispose()


@pytest.fixture
def probes(engines: ConcurrentStableDict[str, Engine]) -> Iterator[ConcurrentStableDict[str, Engine]]:
    """每例重建探针表（失败路径先清理，避免悬挂分支挡住删表）。"""
    for engine in engines.values():
        _create_probe(engine)
    yield engines
    for engine in engines.values():
        _drop_probe(engine)


@pytest.fixture
async def uow() -> AsyncIterator[DbUnitOfWork]:
    """TM 账本工作单元（内存 SQLite；**分支**才是真库——账本与业务分支物理分离，详设 §4）。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as connection:
        for model in (GlobalTxn, GlobalTxnBranch, GlobalTxnRecovery):
            await connection.run_sync(cast("Table", model.__table__).create, checkfirst=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    try:
        yield DbUnitOfWork(session)
    finally:
        await session.close()
        await engine.dispose()


@pytest.fixture
def participant(engines: ConcurrentStableDict[str, Engine]) -> XaTransactionParticipant:
    """参与方：真库分支执行器（登记写入 `op`）。"""
    registry = BranchHandlerRegistry()
    registry.register(_OP_INSERT, _insert_handler)
    return XaTransactionParticipant(cast("Any", _SyncEngines(engines)), registry)


def _coordinator(uow: DbUnitOfWork, driver: BranchDriver) -> TransactionCoordinator:
    """按账本工作单元与驱动构造协调器。"""
    return TransactionCoordinator(
        GlobalTxnRepository(uow.session),
        GlobalTxnBranchRepository(uow.session),
        uow,
        driver,
        deadline_seconds=300.0,
    )


async def _prepare_all(
    participant: XaTransactionParticipant,
    specs: ConcurrentStableList[BranchSpec],
    xids: ConcurrentStableDict[str, str],
    *,
    reject: str | None = None,
) -> ConcurrentStableList[str]:
    """逐分支执行（`XA_START → 业务写 → XA_END → XA_PREPARE`，单请求内一次完成）。

    Args:
        participant: 分支执行器。
        specs: 分支声明。
        xids: 库键 → 分支 `xid`（**取账本分配值**，不用自造值）。
        reject: 指定 `db_key` 的分支改用**未登记 `op`** 载荷（模拟该分支否决）。

    Returns:
        ConcurrentStableList[str]: 各分支执行结果（`prepared` / `rejected`）。
    """
    states: ConcurrentStableList[str] = ConcurrentStableList()
    for spec in specs:
        op = "it.probe.unknown" if spec.db_key == reject else _OP_INSERT
        states.add(
            await participant.execute_branch(
                xid=xids[spec.db_key],
                db_key=spec.db_key,
                ops=ConcurrentStableFrozenList((BranchOp(op=op, args=_payload(spec.db_key, 1)),)),
            )
        )
    return states


async def _begin(coordinator: TransactionCoordinator) -> str:
    """开启全局事务并返回标识（分支 `xid` 由 TM 分配）。"""
    snapshot = await coordinator.begin(caller_service="platform", branches=_probe_specs())
    return snapshot.global_txn_id


async def _set_state(uow: DbUnitOfWork, global_txn_id: str, state: str) -> None:
    """把账本置为指定状态（模拟崩溃现场：决定点前 / 后）。"""
    txns = GlobalTxnRepository(uow.session)
    async with uow.begin():
        row = await txns.get_by_global_txn_id(global_txn_id)
        assert row is not None
        row.state = state
        if state == TXN_COMMITTING:
            row.decided_at = datetime.now(UTC)
        await txns.flush()


async def _branch_xids(uow: DbUnitOfWork, global_txn_id: str) -> ConcurrentStableDict[str, str]:
    """取该事务各分支（`db_key` → `xid`）。"""
    branches = GlobalTxnBranchRepository(uow.session)
    async with uow.begin():
        rows = await branches.list_by_txn(global_txn_id)
    return ConcurrentStableDict({row.db_key: row.xid for row in rows})


async def _rollback_leftovers(participant: XaTransactionParticipant, xids: ConcurrentStableDict[str, str]) -> None:
    """清理残留悬挂分支（失败路径用；已确认的分支回滚会明确失败并被吞掉）。"""
    for db_key, xid in xids.items():
        try:
            await participant.rollback_branch(xid=xid, db_key=db_key)
        except Exception:  # 清理路径失败不掩盖用例结论
            continue


async def test_two_branch_commit_all_prepared(
    probes: ConcurrentStableDict[str, Engine], uow: DbUnitOfWork, participant: XaTransactionParticipant
) -> None:
    """全票提交：两库分支均 `prepared` ⇒ 决定点后全员 `XA_COMMIT`（两库可见同一业务写入）。"""
    driver = _InProcessBranchDriver(participant)
    coordinator = _coordinator(uow, driver)
    global_txn_id = await _begin(coordinator)
    xids = await _branch_xids(uow, global_txn_id)

    states = await _prepare_all(participant, _probe_specs(), xids)
    assert list(states) == [BRANCH_PREPARED, BRANCH_PREPARED]
    # 分支已 PREPARE、未提交 ⇒ **业务不可见**（两库均无行）
    assert _notes(probes[_DB_MYSQL]) == []
    assert _notes(probes[_DB_PG]) == []

    result = await coordinator.commit(global_txn_id)

    assert result.state == "committed"
    assert _notes(probes[_DB_MYSQL]) == [_DB_MYSQL]
    assert _notes(probes[_DB_PG]) == [_DB_PG]
    assert len(driver.committed) == 2
    await _rollback_leftovers(participant, xids)


async def test_single_branch_rejection_rolls_back_all(
    probes: ConcurrentStableDict[str, Engine], uow: DbUnitOfWork, participant: XaTransactionParticipant
) -> None:
    """单分支否决：`pg` 分支载荷 `op` 未登记 ⇒ 全量回滚，**两侧无变更**。"""
    driver = _InProcessBranchDriver(participant)
    coordinator = _coordinator(uow, driver)
    global_txn_id = await _begin(coordinator)
    xids = await _branch_xids(uow, global_txn_id)

    states = await _prepare_all(participant, _probe_specs(), xids, reject=_DB_PG)
    assert list(states) == [BRANCH_PREPARED, "rejected"]

    result = await coordinator.commit(global_txn_id)

    assert result.state == "rolled_back"
    assert len(driver.rolled_back) == 2  # 含未 PREPARE 分支的幂等回滚
    assert _notes(probes[_DB_MYSQL]) == []
    assert _notes(probes[_DB_PG]) == []
    await _rollback_leftovers(participant, xids)


async def test_recovery_rolls_back_before_decision(
    probes: ConcurrentStableDict[str, Engine], uow: DbUnitOfWork, participant: XaTransactionParticipant
) -> None:
    """崩溃注入（**决定点前**）：账本 `preparing` + 两库悬挂分支 ⇒ 恢复器驱动全量回滚、两侧无变更。"""
    driver = _InProcessBranchDriver(participant)
    coordinator = _coordinator(uow, driver)
    global_txn_id = await _begin(coordinator)
    xids = await _branch_xids(uow, global_txn_id)
    await _prepare_all(participant, _probe_specs(), xids)
    await _set_state(uow, global_txn_id, TXN_PREPARING)

    handled = await _recovery(uow, coordinator).run_once()

    assert handled == 1
    assert (await coordinator.status(global_txn_id)).state == "rolled_back"
    assert _notes(probes[_DB_MYSQL]) == []
    assert _notes(probes[_DB_PG]) == []
    await _rollback_leftovers(participant, xids)


async def test_recovery_drives_commit_after_decision(
    probes: ConcurrentStableDict[str, Engine], uow: DbUnitOfWork, participant: XaTransactionParticipant
) -> None:
    """崩溃注入（**决定点后**）：账本 `committing` + 两库悬挂分支 ⇒ 恢复器驱动全量提交。"""
    driver = _InProcessBranchDriver(participant)
    coordinator = _coordinator(uow, driver)
    global_txn_id = await _begin(coordinator)
    xids = await _branch_xids(uow, global_txn_id)
    await _prepare_all(participant, _probe_specs(), xids)
    await _set_state(uow, global_txn_id, TXN_COMMITTING)

    recovery = _recovery(uow, coordinator)
    assert await recovery.run_once() == 1

    assert (await coordinator.status(global_txn_id)).state == "committed"
    assert _notes(probes[_DB_MYSQL]) == [_DB_MYSQL]
    assert _notes(probes[_DB_PG]) == [_DB_PG]
    driven = len(driver.committed)
    assert await recovery.run_once() == 0  # 幂等重放：终态不重复驱动
    assert len(driver.committed) == driven
    await _rollback_leftovers(participant, xids)


def _recovery(uow: DbUnitOfWork, coordinator: TransactionCoordinator) -> TransactionRecovery:
    """构造恢复器（单轮逻辑；账本为内存 SQLite、分支为真库）。"""
    return TransactionRecovery(
        coordinator,
        GlobalTxnRepository(uow.session),
        GlobalTxnBranchRepository(uow.session),
        GlobalTxnRecoveryRepository(uow.session),
        uow,
    )
