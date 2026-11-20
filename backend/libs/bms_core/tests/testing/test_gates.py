"""数据库门上下文用例（Kiwi 2533）：单例、读门 / 写门、升级顺序与关闭。

口径见 `bms_core.testing.gates` 模块文档与《测试规范》「并行与隔离」节。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db import gate as gate_module
from bms_core.db.registry import PLATFORM_DB_KEY
from bms_core.testing import gates, plugin, rwlock

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


def test_gate_is_singleton() -> None:
    """全库共用一把门：不同数据源取到同一实例（13_08 T7 消除跨库互等）。"""
    assert gates.gate(gates.PLATFORM_GATE) is gates.gate(gates.PLATFORM_GATE)
    assert gates.gate(gates.PLATFORM_GATE) is gates.gate(gates.TENANT_GATE)
    assert gates.gate(gates.PLATFORM_GATE).name == gates.GLOBAL_GATE


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


async def test_cross_db_write_does_not_deadlock() -> None:
    """跨库反向嵌套取写门不再互等：全库一把门，只能串行完成，不会出现 ABBA 死锁。

    13_08 T7 实测（24 路并行）：进程 A 持平台写门又等租户门、进程 B 持租户写门又等平台门，
    两边各卡 30 秒把整批拖垮。合成一把门后同样的调用顺序只能排队。
    """
    done: ConcurrentStableList[str] = ConcurrentStableList()

    async def _nested(tag: str, first: str, second: str) -> None:
        async with (
            gates.gate_scope(first, read_only=False, wait=10.0),
            gates.gate_scope(second, read_only=False, wait=10.0),
        ):
            done.add(tag)

    await asyncio.wait_for(
        asyncio.gather(
            _nested("a", gates.PLATFORM_GATE, gates.TENANT_GATE),
            _nested("b", gates.TENANT_GATE, gates.PLATFORM_GATE),
        ),
        timeout=30.0,
    )
    assert sorted(done) == ["a", "b"]
    assert gates.gate(gates.PLATFORM_GATE).mode is None


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
    async with gates.gate_scope(gates.TENANT_GATE, read_only=False, wait=1.0):
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

    real = target._wait_and_lock  # pyright: ignore[reportPrivateUsage]

    async def _fail(wait_write: bool, *, cap: float | None = None) -> None:
        """只在等写门时失败；读门走真实实现（保证真持有内核共享锁）。"""
        if wait_write:
            raise TimeoutError("boom")
        await real(wait_write)

    monkeypatch.setattr(target, "_wait_and_lock", _fail)
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
async def _noop_hook(db_key: str, read_only: bool, wait: float | None = None) -> AsyncGenerator[None]:
    """空门钩子（仅用于验证撤销逻辑）。

    Args:
        db_key: 数据源键。
        read_only: 是否只读。

    Yields:
        None: 区间。
    """
    del db_key, read_only
    yield


def test_pytest_unconfigure_clears_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    """会话结束钩子撤销门钩子并关闭门（覆盖率口径要求该路径被执行）。"""
    monkeypatch.setattr(gate_module, "_hook", gate_module.current_gate_hook())
    gate_module.set_gate_hook(_noop_hook)
    gates.gate(gates.PLATFORM_GATE)

    plugin.pytest_unconfigure(cast("pytest.Config", None))

    assert gate_module.current_gate_hook() is None


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
