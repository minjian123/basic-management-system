"""跨进程读写门语义用例（Kiwi 2533）：多读并发 / 写独占 / 重入 / 超时诊断 / 后端分支。

口径见 `bms_core.testing.rwlock` 模块文档与《测试规范》「并行与隔离」节。
"""

# pyright: reportPrivateUsage=false
# 本文件直接验证模块私有后端（平台分支与超时路径），私有访问是本意。

from __future__ import annotations

import asyncio
import sys
import time
from functools import partial
from pathlib import Path

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing import rwlock

pytestmark = pytest.mark.kiwi_id(2533)


class _FakeFcntl:
    """`fcntl` 替身：记录调用，可按需模拟锁被占用。"""

    LOCK_EX = 1
    LOCK_SH = 2
    LOCK_NB = 4
    LOCK_UN = 8

    def __init__(self) -> None:
        """初始化替身。"""
        self.calls: ConcurrentStableList[tuple[int, int]] = ConcurrentStableList()
        self.busy = False

    def lockf(self, fd: int, operation: int) -> None:
        """记录调用；`busy` 且带非阻塞位时抛 `OSError`。

        Args:
            fd: 文件描述符。
            operation: 操作位。

        Raises:
            OSError: 模拟锁被占用。
        """
        self.calls.append((fd, operation))
        if self.busy and operation & self.LOCK_NB:
            raise OSError("busy")


class _StubBackend:
    """后端替身（覆盖 `_make_backend` 的 Windows 分支，不真调系统接口）。"""

    def __init__(self, path: Path) -> None:
        """记录构造参数。

        Args:
            path: 锁文件路径。
        """
        self.path = path

    def try_acquire(self, *, write: bool) -> bool:
        """恒成功。"""
        del write
        return True

    def release(self) -> None:
        """无操作。"""

    def close(self) -> None:
        """无操作。"""


def _gate(tmp_path: Path, name: str = "unit") -> rwlock.DbGate:
    """建一个独立门（独立锁文件）。

    Args:
        tmp_path: 临时目录。
        name: 门名。

    Returns:
        rwlock.DbGate: 门实例。
    """
    return rwlock.DbGate(name, tmp_path / f"{name}.lock")


def test_gate_path_under_cache_test() -> None:
    """门文件落 `.cache/test/db-gate-<name>.lock`。"""
    path = rwlock.gate_path("platform")

    assert path.name == "db-gate-platform.lock"
    assert path.parent.name == rwlock.DEFAULT_GATE_DIRNAME


def test_make_backend_windows_branch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """平台常量可注入：Windows 分支返回 Windows 后端。"""
    monkeypatch.setattr(rwlock, "_IS_WINDOWS", True)
    monkeypatch.setattr(rwlock, "_WindowsLock", _StubBackend)

    backend = rwlock._make_backend(tmp_path / "win.lock")

    assert isinstance(backend, _StubBackend)
    assert backend.path == tmp_path / "win.lock"


def test_make_backend_posix_branch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """平台常量可注入：非 Windows 分支返回 POSIX 后端（注入替身模块，避免 Windows 无 `fcntl`）。"""
    original = rwlock._PosixLock
    fake = _FakeFcntl()
    monkeypatch.setattr(rwlock, "_IS_WINDOWS", False)
    monkeypatch.setattr(rwlock, "_PosixLock", partial(original, module=fake))

    backend = rwlock._make_backend(tmp_path / "posix.lock")

    assert backend.try_acquire(write=True) is True
    backend.release()
    backend.close()


def test_posix_backend_with_injected_module(tmp_path: Path) -> None:
    """POSIX 后端：覆盖独占 / 共享 / 被占用 / 解锁四个分支。"""
    fake = _FakeFcntl()
    backend = rwlock._PosixLock(tmp_path / "posix.lock", fake)

    assert backend.try_acquire(write=True) is True
    assert fake.calls[-1][1] == fake.LOCK_EX | fake.LOCK_NB
    backend.release()
    assert fake.calls[-1][1] == fake.LOCK_UN
    fake.busy = True
    assert backend.try_acquire(write=False) is False
    assert fake.calls[-1][1] == fake.LOCK_SH | fake.LOCK_NB
    backend.close()


def test_posix_backend_imports_real_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """未注入模块时走真实导入（用 `sys.modules` 替身覆盖该分支）。"""
    fake = _FakeFcntl()
    monkeypatch.setitem(sys.modules, "fcntl", fake)

    backend = rwlock._PosixLock(tmp_path / "posix.lock")

    assert backend._fcntl is fake
    backend.close()


