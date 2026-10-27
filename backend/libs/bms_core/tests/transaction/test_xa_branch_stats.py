"""XA 参与方分支统计用例（07B `02_03` §3.10）：分支内前后快照采集。

**Kiwi 编号**：本批新增用例暂不标 `kiwi_id`，统一归 `05_01` 回填。

**覆盖面**：`execute_branch_with_stats` 的探针分支（真实 SQLite 两阶段不可用，故用假连接替身
驱动 `_execute` 的探针路径）、无探针 / 多 op 时返回零统计、`register_stats_probe` 登记。
"""

from typing import Any

import pytest

from bms_core.core.concurrent import (
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.transaction.base import (
    BRANCH_PREPARED,
    BRANCH_REJECTED,
    BranchHandlerRegistry,
    BranchOp,
    BranchStats,
)
from bms_core.transaction.xa import XaTransactionParticipant


class _FakeTxn:
    """假两阶段事务：记录 prepare 调用。"""

    def __init__(self) -> None:
        """初始化。"""
        self.prepared = False

    def prepare(self) -> None:
        """标记已 prepare。"""
        self.prepared = True


class _FakeDbapi:
    """假 DBAPI 连接（`_release_prepared` 会直接关闭它）。"""

    def __init__(self) -> None:
        """初始化。"""
        self.closed = False

    def close(self) -> None:
        """标记已关闭。"""
        self.closed = True


class _FakeConnection:
    """假同步连接：提供 `begin_twophase` / `rollback` / `close` / `connection.dbapi_connection`。"""

    def __init__(self) -> None:
        """初始化。"""
        self.txn = _FakeTxn()
        self.rolled_back = False
        self.closed = False
        self.detached = False
        self.dbapi = _FakeDbapi()
        # `_release_prepared` 走 `connection.connection.dbapi_connection`
        self.connection = self

    def begin_twophase(self, _xid: str) -> _FakeTxn:
        """开启两阶段事务。

        Args:
            _xid: 分支标识。

        Returns:
            _FakeTxn: 假事务。
        """
        return self.txn

    def rollback(self) -> None:
        """标记已回滚。"""
        self.rolled_back = True

    def close(self) -> None:
        """标记已关闭。"""
        self.closed = True

    def detach(self) -> None:
        """标记已摘池。"""
        self.detached = True

    @property
    def dbapi_connection(self) -> _FakeDbapi:
        """DBAPI 连接（`_release_prepared` 直接关闭它）。

        Returns:
            _FakeDbapi: 假 DBAPI 连接。
        """
        return self.dbapi


class _FakeEngine:
    """假同步引擎：`connect()` 返回假连接。"""

    def __init__(self, connection: _FakeConnection) -> None:
        """初始化。

        Args:
            connection: 假连接。
        """
        self._connection = connection

    def connect(self) -> _FakeConnection:
        """返回假连接。

        Returns:
            _FakeConnection: 连接。
        """
        return self._connection


class _Engines:
    """引擎提供者替身。"""

    def __init__(self, engine: _FakeEngine) -> None:
        """初始化。

        Args:
            engine: 假引擎。
        """
        self._engine = engine

    async def get_sync(self, db_key: str, *, read_only: bool = False) -> _FakeEngine:
        """取引擎。

        Args:
            db_key: 库键。
            read_only: 是否只读。

        Returns:
            _FakeEngine: 引擎。
        """
        del db_key, read_only
        return self._engine


class _Probe:
    """统计探针替身：固定前后快照。"""

    def __init__(self) -> None:
        """初始化。"""
        self.snapshots = 0

    def snapshot(self, _connection: object) -> object:
        """取快照（第二次即执行后）。

        Args:
            _connection: 连接（忽略）。

        Returns:
            object: 快照。
        """
        self.snapshots += 1
        if self.snapshots == 1:
            return ConcurrentStableFrozenDict({"t": ConcurrentStableFrozenDict()})  # pyright: ignore
        return ConcurrentStableFrozenDict({"t": ConcurrentStableFrozenDict({"a": ()})})

    def diff(self, before: object, after: object) -> BranchStats:
        """求差。

        Args:
            before: 前快照。
            after: 后快照。

        Returns:
            BranchStats: 统计。
        """
        del before, after
        return BranchStats(created=1)


async def _handler(_session: Any, _args: Any) -> None:
    """分支处理器替身（空操作）。

    Args:
        _session: 会话。
        _args: 参数。
    """
    return None


def _participant(connection: _FakeConnection, *, with_handler: bool = True) -> XaTransactionParticipant:
    """构造参与方（假引擎 + 可选处理器）。

    Args:
        connection: 假连接。
        with_handler: 是否登记处理器。

    Returns:
        XaTransactionParticipant: 参与方。
    """
    handlers = BranchHandlerRegistry()
    if with_handler:
        handlers.register("op", _handler)
    return XaTransactionParticipant(_Engines(_FakeEngine(connection)), handlers)  # type: ignore[arg-type]


def _ops(op: str = "op") -> ConcurrentStableFrozenList[BranchOp]:
    """构造分支操作。

    Args:
        op: 操作名。

    Returns:
        ConcurrentStableFrozenList[BranchOp]: 操作清单。
    """
    return ConcurrentStableFrozenList((BranchOp(op=op, args=ConcurrentStableFrozenDict[str, object]()),))


async def test_with_stats_uses_probe_when_registered() -> None:
    """单 op 且已登记探针 → 走探针路径，返回统计。"""
    connection = _FakeConnection()
    participant = _participant(connection)
    probe = _Probe()
    participant.register_stats_probe("op", probe)  # pyright: ignore
    state, stats = await participant.execute_branch_with_stats(
        xid="t|a", db_key="platform_platform", ops=ConcurrentStableList(_ops())
    )
    assert state == BRANCH_PREPARED
    assert stats.created == 1
    assert probe.snapshots == 2
    assert connection.txn.prepared is True


async def test_with_stats_returns_zero_without_probe() -> None:
    """未登记探针 → 走普通执行，统计为 0。"""
    connection = _FakeConnection()
    participant = _participant(connection)
    state, stats = await participant.execute_branch_with_stats(
        xid="t|a", db_key="platform_platform", ops=ConcurrentStableList(_ops())
    )
    assert state == BRANCH_PREPARED
    assert (stats.created, stats.updated, stats.skipped) == (0, 0, 0)


async def test_with_stats_returns_zero_for_multiple_ops() -> None:
    """多 op 分支不采集统计（避免口径含糊），返回零统计。"""
    connection = _FakeConnection()
    participant = _participant(connection)
    participant.register_stats_probe("op", _Probe())  # pyright: ignore
    ops = ConcurrentStableList(
        [
            BranchOp(op="op", args=ConcurrentStableFrozenDict[str, object]()),
            BranchOp(op="op", args=ConcurrentStableFrozenDict[str, object]()),
        ]
    )
    state, stats = await participant.execute_branch_with_stats(xid="t|a", db_key="platform_platform", ops=ops)
    assert state == BRANCH_PREPARED
    assert stats.created == 0


async def test_with_stats_rejects_unregistered_op() -> None:
    """未登记 op → rejected（不触碰探针）。"""
    connection = _FakeConnection()
    participant = _participant(connection, with_handler=False)
    participant.register_stats_probe("op", _Probe())  # pyright: ignore
    state, stats = await participant.execute_branch_with_stats(
        xid="t|a", db_key="platform_platform", ops=ConcurrentStableList(_ops())
    )
    assert state == BRANCH_REJECTED
    assert stats.created == 0


async def test_plain_execute_branch_unchanged() -> None:
    """`execute_branch` 保持原契约（返回状态字符串，不受统计改造影响）。"""
    connection = _FakeConnection()
    participant = _participant(connection)
    state = await participant.execute_branch(xid="t|a", db_key="platform_platform", ops=ConcurrentStableList(_ops()))
    assert state == BRANCH_PREPARED


async def test_probe_failure_rolls_back() -> None:
    """处理器抛异常 → 回滚并向上抛（探针路径同样保证零脏数据）。"""

    class _BoomProbe(_Probe):
        """探针替身：`snapshot` 抛异常。"""

        def snapshot(self, _connection: object) -> object:
            """抛异常。

            Args:
                _connection: 连接（忽略）。

            Raises:
                RuntimeError: 恒定抛出。
            """
            raise RuntimeError("快照失败")

    connection = _FakeConnection()
    participant = _participant(connection)
    participant.register_stats_probe("op", _BoomProbe())  # pyright: ignore
    with pytest.raises(RuntimeError, match="快照失败"):
        await participant.execute_branch_with_stats(
            xid="t|a", db_key="platform_platform", ops=ConcurrentStableList(_ops())
        )
    assert connection.rolled_back is True
