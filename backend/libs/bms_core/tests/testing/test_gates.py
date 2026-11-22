"""数据库门上下文用例（Kiwi 2533）：单例、读门 / 写门、升级顺序与关闭。

口径见 `bms_core.testing.gates` 模块文档与《测试规范》「并行与隔离」节。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db import gate as gate_module
from bms_core.db.registry import PLATFORM_DB_KEY
from bms_core.testing import fixtures, gates, plugin, rwlock

pytestmark = pytest.mark.kiwi_id(2533)


@pytest.fixture(autouse=True)
def _isolate_gates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """每个用例用独立门目录，并在前后清空单例。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest 补丁夹具。

    Yields:
        None: 用例运行期。
    """

    def _gate_path(name: str) -> Path:
        """替身门路径（固定到本用例的临时目录）。"""
        return tmp_path / f"db-gate-{name}.lock"

    monkeypatch.setattr(gates, "gate_path", _gate_path)
    gates.reset_gates()
    yield
    gates.reset_gates()


@pytest.mark.kiwi_id(2536)
def test_gate_is_singleton_per_library() -> None:
    """**按库一把门**：同名复用同一实例，不同库（`platform` / `tenant` / 私有库）各一把。"""
    assert gates.gate(gates.PLATFORM_GATE) is gates.gate(gates.PLATFORM_GATE)
    assert gates.gate(gates.PLATFORM_GATE) is not gates.gate(gates.TENANT_GATE)
    assert gates.gate(gates.PLATFORM_GATE).name == gates.PLATFORM_GATE
    assert gates.gate(gates.TENANT_GATE).name == gates.TENANT_GATE


async def test_read_gate_context_releases() -> None:
    """读门上下文进出后回到未持有。"""
    async with gates.gate_scope(gates.PLATFORM_GATE, read_only=True):
        assert gates.gate(gates.PLATFORM_GATE).mode == rwlock.READ

    assert gates.gate(gates.PLATFORM_GATE).mode is None


async def test_write_gate_context_releases() -> None:
    """写门上下文进出后回到未持有。"""
    async with gates.gate_scope(gates.TENANT_GATE, read_only=False):
        assert gates.gate(gates.TENANT_GATE).mode == rwlock.WRITE

    assert gates.gate(gates.TENANT_GATE).mode is None


async def test_write_window_takes_platform_gate() -> None:
    """写窗口按平台库键取平台写门，退出即释放（直连引擎的单次写）。"""
    async with gates.write_window(PLATFORM_DB_KEY):
        assert gates.gate(gates.PLATFORM_GATE).mode == rwlock.WRITE

    assert gates.gate(gates.PLATFORM_GATE).mode is None


async def test_write_window_takes_tenant_gate_for_other_keys() -> None:
    """非平台库键一律走租户写门。"""
    async with gates.write_window("tenant_demo"):
        assert gates.gate(gates.TENANT_GATE).mode == rwlock.WRITE

    assert gates.gate(gates.TENANT_GATE).mode is None


@pytest.mark.kiwi_id(2537)
async def test_cross_db_write_follows_fixed_order() -> None:
    """跨库嵌套取门只允许**固定顺序**「平台库在前、租户库在后」：同向嵌套可完成、两把门各自归零。

    口径变更（2026-11-22 业主拍板）：门从「全库一把」改为「按库一把」。旧实现靠合并成一把门
    消除跨库 ABBA 互等；拆分后互等的可能性由**锁序约定**消除——反序嵌套（租户→平台）属违规
    用法，会等到超时后失败，不再有「同一把门可重入」的隐性兜底。因此本用例只锁「合规顺序」。
    """
    done: ConcurrentStableList[str] = ConcurrentStableList()

    async def _nested(tag: str) -> None:
        """平台写门内再取租户写门（合规顺序）。

        Args:
            tag: 完成标记。
        """
        async with (
            gates.gate_scope(gates.PLATFORM_GATE, read_only=False, wait=10.0),
            gates.gate_scope(gates.TENANT_GATE, read_only=False, wait=10.0),
        ):
            done.add(tag)

    await asyncio.wait_for(asyncio.gather(_nested("a"), _nested("b")), timeout=30.0)
    assert sorted(done) == ["a", "b"]
    assert gates.gate(gates.PLATFORM_GATE).mode is None
    assert gates.gate(gates.TENANT_GATE).mode is None


async def test_write_upgrade_leaves_no_read_share() -> None:
    """写路径升级后不留残余读份额（否则内核共享锁永不释放，写者只能等满硬上限）。

    13_08 T7 实测故障形态：升级时把本任务读份额让出、写完又「补回 + 另取一份新份额」，
    旧份额没人释放 → 读者的共享锁长期不放 → 写请求排队 30 秒后失败。
    """
    async with gates.gate_scope(gates.PLATFORM_GATE, read_only=False):
        assert gates.gate(gates.PLATFORM_GATE).mode == rwlock.WRITE
    target = gates.gate(gates.PLATFORM_GATE)
    assert target.mode is None
    assert target.depth == 0
    # 有残余读份额时这里会自锁超时，故用短上限验证「门是干净的」
    async with gates.gate_scope(gates.PLATFORM_GATE, read_only=False, wait=1.0):
        assert target.mode == rwlock.WRITE


async def test_upgrade_restores_read_mode() -> None:
    """升级写门期间为写模式，退出后恢复原读状态。"""
    async with gates.gate_scope(gates.PLATFORM_GATE, read_only=True):
        async with gates.gate_scope(gates.PLATFORM_GATE, read_only=False):
            assert gates.gate(gates.PLATFORM_GATE).mode == rwlock.WRITE
        assert gates.gate(gates.PLATFORM_GATE).mode == rwlock.READ
        assert gates.gate(gates.PLATFORM_GATE).depth == 1

    assert gates.gate(gates.PLATFORM_GATE).mode is None


async def test_upgrade_failure_restores_read_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """取写门失败时恢复读份额并原样抛出异常（退出后不残留）。"""
    target = gates.gate(gates.PLATFORM_GATE)

    async def _fail(*, wait: float | None = None) -> None:
        """写门请求直接失败。"""
        raise TimeoutError("boom")

    monkeypatch.setattr(target, "acquire_write", _fail)
    with pytest.raises(TimeoutError, match="boom"):
        async with gates.gate_scope(gates.PLATFORM_GATE, read_only=False):
            pass

    assert target.mode is None
    assert target.depth == 0


async def test_upgrade_timeout_restores_read_share(monkeypatch: pytest.MonkeyPatch) -> None:
    """升级等写门超时（份额已让出）：补回读份额并原样抛出，退出后不残留。"""
    target = gates.gate(gates.PLATFORM_GATE)

    real = target._wait_granted  # pyright: ignore[reportPrivateUsage]

    async def _fail(lease: rwlock._Lease, limit: float) -> None:  # pyright: ignore[reportPrivateUsage]
        """只在等写门时失败；读门走真实实现（保证真持有系统共享锁）。"""
        if lease.write:
            raise TimeoutError("boom")
        await real(lease, limit)

    monkeypatch.setattr(target, "_wait_granted", _fail)
    with pytest.raises(TimeoutError, match="boom"):
        async with gates.gate_scope(gates.PLATFORM_GATE, read_only=False):
            pass

    assert target.mode is None
    assert target.depth == 0


def test_close_gates_drops_singletons() -> None:
    """关闭后再次取门得到新实例（旧句柄已释放）。"""
    first = gates.gate(gates.TENANT_GATE)

    gates.close_gates()
    second = gates.gate(gates.TENANT_GATE)

    assert first is not second


@asynccontextmanager
async def _noop_hook(
    db_key: str, read_only: bool, wait: float | None = None, url: str | None = None
) -> AsyncGenerator[None]:
    """空门钩子（仅用于验证撤销逻辑）。

    Args:
        db_key: 数据源键。
        read_only: 是否只读。
        wait: 等待上限。
        url: 实际库连接串。

    Yields:
        None: 区间。
    """
    del db_key, read_only, wait, url
    yield


def test_pytest_unconfigure_clears_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    """会话结束钩子撤销门钩子并关闭门（覆盖率口径要求该路径被执行）。"""
    monkeypatch.setattr(gate_module, "_hook", gate_module.current_gate_hook())
    gate_module.set_gate_hook(_noop_hook)
    gates.gate(gates.PLATFORM_GATE)
    # 会话结束的「恢复补丁」用替身：直接调真实现会把本进程的自动提交补丁撤掉，影响同 worker 后续用例
    restored: ConcurrentStableList[str] = ConcurrentStableList()
    monkeypatch.setattr(plugin, "_restore_session_factory", lambda: restored.add("session"))
    monkeypatch.setattr(plugin, "_restore_sqlite_connections", lambda: restored.add("sqlite"))

    plugin.pytest_unconfigure(cast("pytest.Config", None))

    assert gate_module.current_gate_hook() is None
    assert set(restored) == {"session", "sqlite"}


async def test_gate_scope_records_hold_when_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """开启持有时长采样后，一次门区间会落一行（含门名与模式）。"""
    from bms_core.testing import diagnostics

    monkeypatch.setenv(diagnostics.HOLD_ENV, "1")
    monkeypatch.chdir(tmp_path)

    async with gates.gate_scope(gates.PLATFORM_GATE, read_only=True):
        pass

    text = (tmp_path / ".cache/test/gate-hold.log").read_text(encoding="utf-8")
    assert gates.PLATFORM_GATE in text
    assert "read" in text


async def test_gate_scope_marks_write_reentry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """嵌套写区间标记为重入：取写门不排队（等写≈0），慢只可能出在门内或 SQLite 锁上。"""
    from bms_core.testing import diagnostics

    monkeypatch.setenv(diagnostics.HOLD_ENV, "1")
    monkeypatch.chdir(tmp_path)
    target = gates.gate(gates.PLATFORM_GATE)

    async with gates.gate_scope(gates.PLATFORM_GATE, read_only=False):
        assert len(target.write_holders()) == 1
        async with gates.gate_scope(gates.PLATFORM_GATE, read_only=False):
            pass

    lines = (tmp_path / ".cache/test/gate-hold.log").read_text(encoding="utf-8").splitlines()
    rows = [line.split("\t") for line in lines]
    # 第 8 列是重入标记：内层 1、外层 0；末列是结果（正常退出为 ok）。
    assert sorted(row[7] for row in rows) == ["0", "1"]
    assert [row[8] for row in rows] == ["ok", "ok"]
    assert len(target.write_holders()) == 0


async def test_read_wait_timeout_is_recorded_as_wait(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """读门等待超时也落一行：等待进「等读」列、实占归零、末列标 `read-timeout`。

    这是 T7 定位口径的一部分：改前 `wait_read` 在 `await` 之后赋值，超时抛异常就跳过，
    180s 等门被算成 180s 实占。
    """
    from bms_core.testing import diagnostics

    monkeypatch.setenv(diagnostics.HOLD_ENV, "1")
    monkeypatch.chdir(tmp_path)
    target = gates.gate(gates.PLATFORM_GATE)

    async def _timeout() -> int:
        """模拟等读门超时。"""
        raise TimeoutError("等待读门超时")

    monkeypatch.setattr(target, "acquire_read", _timeout)
    with pytest.raises(TimeoutError, match="等待读门超时"):
        async with gates.gate_scope(gates.PLATFORM_GATE, read_only=True):
            pass

    cols = (tmp_path / ".cache/test/gate-hold.log").read_text(encoding="utf-8").strip().split("\t")
    assert cols[1] == "read"
    # 等待没有进「实占」列（改前的口径会把整段等待算成实占）；高负载下仍有毫秒级记账开销
    assert float(cols[6]) < 0.5
    assert cols[8] == "read-timeout"


async def test_read_error_is_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """取读门时的非超时异常同样落盘，末列标 `read-error`。"""
    from bms_core.testing import diagnostics

    monkeypatch.setenv(diagnostics.HOLD_ENV, "1")
    monkeypatch.chdir(tmp_path)
    target = gates.gate(gates.PLATFORM_GATE)

    async def _boom() -> int:
        """模拟取读门失败。"""
        raise RuntimeError("读门坏了")

    monkeypatch.setattr(target, "acquire_read", _boom)
    with pytest.raises(RuntimeError, match="读门坏了"):
        async with gates.gate_scope(gates.PLATFORM_GATE, read_only=True):
            pass

    cols = (tmp_path / ".cache/test/gate-hold.log").read_text(encoding="utf-8").strip().split("\t")
    assert cols[8] == "read-error"


async def test_write_wait_timeout_is_recorded_as_wait(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """等写门超时：等待进「等写」列、实占归零、末列标 `write-timeout`。"""
    from bms_core.testing import diagnostics

    monkeypatch.setenv(diagnostics.HOLD_ENV, "1")
    monkeypatch.chdir(tmp_path)
    target = gates.gate(gates.PLATFORM_GATE)

    async def _timeout(*, wait: float | None = None) -> ConcurrentStableList[int]:
        """模拟等写门超时。"""
        del wait
        raise TimeoutError("等待写门超时")

    monkeypatch.setattr(target, "acquire_write", _timeout)
    with pytest.raises(TimeoutError, match="等待写门超时"):
        async with gates.gate_scope(gates.PLATFORM_GATE, read_only=False):
            pass

    cols = (tmp_path / ".cache/test/gate-hold.log").read_text(encoding="utf-8").strip().split("\t")
    assert cols[1] == "write"
    # 实占只剩「释放写门 + 补回读份额」的毫秒级开销，不再包含等门时间。
    assert float(cols[6]) < 0.5
    assert cols[8] == "write-timeout"
    assert target.mode is None
    assert target.depth == 0


async def test_hold_error_is_distinguished(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """门内业务异常记为 `hold-error`，不会被误当成等门超时。"""
    from bms_core.testing import diagnostics

    monkeypatch.setenv(diagnostics.HOLD_ENV, "1")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="业务失败"):
        async with gates.gate_scope(gates.PLATFORM_GATE, read_only=False):
            raise ValueError("业务失败")

    cols = (tmp_path / ".cache/test/gate-hold.log").read_text(encoding="utf-8").strip().split("\t")
    assert cols[1] == "write"
    assert cols[8] == "hold-error"


class _FakeConnection:
    """异步连接替身：记录执行次数与回滚次数（`in_transaction` 恒 False）。"""

    def __init__(self) -> None:
        """初始化计数。"""
        self.executed = 0
        self.rolled_back = 0

    def in_transaction(self) -> bool:
        """恒「不在事务中」（autocommit 连接）。"""
        return False

    async def execute(self, *args: object, **kwargs: object) -> str:
        """执行 SQL。"""
        del args, kwargs
        self.executed += 1
        return "executed"

    async def exec_driver_sql(self, *args: object, **kwargs: object) -> str:
        """执行驱动级 SQL。"""
        del args, kwargs
        self.executed += 1
        return "driver"

    async def scalar(self, *args: object, **kwargs: object) -> int:
        """取标量。"""
        del args, kwargs
        self.executed += 1
        return 7

    async def scalars(self, *args: object, **kwargs: object) -> str:
        """取标量集合。"""
        del args, kwargs
        self.executed += 1
        return "scalars"

    async def rollback(self) -> None:
        """结束自动事务。"""
        self.rolled_back += 1


class _FakeEngine:
    """异步引擎替身：`connect()` / `begin()` 产出同一个假连接。"""

    url = "fake://engine"
    """假引擎连接串（`GatedEngine` 取门时读它，用于按库取名）。"""

    def __init__(self) -> None:
        """初始化连接。"""
        self.connection = _FakeConnection()
        self.disposed = 0

    @asynccontextmanager
    async def connect(self) -> AsyncGenerator[_FakeConnection]:
        """打开连接。"""
        yield self.connection

    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[_FakeConnection]:
        """打开写事务（假实现不开事务）。"""
        yield self.connection

    async def dispose(self) -> None:
        """销毁。"""
        self.disposed += 1


async def test_gated_connection_wraps_each_execution() -> None:
    """门代理连接：每次执行各取放一次门，并在自动事务后立即结束事务。"""
    entered: ConcurrentStableList[bool] = ConcurrentStableList()
    fake = _FakeConnection()

    @asynccontextmanager
    async def _scope() -> AsyncGenerator[None]:
        entered.add(True)
        yield

    connection = gates._GatedConnection(fake, _scope)  # pyright: ignore[reportPrivateUsage]
    assert await connection.execute("stmt") == "executed"
    assert await connection.exec_driver_sql("stmt") == "driver"
    assert await connection.scalar("stmt") == 7
    assert await connection.scalars("stmt") == "scalars"
    assert fake.executed == 4
    assert fake.rolled_back == 4
    assert len(entered) == 4


async def test_gated_engine_connect_and_begin_use_gate() -> None:
    """门代理引擎：`connect()` 的读与 `begin()` 的写都走门，销毁透传。"""
    fake = _FakeEngine()
    engine = gates.GatedEngine(fake, PLATFORM_DB_KEY)

    async with engine.connect() as reader:
        assert await reader.execute("stmt") == "executed"
    async with engine.begin() as writer:
        assert await writer.execute("stmt") == "executed"
    await engine.dispose()
    assert fake.disposed == 1
    assert fake.connection.executed == 2


def test_session_factory_patch_is_idempotent() -> None:
    """会话工厂补丁可重复调用（第二次走早退分支）。"""
    plugin._patch_session_factory_autocommit()  # pyright: ignore[reportPrivateUsage]


def test_patch_sqlite_connections_sets_autocommit_and_pragma(monkeypatch: pytest.MonkeyPatch) -> None:
    """连接补丁：新建连接为自动提交，并关掉 WAL 自动检查点（会话结束后恢复）。"""
    import sqlite3

    original = sqlite3.connect
    monkeypatch.setattr(plugin, "_original_sqlite_connect", None)
    # 用例结束由 monkeypatch 还原，避免把本进程的补丁再套一层
    monkeypatch.setattr(sqlite3, "connect", original)

    plugin._patch_sqlite_connections()  # pyright: ignore[reportPrivateUsage]
    try:
        connection = sqlite3.connect(":memory:")
        try:
            assert connection.isolation_level is None
            assert connection.execute("PRAGMA wal_autocheckpoint").fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        plugin._restore_sqlite_connections()  # pyright: ignore[reportPrivateUsage]

    assert sqlite3.connect is original
    assert plugin._original_sqlite_connect is None  # pyright: ignore[reportPrivateUsage]


def test_restore_session_factory_is_noop_without_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    """未打补丁时恢复是空操作（会话结束路径可重复调用）。"""
    monkeypatch.setattr(plugin, "_original_session_create", None)
    plugin._restore_session_factory()  # pyright: ignore[reportPrivateUsage]


def test_restore_sqlite_connections_is_noop_without_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    """未改写过 `sqlite3.connect` 时恢复是空操作（会话结束路径可重复调用）。"""
    monkeypatch.setattr(plugin, "_original_sqlite_connect", None)
    plugin._restore_sqlite_connections()  # pyright: ignore[reportPrivateUsage]


def test_restore_sqlite_connections_puts_back_original(monkeypatch: pytest.MonkeyPatch) -> None:
    """恢复把 `sqlite3.connect` 换回补丁前的实现，并清空快照。"""
    import sqlite3

    sentinel = sqlite3.connect

    def _passthrough(*args: object, **kwargs: object) -> sqlite3.Connection:
        """透传建连（替身只为验证恢复换回引用）。

        Args:
            *args: 透传。
            **kwargs: 透传。

        Returns:
            sqlite3.Connection: 原实现建出的连接。
        """
        return cast("Any", sentinel)(*args, **kwargs)

    monkeypatch.setattr(plugin, "_original_sqlite_connect", sentinel)
    monkeypatch.setattr(sqlite3, "connect", _passthrough)

    plugin._restore_sqlite_connections()  # pyright: ignore[reportPrivateUsage]

    assert sqlite3.connect is sentinel
    assert plugin._original_sqlite_connect is None  # pyright: ignore[reportPrivateUsage]


def test_restore_session_factory_puts_back_original(monkeypatch: pytest.MonkeyPatch) -> None:
    """恢复把会话工厂的 `create` 换回补丁前的实现，并清空快照。"""
    from bms_core.db.session import SessionFactory

    sentinel = SessionFactory.create

    def _create(*args: object, **kwargs: object) -> None:
        """空替身（只为验证恢复换回引用）。"""
        del args, kwargs

    monkeypatch.setattr(plugin, "_original_session_create", sentinel)
    monkeypatch.setattr(SessionFactory, "create", _create)

    plugin._restore_session_factory()  # pyright: ignore[reportPrivateUsage]

    assert SessionFactory.create is sentinel
    assert plugin._original_session_create is None  # pyright: ignore[reportPrivateUsage]


def test_busy_timeout_from_env_parses_and_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """忙等上限：环境变量缺省 0.1s、合法值生效、非法值回落 0.1s。"""
    monkeypatch.delenv("BMS_TEST_SQLITE_BUSY_TIMEOUT", raising=False)
    assert plugin._busy_timeout_from_env() == 0.1  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setenv("BMS_TEST_SQLITE_BUSY_TIMEOUT", "0.5")
    assert plugin._busy_timeout_from_env() == 0.5  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setenv("BMS_TEST_SQLITE_BUSY_TIMEOUT", "abc")
    assert plugin._busy_timeout_from_env() == 0.1  # pyright: ignore[reportPrivateUsage]


def test_prepare_test_dir_resets_and_warns(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """会话入口准备：先重建共享库，再清临时产物；非锁文件清理失败只告警。"""
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    def _clear_warn(*, include_databases: bool) -> ConcurrentStableList[str]:
        """返回一份「清不掉的临时文件」清单（不含 .lock）。

        Args:
            include_databases: 未使用（与真函数同形）。

        Returns:
            ConcurrentStableList[str]: 失败清单。
        """
        del include_databases
        return ConcurrentStableList(["x.tmp"])

    def _reset_ok() -> ConcurrentStableList[str]:
        """记录一次清场并返回空失败清单。

        Returns:
            ConcurrentStableList[str]: 空清单（共享库已删净）。
        """
        calls.add("reset")
        return ConcurrentStableList()

    monkeypatch.setattr(fixtures, "reset_shared_databases", _reset_ok)
    monkeypatch.setattr(fixtures, "clear_shared_db_files", _clear_warn)
    plugin._prepare_test_dir()  # pyright: ignore[reportPrivateUsage]
    assert list(calls) == ["reset"]
    assert "共享测试库清理失败" in capsys.readouterr().out


def test_prepare_test_dir_fails_on_stuck_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    """会话入口准备：残留 `.lock` 清不掉即阻断（带锁开跑会拖成一堆假超时）。"""

    def _clear_lock(*, include_databases: bool) -> ConcurrentStableList[str]:
        """返回一份残留锁清单。

        Args:
            include_databases: 未使用（与真函数同形）。

        Returns:
            ConcurrentStableList[str]: 失败清单。
        """
        del include_databases
        return ConcurrentStableList(["a.lock"])

    monkeypatch.setattr(fixtures, "reset_shared_databases", lambda: ConcurrentStableList())
    monkeypatch.setattr(fixtures, "clear_shared_db_files", _clear_lock)
    with pytest.raises(RuntimeError, match="残留测试锁清理失败"):
        plugin._prepare_test_dir()  # pyright: ignore[reportPrivateUsage]


def test_collection_modifyitems_skips_without_shared_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """初始化阶段：本次用例用不到共享库时直接返回（纯单元测试不为建库多花数秒）。"""
    prepared: ConcurrentStableList[str] = ConcurrentStableList()

    def _needed(items: object) -> ConcurrentStableList[str]:
        """不需要任何共享库。

        Args:
            items: 收集到的用例（未使用）。

        Returns:
            ConcurrentStableList[str]: 空清单。
        """
        del items
        return ConcurrentStableList()

    def _prepare(names: object) -> ConcurrentStableList[str]:
        """记录被调用（本用例不应发生）。

        Args:
            names: 数据源清单（未使用）。

        Returns:
            ConcurrentStableList[str]: 空清单。
        """
        del names
        prepared.add("called")
        return ConcurrentStableList()

    monkeypatch.setattr(fixtures, "needed_shared_databases", _needed)
    monkeypatch.setattr(fixtures, "prepare_shared_databases", _prepare)
    plugin.pytest_collection_modifyitems(cast("pytest.Config", None), [])
    assert list(prepared) == []


def test_collection_modifyitems_prepares_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    """初始化阶段：按夹具闭包需要共享库时调建库（首个建、其余等就绪）。"""
    prepared: ConcurrentStableList[ConcurrentStableList[str]] = ConcurrentStableList()

    def _needed(items: object) -> ConcurrentStableList[str]:
        """需要平台库。

        Args:
            items: 收集到的用例（未使用）。

        Returns:
            ConcurrentStableList[str]: 数据源清单。
        """
        del items
        return ConcurrentStableList(["platform"])

    def _prepare(names: ConcurrentStableList[str]) -> ConcurrentStableList[str]:
        """记录建库入参。

        Args:
            names: 数据源清单。

        Returns:
            ConcurrentStableList[str]: 空清单。
        """
        prepared.add(ConcurrentStableList(names))
        return ConcurrentStableList()

    monkeypatch.setattr(fixtures, "needed_shared_databases", _needed)
    monkeypatch.setattr(fixtures, "prepare_shared_databases", _prepare)
    plugin.pytest_collection_modifyitems(cast("pytest.Config", None), [])
    assert [list(names) for names in prepared] == [["platform"]]
