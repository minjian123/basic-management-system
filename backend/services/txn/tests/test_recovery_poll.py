"""恢复器常驻任务用例（强一致专项 05_07；Kiwi 2271）：启动扫一轮 / 周期 / 领导者续租 / 锁不可用 / 指标。

- **仅 leader 驱动**：非 leader（锁被占）与锁不可用（Redis 故障）一律跳过本轮、不触碰账本会话；
- **续租**：已持有 token 时 `extend`；续租失败即重新竞争（`acquire`）；
- **生命周期**：`setup()` 先扫一轮再起周期；`aclose()` 取消循环并释放 leader 锁；
- **装配**：工厂从应用状态取引擎注册表 / 分布式锁 / 分支驱动 / 指标。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import cast

import pytest
from fastapi import FastAPI
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import PluginError
from bms_core.core.plugin import PluginImpl
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.lock.base import BaseDistributedLock
from bms_core.lock.null import NullDistributedLock
from bms_core.transaction.base import BRANCH_PREPARED, TXN_COMMITTING, BranchSpec
from bms_txn.domains.txn.models.ledger import GlobalTxn, GlobalTxnBranch, GlobalTxnRecovery
from bms_txn.domains.txn.repositories.ledger import GlobalTxnBranchRepository, GlobalTxnRepository
from bms_txn.domains.txn.services.coordinator import TransactionCoordinator
from bms_txn.domains.txn.services.driver import BranchDriver
from bms_txn.domains.txn.services.recovery_poll import (
    METRIC_LEADER_SWITCH,
    POLL_PROVIDER_NAME,
    PollTransactionRecovery,
    PollTransactionRecoveryFactory,
    SessionOpener,
    register_transaction_recovery,
)
from tests_support.metrics import RecordingMetrics

pytestmark = [pytest.mark.kiwi_id(2271)]

SessionMaker = async_sessionmaker[AsyncSession]


class FakeLock(BaseDistributedLock):
    """分布式锁替身：可注故障、记录调用并支持续租成功 / 失败切换。"""

    def __init__(self, *, fail: bool = False, taken: bool = False) -> None:
        """初始化。

        Args:
            fail: True 时 `acquire` / `extend` 抛错（模拟 Redis 故障）。
            taken: True 时锁键已被他人持有（本副本拿不到）。
        """
        self.fail = fail
        self.taken = taken
        self.extend_result = True
        self.acquire_calls = 0
        self.extend_calls = 0
        self.release_calls = 0
        self.held: str | None = None

    async def acquire(self, key: str, *, ttl: int = 30, wait: float = 0) -> str | None:
        """取锁（`taken` 时返回 None）。"""
        del key, ttl, wait
        self.acquire_calls += 1
        if self.fail:
            raise RuntimeError("redis down")
        if self.taken:
            return None
        self.held = f"token-{self.acquire_calls}"
        return self.held

    async def release(self, key: str, token: str) -> bool:
        """释放锁。"""
        del key
        self.release_calls += 1
        released = self.held == token
        self.held = None
        return released

    async def extend(self, key: str, token: str, *, ttl: int = 30) -> bool:
        """续租（`extend_result` 为假即续租失败）。"""
        del key, token, ttl
        self.extend_calls += 1
        if self.fail:
            raise RuntimeError("redis down")
        return self.extend_result


class FakeDriver(BranchDriver):
    """分支驱动替身：核验恒 `prepared`，记录驱动调用（真实驱动见集成用例）。"""

    def __init__(self) -> None:
        """初始化。"""
        self.committed: ConcurrentStableList[str] = ConcurrentStableList()
        self.verified: ConcurrentStableList[str] = ConcurrentStableList()

    async def verify(self, *, service: str, db_key: str, xid: str) -> str:
        """核验分支（恒 `prepared`）。"""
        del service, db_key
        self.verified.add(xid)
        return BRANCH_PREPARED

    async def commit(self, *, service: str, db_key: str, xid: str) -> str:
        """提交分支并记录。"""
        del service, db_key
        self.committed.add(xid)
        return "committed"

    async def rollback(self, *, service: str, db_key: str, xid: str) -> str:
        """回滚分支（本用例不记录）。"""
        del service, db_key, xid
        return "rolled_back"


class _LedgerEngine:
    """内存 SQLite 账本（异步上下文管理器：进入建三表、退出释放引擎）。"""

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


class _SessionScope:
    """账本会话作用域（进入开会话、退出关闭）。"""

    def __init__(self, factory: SessionMaker) -> None:
        self._session = factory()

    async def __aenter__(self) -> DbSession:
        """返回会话。"""
        return self._session

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """关闭会话。"""
        del exc_type, exc, traceback
        await self._session.close()


def _opener(factory: SessionMaker) -> SessionOpener:
    """会话开启器：每轮新建会话、用后关闭。"""

    def _open() -> AbstractAsyncContextManager[DbSession]:
        return _SessionScope(factory)

    return _open


async def _seed_committing(factory: SessionMaker, driver: FakeDriver) -> None:
    """建一个 `committing` 在途事务（模拟「决定点已落、驱动中断」）。"""
    session = factory()
    uow = DbUnitOfWork(session)
    coordinator = TransactionCoordinator(GlobalTxnRepository(session), GlobalTxnBranchRepository(session), uow, driver)
    started = await coordinator.begin(
        caller_service="platform",
        branches=ConcurrentStableList((BranchSpec(branch_id="p1", service="platform", db_key="platform"),)),
    )
    txns = GlobalTxnRepository(session)
    async with uow.begin():
        row = await txns.get_by_global_txn_id(started.global_txn_id)
        assert row is not None
        row.state = TXN_COMMITTING
        row.decided_at = datetime.now(UTC)
        await txns.flush()
    await session.close()


@pytest.fixture
async def ledger() -> AsyncIterator[SessionMaker]:
    """账本会话工厂（内存 SQLite，三表）。"""
    async with _LedgerEngine() as factory:
        yield factory


@pytest.fixture
async def drain() -> AsyncIterator[ConcurrentStableList[PollTransactionRecovery]]:
    """收集用例构造的常驻任务，用例结束统一 `aclose`（避免后台任务泄漏）。"""
    created: ConcurrentStableList[PollTransactionRecovery] = ConcurrentStableList()
    yield created
    for item in created:
        await item.aclose()


async def test_setup_runs_startup_round_then_periodic(
    ledger: SessionMaker, drain: ConcurrentStableList[PollTransactionRecovery], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`setup()`：先跑一轮（处置在途事务）再起周期循环；`aclose()` 停止循环。"""
    driver = FakeDriver()
    await _seed_committing(ledger, driver)
    plugin = PollTransactionRecovery(
        sessions=_opener(ledger), lock=FakeLock(), driver=driver, interval_seconds=0.01, metrics=RecordingMetrics()
    )
    drain.add(plugin)
    calls: ConcurrentStableList[int] = ConcurrentStableList()
    original = plugin.run_once

    async def _counting(*, now: datetime | None = None) -> int:
        calls.add(1)
        return await original(now=now)

    monkeypatch.setattr(plugin, "run_once", _counting)
    await plugin.setup()
    assert len(calls) == 1  # 启动即扫一轮
    assert len(driver.committed) == 1  # 且已驱动提交（committing ⇒ commit）
    import asyncio  # 局部导入：仅本用例需要等待周期

    await asyncio.sleep(0.05)
    assert len(calls) >= 2  # 周期循环已在跑
    await plugin.aclose()
    settled = len(calls)
    await asyncio.sleep(0.05)
    assert len(calls) == settled  # 取消后不再推进