async def test_gate_reentrant_same_mode(tmp_path: Path) -> None:
    """同模式重入只加计数；归零后回到未持有。"""
    gate = _gate(tmp_path)

    await gate.acquire(write=False)
    await gate.acquire(write=False)
    assert gate.mode == rwlock.READ
    assert gate.depth == 2
    await gate.release(write=False)
    assert gate.depth == 1
    await gate.release(write=False)
    assert gate.mode is None
    assert gate.depth == 0


async def test_gate_rejects_cross_mode(tmp_path: Path) -> None:
    """持读门时请求写门直接报错（禁止原地升级）。"""
    gate = _gate(tmp_path)
    await gate.acquire(write=False)
    try:
        with pytest.raises(RuntimeError, match="禁止原地升级"):
            await gate.acquire(write=True)
    finally:
        await gate.release(write=False)


async def test_gate_release_mode_mismatch(tmp_path: Path) -> None:
    """释放模式与持有模式不一致即报错。"""
    gate = _gate(tmp_path)
    await gate.acquire(write=True)
    try:
        with pytest.raises(RuntimeError, match="释放模式不匹配"):
            await gate.release(write=False)
    finally:
        await gate.release(write=True)
    with pytest.raises(RuntimeError, match="释放模式不匹配"):
        await gate.release(write=False)


async def test_release_write_without_holding_raises(tmp_path: Path) -> None:
    """未持写门时释放写门报错。"""
    gate = _gate(tmp_path)

    with pytest.raises(RuntimeError, match="释放模式不匹配"):
        await gate.release(write=True)


async def test_borrowed_read_share_retires_with_write_gate(tmp_path: Path) -> None:
    """写门内借用的读份额随写门作废：写门先释放、读门后释放**不报错**，只销账。

    真实场景：FastAPI 的 yield 依赖把只读会话的生命周期拉到响应结束，读门可能晚于写门释放；
    若此时判「未持有」会把正常请求打成 500（13_08 实测 `RuntimeError: 门 platform 释放模式不匹配`）。
    """
    gate = _gate(tmp_path)
    await gate.acquire(write=True)
    await gate.acquire(write=False)
    assert gate.mode == rwlock.WRITE
    assert gate.depth == 2

    await gate.release(write=True)
    assert gate.mode == rwlock.READ

    await gate.release(write=False)
    assert gate.mode is None


async def test_read_gates_run_concurrently(tmp_path: Path) -> None:
    """两个句柄同时持读门：总耗时接近单个，而不是两倍。"""
    path = tmp_path / "shared.lock"
    first = rwlock.DbGate("first", path)
    second = rwlock.DbGate("second", path)

    async def _hold(gate: rwlock.DbGate) -> None:
        """持读门 50ms。"""
        await gate.acquire(write=False)
        try:
            await asyncio.sleep(0.05)
        finally:
            await gate.release(write=False)

    started = time.monotonic()
    await asyncio.gather(_hold(first), _hold(second))

    assert time.monotonic() - started < 0.095


async def test_write_gate_is_exclusive(tmp_path: Path) -> None:
    """写门持有期间另一写门阻塞，释放后立即获得。"""
    path = tmp_path / "shared.lock"
    holder = rwlock.DbGate("holder", path)
    contender = rwlock.DbGate("contender", path)
    await holder.acquire(write=True)
    waiter = asyncio.create_task(contender.acquire(write=True))
    try:
        await asyncio.sleep(0.05)
        assert not waiter.done()
    finally:
        await holder.release(write=True)
    await asyncio.wait_for(waiter, timeout=2.0)
    await contender.release(write=True)


async def test_gate_timeout_reports_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """等门超过告警阈值先打印一行，超过上限抛 `TimeoutError`。"""
    monkeypatch.setattr(rwlock, "DEFAULT_TIMEOUT", 0.3)
    monkeypatch.setattr(rwlock, "WARN_AFTER", 0.05)
    path = tmp_path / "shared.lock"
    holder = rwlock.DbGate("holder", path)
    contender = rwlock.DbGate("contender", path)
    await holder.acquire(write=True)
    try:
        with pytest.raises(TimeoutError, match="contender"):
            await contender.acquire(write=True)
    finally:
        await holder.release(write=True)

    assert "等待门" in capsys.readouterr().out


def test_gate_close(tmp_path: Path) -> None:
    """关闭门不报错（会话结束路径）。"""
    gate = _gate(tmp_path, "close")

    gate.close()


@pytest.mark.skipif(not rwlock._IS_WINDOWS, reason="仅 Windows 真实字节锁")
def test_windows_release_after_close_raises(tmp_path: Path) -> None:
    """句柄关闭后释放锁报 `OSError`（覆盖释放失败分支）。"""
    backend = rwlock._WindowsLock(tmp_path / "closed.lock")
    backend.close()

    with pytest.raises(OSError):
        backend.release()
