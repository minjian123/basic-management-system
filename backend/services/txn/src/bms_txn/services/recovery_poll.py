"""恢复器常驻任务（插件 `transaction_recovery` × `poll`）：周期对账 + 领导者续租 + 指标。

装配口径（详设 05_07 §3.4）：

- `setup()` **先跑一轮**（仅 leader）再起周期循环；`aclose()` 取消任务并尽力释放 leader 锁
  （`BasePluggable` 具异步资源语义，装配后由资源管理器逆序回收）；
- **每轮新建账本会话**（平台库）→ 构造协调器与仓储 → 复用 `TransactionRecovery` 单轮逻辑；
- **领导者选举**：持有 token 时 `extend` 续租，续租失败即重新竞争（`acquire(wait=0)`）；
  **锁不可用**（Redis 故障 / `null` 实现）⇒ 跳过本轮 + 明确告警（不阻断服务与 API，**不退化为直跑**）；
- **指标**：`bms_txn_leader_switch_total`（本副本取得领导权次数，≈ 全局切换次数）；单轮的恢复驱动与
  悬挂计数由 `TransactionRecovery` 上报（`bms_txn_recovery_total` / `bms_txn_hung`）。
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import TYPE_CHECKING, cast

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import PluginError
from bms_core.core.factory import BasePluginFactory
from bms_core.core.logging import get_logger
from bms_core.core.plugin import default_plugin_registry, register_plugin
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, SessionFactory, session_scope
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.lock.base import BaseDistributedLock
from bms_core.lock.null import NullDistributedLock
from bms_core.metrics.base import BaseMetrics
from bms_core.transaction.base import TRANSACTION_RECOVERY_KEY, BaseTransactionRecovery
from bms_txn.repositories.ledger import (
    GlobalTxnBranchRepository,
    GlobalTxnRecoveryRepository,
    GlobalTxnRepository,
)
from bms_txn.services.coordinator import DEFAULT_DEADLINE_SECONDS, TransactionCoordinator
from bms_txn.services.driver import BranchDriver, UnavailableBranchDriver
from bms_txn.services.ledger_cleanup import DEFAULT_RETENTION_DAYS, LedgerCleanup
from bms_txn.services.recovery import DEFAULT_BATCH_LIMIT, TransactionRecovery

if TYPE_CHECKING:
    from fastapi import FastAPI

__all__ = [
    "METRIC_LEADER_SWITCH",
    "POLL_PROVIDER_NAME",
    "PollTransactionRecovery",
    "PollTransactionRecoveryFactory",
    "SessionOpener",
    "register_transaction_recovery",
]

POLL_PROVIDER_NAME = "poll"
"""恢复器实现名（`[transaction_manager].transaction_recovery`）。"""

METRIC_LEADER_SWITCH = "bms_txn_leader_switch_total"
"""指标：本副本取得领导权次数（≈ leader 切换次数；多副本下各副本各自计数）。"""

_LOGGER = get_logger("bms.txn.recovery")

_REGISTERED_REGISTRIES: ConcurrentStableList[object] = ConcurrentStableList()
"""已登记 `poll` 恢复器的注册表实例清单（按实例幂等；注册表重置后需重新登记）。"""


def register_transaction_recovery(settings: Settings, app: FastAPI) -> bool:
    """登记恢复器工厂（服务侧插件钩子调用，**须在建注册表之前**）。

    **按注册表实例幂等**（插件注册表是进程级、且可被测试重置）：同一注册表只登记一次；
    换个注册表实例（重置 / 替换）则重新登记，避免重置后 `poll` 丢失（口径同 `permission`）。

    **多服务同进程**（测试里 platform + txn 应用并存）时注册表可能**已冻结**：此时无法登记，
    函数返回假并告警——调用方据此**不下发** `poll` 缺省（回落 `null` 不启用），避免装配期解析失败。

    Args:
        settings: 应用配置（`[transaction_manager]` 周期与锁参数）。
        app: 应用实例（工厂延迟取用 `state`）。

    Returns:
        bool: 已登记（或本次无需登记）为真；注册表已冻结无法登记为假。
    """
    registry = default_plugin_registry()
    if any(item is registry for item in _REGISTERED_REGISTRIES):
        return True
    try:
        register_plugin(TRANSACTION_RECOVERY_KEY, POLL_PROVIDER_NAME, PollTransactionRecoveryFactory(settings, app))
    except PluginError as exc:
        _LOGGER.warning("transaction_recovery_registration_skipped", error=str(exc))
        return False
    _REGISTERED_REGISTRIES.add(registry)
    return True


SessionOpener = Callable[[], AbstractAsyncContextManager[DbSession]]
"""账本会话开启器（每轮新建；生产为平台库会话，用例可注入替身）。"""


class PollTransactionRecovery(BaseTransactionRecovery):
    """恢复器常驻任务：`setup()` 先扫一轮再起周期，**仅 leader** 执行（详设 §3.4）。"""

    plugin_name: str = POLL_PROVIDER_NAME

    def __init__(
        self,
        *,
        sessions: SessionOpener,
        lock: BaseDistributedLock,
        driver: BranchDriver,
        interval_seconds: float = 30.0,
        leader_lock_key: str = "bms:global:lock:txn:leader",
        leader_lock_ttl: int = 30,
        deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
        batch_limit: int = DEFAULT_BATCH_LIMIT,
        ledger_retention_days: int = DEFAULT_RETENTION_DAYS,
        metrics: BaseMetrics | None = None,
    ) -> None:
        """初始化。

        Args:
            sessions: 账本会话开启器（每轮新建；平台库）。
            lock: 分布式锁（领导者选举；复用 `[distributed_lock]`）。
            driver: 分支驱动（TM 驱动各参与端点）。
            interval_seconds: 扫描间隔（秒）。
            leader_lock_key: leader 锁键。
            leader_lock_ttl: leader 锁 TTL（秒；每轮续租）。
            deadline_seconds: 全局提交截止（秒；协调器用）。
            batch_limit: 单轮扫描上限。
            ledger_retention_days: 账本保留期（天；终态超期即清理，详设 §3.5）。
            metrics: 指标出口（None 不上报）。
        """
        self._sessions = sessions
        self._lock = lock
        self._driver = driver
        self._interval_seconds = interval_seconds
        self._leader_lock_key = leader_lock_key
        self._leader_lock_ttl = leader_lock_ttl
        self._deadline_seconds = deadline_seconds
        self._batch_limit = batch_limit
        self._ledger_retention_days = ledger_retention_days
        self._metrics = metrics
        self._token: str | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def enabled(self) -> bool:
        """恒定真（TM 服务本职；非 TM 服务由缺省 `null` 提供者承担「不启用」）。"""
        return True

    async def setup(self) -> None:
        """启动：**先跑一轮**（仅 leader）再起周期循环（幂等）。"""
        if self._task is not None:
            return
        await self._round_guarded()
        self._task = asyncio.create_task(self._run_forever())

    async def aclose(self) -> None:
        """收尾：取消后台循环并尽力释放 leader 锁（幂等）。"""
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        token = self._token
        self._token = None
        if token is None:
            return
        with contextlib.suppress(Exception):  # 释放失败不影响退出（TTL 自行过期）
            await self._lock.release(self._leader_lock_key, token)

    async def run_once(self, *, now: datetime | None = None) -> int:
        """单轮：非 leader / 锁不可用即跳过（返回 0）；leader 则执行一轮对账。

        Args:
            now: 当前时间（UTC；缺省取系统时钟；用例可注入）。

        Returns:
            int: 本轮处置的事务数（跳过时为 0）。
        """
        if not await self._refresh_leadership():
            return 0
        async with self._sessions() as session:
            recovery = self._build_recovery(session)
            handled = await recovery.run_once(now=now)
            cleaned = await self._build_cleanup(session).run_once(now=now)
        _LOGGER.info("txn_recovery_round", handled=handled, cleaned=cleaned.total)
        return handled

    def _build_recovery(self, session: DbSession) -> TransactionRecovery:
        """按本轮会话构造协调器与恢复器（**只组合既有件，不复制业务逻辑**）。

        Args:
            session: 本轮账本会话（平台库）。

        Returns:
            TransactionRecovery: 本轮恢复器实例。
        """
        uow = DbUnitOfWork(session)
        coordinator = TransactionCoordinator(
            GlobalTxnRepository(session),
            GlobalTxnBranchRepository(session),
            uow,
            self._driver,
            deadline_seconds=self._deadline_seconds,
            metrics=self._metrics,
        )
        return TransactionRecovery(
            coordinator,
            GlobalTxnRepository(session),
            GlobalTxnBranchRepository(session),
            GlobalTxnRecoveryRepository(session),
            uow,
            batch_limit=self._batch_limit,
            metrics=self._metrics,
        )

    def _build_cleanup(self, session: DbSession) -> LedgerCleanup:
        """按本轮会话构造账本清理器（**先对账、后清理**，同轮同会话）。

        Args:
            session: 本轮账本会话（平台库）。

        Returns:
            LedgerCleanup: 本轮清理器实例。
        """
        return LedgerCleanup(
            GlobalTxnRepository(session),
            GlobalTxnBranchRepository(session),
            GlobalTxnRecoveryRepository(session),
            DbUnitOfWork(session),
            retention_days=self._ledger_retention_days,
            batch_limit=self._batch_limit,
            metrics=self._metrics,
        )

    async def _run_forever(self) -> None:
        """后台循环（取消时退出；单轮异常不终止循环）。"""
        while True:
            await asyncio.sleep(self._interval_seconds)
            await self._round_guarded()

    async def _round_guarded(self) -> None:
        """执行一轮并吸收异常（取消照常抛出）。"""
        try:
            await self.run_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # 单轮异常不终止循环（下一轮重试）
            _LOGGER.warning("txn_recovery_round_error", error=repr(exc))

    async def _refresh_leadership(self) -> bool:
        """续租或重新竞争 leader 锁（锁不可用即告警并返回假）。

        Returns:
            bool: 本副本当前是否为 leader（锁不可用 / 他人持有时为 False）。
        """
        token = self._token
        if token is not None:
            try:
                if await self._lock.extend(self._leader_lock_key, token, ttl=self._leader_lock_ttl):
                    return True
            except Exception as exc:
                _LOGGER.warning("txn_recovery_lock_unavailable", error=repr(exc))
                self._token = None
                return False
            self._token = None  # 续租失败（已被他人取得）⇒ 重新竞争
        try:
            acquired = await self._lock.acquire(self._leader_lock_key, ttl=self._leader_lock_ttl, wait=0)
        except Exception as exc:
            _LOGGER.warning("txn_recovery_lock_unavailable", error=repr(exc))
            return False
        if acquired is None:
            return False
        self._token = acquired
        metrics = self._metrics
        if metrics is not None:
            await metrics.counter(METRIC_LEADER_SWITCH)
        return True


class PollTransactionRecoveryFactory(BasePluginFactory[PollTransactionRecovery]):
    """`transaction_recovery` × `poll` 工厂（经应用 state 取引擎注册表 / 锁 / 驱动 / 指标）。"""

    plugin_key: str = TRANSACTION_RECOVERY_KEY
    plugin_name: str = POLL_PROVIDER_NAME

    def __init__(self, settings: Settings, app: FastAPI) -> None:
        """初始化。

        Args:
            settings: 应用配置（`[transaction_manager]` 周期与锁参数）。
            app: 应用实例（取 `engine_registry` / `distributed_lock` / `branch_driver` / `metrics`）。
        """
        self._settings = settings
        self._app = app

    def create(self, options: None = None) -> PollTransactionRecovery:
        """构造恢复器常驻任务。

        Args:
            options: 未使用（零参口径）。

        Returns:
            PollTransactionRecovery: 恢复器实例。
        """
        del options
        section = self._settings.transaction_manager
        return PollTransactionRecovery(
            sessions=_session_opener(self._app),
            lock=_lock_of(self._app),
            driver=_driver_of(self._app),
            interval_seconds=float(section.recovery_interval_seconds),
            leader_lock_key=section.leader_lock_key,
            leader_lock_ttl=int(section.leader_lock_ttl_seconds),
            deadline_seconds=float(section.deadline_seconds),
            ledger_retention_days=int(section.ledger_retention_days),
            metrics=_metrics_of(self._app),
        )


def _session_opener(app: FastAPI) -> SessionOpener:
    """构造账本会话开启器（每轮新建平台库会话；注册表取用时读取）。

    Args:
        app: 应用实例。

    Returns:
        SessionOpener: 会话开启器。
    """

    def _open() -> AbstractAsyncContextManager[DbSession]:
        registry = cast("EngineRegistry", app.state.engine_registry)
        return session_scope(registry, factory=SessionFactory())

    return _open


def _lock_of(app: FastAPI) -> BaseDistributedLock:
    """取应用装配的分布式锁（未装配回退 `null` 实现 ⇒ 本轮跳过并告警）。

    Args:
        app: 应用实例。

    Returns:
        BaseDistributedLock: 分布式锁实现。
    """
    lock = getattr(app.state, "distributed_lock", None)
    return lock if isinstance(lock, BaseDistributedLock) else NullDistributedLock()


def _metrics_of(app: FastAPI) -> BaseMetrics | None:
    """取应用装配的指标出口（未装配即不上报）。

    Args:
        app: 应用实例。

    Returns:
        BaseMetrics | None: 指标出口。
    """
    metrics = getattr(app.state, "metrics", None)
    return metrics if isinstance(metrics, BaseMetrics) else None


def _driver_of(app: FastAPI) -> BranchDriver:
    """取应用装配的分支驱动（未装配回退「不可用」实现 ⇒ 驱动即明确失败，不静默成功）。

    Args:
        app: 应用实例。

    Returns:
        BranchDriver: 分支驱动实现。
    """
    driver = getattr(app.state, "branch_driver", None)
    return driver if isinstance(driver, BranchDriver) else UnavailableBranchDriver()