async def test_run_once_skips_when_lock_taken(ledger: SessionMaker) -> None:
    """非 leader（锁被他人持有）⇒ 跳过本轮，且**不开启账本会话**。"""
    opened: ConcurrentStableList[int] = ConcurrentStableList()
    opener = _opener(ledger)

    def _counting_opener() -> AbstractAsyncContextManager[DbSession]:
        opened.add(1)
        return opener()

    plugin = PollTransactionRecovery(sessions=_counting_opener, lock=FakeLock(taken=True), driver=FakeDriver())
    assert plugin.enabled is True
    assert await plugin.run_once() == 0
    assert opened == []


async def test_run_once_skips_when_lock_unavailable(ledger: SessionMaker) -> None:
    """锁不可用（Redis 故障）⇒ 跳过本轮并告警，不抛错、不触碰账本。"""
    plugin = PollTransactionRecovery(sessions=_opener(ledger), lock=FakeLock(fail=True), driver=FakeDriver())
    assert await plugin.run_once() == 0


async def test_leader_renewed_then_reacquired(
    ledger: SessionMaker, drain: ConcurrentStableList[PollTransactionRecovery]
) -> None:
    """首轮取锁，次轮续租（不重新取）；续租失败则重新竞争并再次计数。"""
    lock = FakeLock()
    metrics = RecordingMetrics()
    plugin = PollTransactionRecovery(sessions=_opener(ledger), lock=lock, driver=FakeDriver(), metrics=metrics)
    drain.add(plugin)
    assert await plugin.run_once() == 0
    assert (lock.acquire_calls, lock.extend_calls) == (1, 0)
    assert await plugin.run_once() == 0  # 续租成功：不再 acquire
    assert (lock.acquire_calls, lock.extend_calls) == (1, 1)
    lock.extend_result = False
    assert await plugin.run_once() == 0  # 续租失败：重新竞争
    assert (lock.acquire_calls, lock.extend_calls) == (2, 2)
    assert list(metrics.counter_values(METRIC_LEADER_SWITCH)) == [1.0, 1.0]  # 两次取得领导权


async def test_extend_failure_swallows_lock_error(
    ledger: SessionMaker, drain: ConcurrentStableList[PollTransactionRecovery]
) -> None:
    """续租抛错（锁不可用）⇒ 跳过本轮并清零 token，下轮重新竞争。"""
    lock = FakeLock()
    plugin = PollTransactionRecovery(sessions=_opener(ledger), lock=lock, driver=FakeDriver())
    drain.add(plugin)
    assert await plugin.run_once() == 0
    lock.fail = True
    assert await plugin.run_once() == 0
    assert lock.acquire_calls == 1  # 续租抛错当轮不再竞争
    lock.fail = False
    assert await plugin.run_once() == 0
    assert lock.acquire_calls == 2


async def test_aclose_releases_leadership(
    ledger: SessionMaker, drain: ConcurrentStableList[PollTransactionRecovery]
) -> None:
    """`aclose()`：释放 leader 锁且不重复释放（非 leader 时为空操作）。"""
    lock = FakeLock()
    plugin = PollTransactionRecovery(sessions=_opener(ledger), lock=lock, driver=FakeDriver())
    drain.add(plugin)
    assert await plugin.run_once() == 0
    await plugin.aclose()
    assert lock.release_calls == 1
    await plugin.aclose()  # 幂等：token 已清零，不再释放
    assert lock.release_calls == 1


async def test_round_guarded_swallows_errors(
    ledger: SessionMaker, drain: ConcurrentStableList[PollTransactionRecovery], monkeypatch: pytest.MonkeyPatch
) -> None:
    """单轮异常被吸收（循环不终止）。"""
    plugin = PollTransactionRecovery(sessions=_opener(ledger), lock=FakeLock(), driver=FakeDriver())
    drain.add(plugin)

    async def _boom(*, now: datetime | None = None) -> int:
        del now
        raise RuntimeError("round down")

    monkeypatch.setattr(plugin, "run_once", _boom)
    await plugin.setup()  # 启动轮异常被吸收，不向上抛
    assert plugin._task is not None  # pyright: ignore[reportPrivateUsage]  # 后台任务已起


async def test_run_once_drives_ledger_round(ledger: SessionMaker) -> None:
    """单轮：构造真实仓储与会话驱动在途事务（计数 1，分支被提交）。"""
    driver = FakeDriver()
    await _seed_committing(ledger, driver)
    plugin = PollTransactionRecovery(
        sessions=_opener(ledger),
        lock=FakeLock(),
        driver=driver,
        metrics=RecordingMetrics(),
        batch_limit=5,
        deadline_seconds=123.0,
    )
    assert await plugin.run_once() == 1
    assert len(driver.committed) == 1


async def test_factory_reads_app_state_and_falls_back() -> None:
    """工厂：从应用状态取锁 / 驱动 / 指标；缺失时回退 `null` 锁与「不可用」驱动。"""
    settings = Settings()
    app = FastAPI()
    app.state.metrics = RecordingMetrics()
    app.state.distributed_lock = FakeLock()
    app.state.branch_driver = FakeDriver()
    plugin = PollTransactionRecoveryFactory(settings, app).create()
    assert plugin.plugin_name == POLL_PROVIDER_NAME
    assert isinstance(plugin._driver, FakeDriver)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(plugin._lock, FakeLock)  # pyright: ignore[reportPrivateUsage]

    bare = FastAPI()
    fallback = PollTransactionRecoveryFactory(settings, bare).create()
    assert isinstance(fallback._lock, NullDistributedLock)  # pyright: ignore[reportPrivateUsage]
    assert fallback._metrics is None  # pyright: ignore[reportPrivateUsage]


async def test_session_opener_opens_registry_session(ledger: SessionMaker, monkeypatch: pytest.MonkeyPatch) -> None:
    """会话开启器：工厂装配后**按应用注册表开会话**（单轮真实构造与执行）。"""
    from bms_txn.domains.txn.services import recovery_poll as module

    settings = Settings()
    app = FastAPI()
    app.state.engine_registry = EngineRegistry(EngineFactory(settings))
    app.state.distributed_lock = FakeLock()
    app.state.branch_driver = FakeDriver()
    opened: ConcurrentStableList[str] = ConcurrentStableList()

    def _scope(_registry: object, *, factory: object = None) -> AbstractAsyncContextManager[DbSession]:
        del _registry, factory
        opened.add("open")
        return _SessionScope(ledger)

    monkeypatch.setattr(module, "session_scope", _scope)
    plugin = PollTransactionRecoveryFactory(settings, app).create()
    try:
        assert await plugin.run_once() == 0
    finally:
        await plugin.aclose()
    assert list(opened) == ["open"]


def test_register_transaction_recovery_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """登记：同一注册表重复调用只登记一次（幂等）且返回真。"""
    from bms_txn.domains.txn.services import recovery_poll as module

    recorded: ConcurrentStableList[str] = ConcurrentStableList()
    monkeypatch.setattr(module, "_REGISTERED_REGISTRIES", ConcurrentStableList())
    monkeypatch.setattr(module, "register_plugin", _record_plugin(recorded))
    settings = Settings()
    app = FastAPI()
    assert register_transaction_recovery(settings, app) is True
    assert register_transaction_recovery(settings, app) is True
    assert list(recorded) == [POLL_PROVIDER_NAME]


def test_register_transaction_recovery_skips_when_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    """注册表已冻结（多服务同进程）：跳过登记并返回假（调用方回落 `null`，不阻断应用构造）。"""
    from bms_txn.domains.txn.services import recovery_poll as module

    def _frozen(*args: object, **kwargs: object) -> None:
        raise PluginError("插件注册表已构建，运行期只读，禁止再登记")

    monkeypatch.setattr(module, "_REGISTERED_REGISTRIES", ConcurrentStableList())
    monkeypatch.setattr(module, "register_plugin", _frozen)
    assert register_transaction_recovery(Settings(), FastAPI()) is False


async def test_round_guarded_reraises_cancel(
    ledger: SessionMaker, drain: ConcurrentStableList[PollTransactionRecovery], monkeypatch: pytest.MonkeyPatch
) -> None:
    """单轮遇取消：照常向上抛出（不吞 `CancelledError`，保证收尾语义）。"""
    import asyncio

    plugin = PollTransactionRecovery(sessions=_opener(ledger), lock=FakeLock(), driver=FakeDriver())
    drain.add(plugin)

    async def _cancel(*, now: datetime | None = None) -> int:
        del now
        raise asyncio.CancelledError

    monkeypatch.setattr(plugin, "run_once", _cancel)
    with pytest.raises(asyncio.CancelledError):
        await plugin.setup()


def test_txn_configure_plugins_defaults_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    """服务侧钩子：登记成功且未显式配置 ⇒ 缺省置 `poll`。"""
    from bms_txn import main as txn_main

    settings = Settings()
    monkeypatch.setattr(txn_main, "register_transaction_recovery", _always_true)
    txn_main.ApplicationFactory().configure_plugins(FastAPI(), settings)
    assert settings.transaction_manager.transaction_recovery == POLL_PROVIDER_NAME


def test_txn_configure_plugins_keeps_empty_when_registration_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """服务侧钩子：登记失败（注册表冻结）⇒ **不下发缺省**（回落 `null` 不启用）。"""
    from bms_txn import main as txn_main

    settings = Settings()
    monkeypatch.setattr(txn_main, "register_transaction_recovery", _always_false)
    txn_main.ApplicationFactory().configure_plugins(FastAPI(), settings)
    assert settings.transaction_manager.transaction_recovery == ""


def _record_plugin(recorded: ConcurrentStableList[str]) -> Callable[[str, str, PluginImpl], None]:
    """构造登记替身：记录实现名（签名与 `register_plugin` 一致）。"""

    def _register(_key: str, name: str, _impl: PluginImpl) -> None:
        recorded.add(name)

    return _register


def _always_true(_settings: Settings, _app: FastAPI) -> bool:
    """登记替身：恒定成功。"""
    del _settings, _app
    return True


def _always_false(_settings: Settings, _app: FastAPI) -> bool:
    """登记替身：恒定失败（注册表冻结）。"""
    del _settings, _app
    return False


async def test_setup_is_idempotent(ledger: SessionMaker, drain: ConcurrentStableList[PollTransactionRecovery]) -> None:
    """`setup()` 幂等：已在运行时再次调用不重复起任务、不重复启动扫描。"""
    plugin = PollTransactionRecovery(
        sessions=_opener(ledger), lock=FakeLock(), driver=FakeDriver(), interval_seconds=30.0
    )
    drain.add(plugin)
    await plugin.setup()
    task = plugin._task  # pyright: ignore[reportPrivateUsage]
    await plugin.setup()  # 早退：不重复起任务
    assert plugin._task is task  # pyright: ignore[reportPrivateUsage]
