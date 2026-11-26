"""跨进程读写门语义用例（Kiwi 2533）：真阻塞等待 / 写门卡住读门 / 重入 / 超时诊断 / 后端分支。

口径见 `bms_core.testing.rwlock` 模块文档与《测试规范》「并行与隔离」节。
"""

# pyright: reportPrivateUsage=false
# 本文件直接验证模块私有后端（平台分支与超时路径），私有访问是本意。

from __future__ import annotations

import asyncio
import os
import sys
import time
import weakref
from functools import partial
from pathlib import Path
from typing import Any, cast

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing import rwlock

pytestmark = pytest.mark.kiwi_id(2533)


class _FakeFcntl:
    """`fcntl` 替身：记录调用，可按需模拟锁被占用。"""

    LOCK_EX = 1
    LOCK_SH = 2
    LOCK_UN = 8

    def __init__(self) -> None:
        """初始化替身。"""
        self.calls: ConcurrentStableList[tuple[int, int]] = ConcurrentStableList()
        self.busy = False

    def flock(self, fd: int, operation: int) -> None:
        """记录调用；`busy` 且不是解锁时抛 `OSError`。

        Args:
            fd: 文件描述符。
            operation: 操作位。

        Raises:
            OSError: 模拟锁被占用。
        """
        self.calls.append((fd, operation))
        if self.busy and operation != self.LOCK_UN:
            raise OSError("busy")


class _StubHeld:
    """已持有锁替身。"""

    def __init__(self) -> None:
        """初始化。"""
        self.released = False

    def release(self) -> None:
        """记录释放。"""
        self.released = True


class _StubBackend:
    """后端替身（覆盖 `_make_backend` 的 Windows 分支，不真调系统接口）。"""

    def __init__(self, path: Path) -> None:
        """记录构造参数。

        Args:
            path: 锁文件路径。
        """
        self.path = path
        self.acquires: ConcurrentStableList[bool] = ConcurrentStableList()

    def acquire(self, *, write: bool) -> _StubHeld:
        """记录模式并恒成功。"""
        self.acquires.append(write)
        return _StubHeld()


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

    held = backend.acquire(write=True)
    assert fake.calls[-1][1] == fake.LOCK_EX
    held.release()
    assert fake.calls[-1][1] == fake.LOCK_UN


def test_posix_backend_with_injected_module(tmp_path: Path) -> None:
    """POSIX 后端：共享 / 独占 / 被占用 / 解锁四个分支。"""
    fake = _FakeFcntl()
    backend = rwlock._PosixLock(tmp_path / "posix.lock", fake)

    held = backend.acquire(write=False)
    assert fake.calls[-1][1] == fake.LOCK_SH
    held.release()
    assert fake.calls[-1][1] == fake.LOCK_UN

    fake.busy = True
    with pytest.raises(OSError, match="busy"):
        backend.acquire(write=True)
    assert fake.calls[-1][1] == fake.LOCK_EX


def test_posix_held_release_is_idempotent(tmp_path: Path) -> None:
    """同一份系统锁重复释放只生效一次（取消路径可能重复调用）。"""
    fake = _FakeFcntl()
    backend = rwlock._PosixLock(tmp_path / "posix.lock", fake)
    held = backend.acquire(write=True)

    held.release()
    calls = len(fake.calls)
    held.release()

    assert len(fake.calls) == calls


def test_posix_backend_imports_real_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """未注入模块时走真实导入（用 `sys.modules` 替身覆盖该分支）。"""
    fake = _FakeFcntl()
    monkeypatch.setitem(sys.modules, "fcntl", fake)

    backend = rwlock._PosixLock(tmp_path / "posix.lock")

    assert backend._fcntl is fake


async def test_gate_reentrant_same_mode(tmp_path: Path) -> None:
    """同模式重入：每份一个 token，全部释放后回到未持有。"""
    gate = _gate(tmp_path)

    first = await gate.acquire_read()
    second = await gate.acquire_read()
    assert gate.mode == rwlock.READ
    assert gate.depth == 2
    await gate.release_read(second)
    assert gate.depth == 1
    await gate.release_read(first)
    assert gate.mode is None
    assert gate.depth == 0


async def test_write_waits_for_other_task_reads(tmp_path: Path) -> None:
    """其它任务持读时，写门**排队**等它们收尾（不报错）。"""
    gate = _gate(tmp_path)
    reading = asyncio.Event()
    finish = asyncio.Event()

    async def _hold() -> None:
        """另一个任务持读份额直到放行。"""
        token = await gate.acquire_read()
        reading.set()
        await finish.wait()
        await gate.release_read(token)

    holder = asyncio.create_task(_hold())
    await reading.wait()
    writer = asyncio.create_task(gate.acquire_write())
    await asyncio.sleep(0.05)
    assert not writer.done(), "有读者时写门必须排队"

    finish.set()
    await holder
    await asyncio.wait_for(writer, timeout=2.0)
    assert gate.mode == rwlock.WRITE
    await gate.release_write()
    assert gate.mode is None


async def test_gate_upgrade_releases_only_own_share(tmp_path: Path) -> None:
    """同任务升级只让出自己的份额，取出写门后按返回的 token 恢复。"""
    gate = _gate(tmp_path)
    token = await gate.acquire_read()

    restored = await gate.acquire_write()
    try:
        assert list(restored) == [token]
        assert gate.mode == rwlock.WRITE
    finally:
        await gate.release_write(restored)

    assert gate.mode == rwlock.READ
    assert gate.depth == 1
    await gate.release_read(token)
    assert gate.mode is None


async def test_release_read_token_mismatch_raises(tmp_path: Path) -> None:
    """释放不属于本门的读份额 token 报错。"""
    gate = _gate(tmp_path)
    await gate.acquire_write()
    try:
        with pytest.raises(RuntimeError, match="未被持有"):
            await gate.release_read(999)
    finally:
        await gate.release_write()
    assert gate.mode is None


async def test_release_write_without_holding_is_tolerated(tmp_path: Path) -> None:
    """未持写门时释放写门只告警、不抛错（`gate_scope` 的 finally 必经此处）。"""
    gate = _gate(tmp_path)

    await gate.release_write()

    assert gate.mode is None


async def test_borrowed_read_share_retires_with_write_gate(tmp_path: Path) -> None:
    """写门内借用的读份额随写门退役：写门先释放、读门后释放**不报错**，只销账。

    真实场景：FastAPI 的 yield 依赖把只读会话的生命周期拉到响应结束，读门可能晚于写门释放；
    若此时判「未持有」会把正常请求打成 500。
    """
    gate = _gate(tmp_path)
    await gate.acquire_write()
    token = await gate.acquire_read()
    assert gate.mode == rwlock.WRITE
    assert gate.depth == 2

    await gate.release_write()
    assert gate.mode is None

    await gate.release_read(token)
    assert gate.mode is None


async def test_read_gates_run_concurrently(tmp_path: Path) -> None:
    """两个句柄同时持读门：总耗时接近单个，而不是两倍（共享锁真并发）。

    判别窗口取「持有 200ms / 阈值 300ms（串行 400ms）」：并行批次的 CPU 争抢会让
    `asyncio.sleep` 明显超时（实测 50ms 变 108ms），窗口太窄会把真并发误判成串行。
    """
    path = tmp_path / "shared.lock"
    first = rwlock.DbGate("first", path)
    second = rwlock.DbGate("second", path)

    async def _hold(gate: rwlock.DbGate) -> None:
        """持读门 200ms。"""
        token = await gate.acquire_read()
        try:
            await asyncio.sleep(0.2)
        finally:
            await gate.release_read(token)

    started = time.monotonic()
    await asyncio.gather(_hold(first), _hold(second))

    assert time.monotonic() - started < 0.3


async def test_write_gate_blocks_other_task_reads(tmp_path: Path) -> None:
    """**写门落锁即同步卡住读门**：写门持有期间同进程其它任务取读门必须阻塞。"""
    gate = _gate(tmp_path)
    await gate.acquire_write()
    reader = asyncio.create_task(gate.acquire_read())
    await asyncio.sleep(0.05)
    assert not reader.done(), "写门持有期间其它任务不得拿到读门"

    await gate.release_write()
    token = await asyncio.wait_for(reader, timeout=2.0)
    assert gate.mode == rwlock.READ
    await gate.release_read(token)
    assert gate.mode is None


async def test_write_gate_blocks_other_instance_reads(tmp_path: Path) -> None:
    """写门持有期间，**另一个门实例**（模拟另一进程 / 另一套连接）的读门也必须阻塞。"""
    path = tmp_path / "shared.lock"
    writer = rwlock.DbGate("writer", path)
    reader = rwlock.DbGate("reader", path)
    await writer.acquire_write()
    pending = asyncio.create_task(reader.acquire_read())
    await asyncio.sleep(0.05)
    assert not pending.done(), "写门独占期间读门不得进入"

    await writer.release_write()
    token = await asyncio.wait_for(pending, timeout=2.0)
    await reader.release_read(token)
    assert reader.mode is None


class _WarningRecorder:
    """日志门面替身：只记下 `warning` 事件名（本模块用 `StdoutLogger`，capsys 抓不到）。"""

    def __init__(self) -> None:
        """初始化事件清单。"""
        self.events: ConcurrentStableList[str] = ConcurrentStableList()

    def warning(self, event: str, **_kwargs: object) -> None:
        """记录一次告警。

        Args:
            event: 事件名。
            **_kwargs: 其余字段（忽略）。
        """
        self.events.add(event)


@pytest.mark.kiwi_id(2538)
async def test_release_write_without_write_warns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """自认为持有却查无账目（重复释放 / 租约丢了）：留一条告警，便于定位「谁把门弄丢了」。"""
    recorder = _WarningRecorder()
    monkeypatch.setattr(rwlock, "_LOGGER", recorder)
    gate = _gate(tmp_path)
    await gate.release_write()
    assert list(recorder.events) == ["gate_release_without_write"]


@pytest.mark.kiwi_id(2539)
async def test_release_write_without_write_quiet_when_expected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """取写门超时后收尾的释放是**预期未持有**：不告警（否则每轮超时都刷一条假警告）。"""
    recorder = _WarningRecorder()
    monkeypatch.setattr(rwlock, "_LOGGER", recorder)
    gate = _gate(tmp_path)
    await gate.release_write(expect_held=False)
    assert list(recorder.events) == []


async def test_write_gate_reentrant(tmp_path: Path) -> None:
    """写门同任务重入只加深度，不重复取系统锁。"""
    gate = _gate(tmp_path)
    await gate.acquire_write()
    restored = await gate.acquire_write()
    assert list(restored) == []
    assert gate.mode == rwlock.WRITE
    assert gate.depth == 2

    await gate.release_write(restored)
    assert gate.depth == 1
    await gate.release_write()
    assert gate.mode is None


async def test_write_gate_is_exclusive(tmp_path: Path) -> None:
    """写门持有期间另一写门阻塞，释放后立即获得。"""
    path = tmp_path / "shared.lock"
    holder = rwlock.DbGate("holder", path)
    contender = rwlock.DbGate("contender", path)
    await holder.acquire_write()
    waiter = asyncio.create_task(contender.acquire_write())
    try:
        await asyncio.sleep(0.05)
        assert not waiter.done()
    finally:
        await holder.release_write()
    await asyncio.wait_for(waiter, timeout=2.0)
    await contender.release_write()


async def test_write_waits_process_writer_and_times_out(tmp_path: Path) -> None:
    """同进程另一任务持写门时，本任务取写门等满上限即失败（不再当成重入直接放行）。"""
    gate = _gate(tmp_path)
    await gate.acquire_write()

    async def _contend() -> None:
        """另一任务取写门（等满上限应失败）。"""
        await gate.acquire_write(wait=0.05)

    contender = asyncio.create_task(_contend())
    try:
        with pytest.raises(TimeoutError, match="等待数据库门超时"):
            await contender
    finally:
        await gate.release_write()
    assert gate.mode is None


async def test_read_waits_process_writer_and_times_out(tmp_path: Path) -> None:
    """同进程另一任务持写门时，本任务取读门等满上限即失败（不读写一半的数据）。"""
    gate = _gate(tmp_path)
    await gate.acquire_write()

    async def _contend() -> None:
        """另一任务取读门（等满上限应失败）。"""
        await gate.acquire_read(wait=0.05)

    contender = asyncio.create_task(_contend())
    try:
        with pytest.raises(TimeoutError, match="等待数据库门超时"):
            await contender
    finally:
        await gate.release_write()
    assert gate.mode is None


async def test_read_timeout_leaves_no_stale_lock(tmp_path: Path) -> None:
    """读门等锁超时后不残留租约：写门释放后下一次取读门立即成功。"""
    monkeypatch_timeout = 0.05
    path = tmp_path / "shared.lock"
    holder = rwlock.DbGate("holder", path)
    contender = rwlock.DbGate("contender", path)
    await holder.acquire_write()
    try:
        with pytest.raises(TimeoutError):
            await contender.acquire_read(wait=monkeypatch_timeout)
    finally:
        await holder.release_write()

    token = await asyncio.wait_for(contender.acquire_read(), timeout=2.0)
    await contender.release_read(token)
    assert contender.mode is None


async def test_reclaims_write_of_finished_task(tmp_path: Path) -> None:
    """持有任务已结束时回收写租约：别的任务取读门不再等满上限。

    真实场景：用例收尾漏放 / 事件循环关闭时 pending 任务不会被自动取消，持有方进程仍活着，
    跨进程的等待者只能等满 10s；必须由持有方自查回收（旧实现在等门循环里做，本轮补回）。
    """
    gate = _gate(tmp_path)

    async def _grab_without_release() -> None:
        """取写门后不释放，任务直接结束。"""
        await gate.acquire_write()

    await asyncio.create_task(_grab_without_release())
    assert gate.mode == rwlock.WRITE

    token = await asyncio.wait_for(gate.acquire_read(), timeout=2.0)
    assert gate.mode == rwlock.READ
    await gate.release_read(token)
    assert gate.mode is None


async def test_reclaims_read_share_of_finished_task(tmp_path: Path) -> None:
    """持有任务已结束时回收读份额：后续写门不被已结束任务的共享锁挡住。"""
    gate = _gate(tmp_path)

    async def _grab_without_release() -> None:
        """取读门后不释放，任务直接结束。"""
        await gate.acquire_read()

    await asyncio.create_task(_grab_without_release())
    assert gate.mode == rwlock.READ

    started = time.monotonic()
    await asyncio.wait_for(gate.acquire_write(wait=1.0), timeout=2.0)
    assert time.monotonic() - started < 0.5
    await gate.release_write()
    assert gate.mode is None


async def test_cancelled_read_wait_releases_granted_lock(tmp_path: Path) -> None:
    """取消等门后，工作线程拿到的共享锁必须立即释放，后续写门能立刻进来。"""
    path = tmp_path / "shared.lock"
    holder = rwlock.DbGate("holder", path)
    contender = rwlock.DbGate("contender", path)
    await holder.acquire_write()
    reader = asyncio.create_task(contender.acquire_read())
    await asyncio.sleep(0.05)
    reader.cancel()
    with pytest.raises(asyncio.CancelledError):
        await reader
    await holder.release_write()

    started = time.monotonic()
    await asyncio.wait_for(contender.acquire_write(wait=1.0), timeout=1.5)
    assert time.monotonic() - started < 0.5
    await contender.release_write()
    assert contender.mode is None


def test_write_wait_cap_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    """上限读取：环境变量优先，非法 / 非正回落默认。"""
    monkeypatch.delenv(rwlock.WRITE_WAIT_CAP_ENV, raising=False)
    assert rwlock.write_wait_cap() == rwlock.WRITE_WAIT_CAP
    monkeypatch.setenv(rwlock.WRITE_WAIT_CAP_ENV, "abc")
    assert rwlock.write_wait_cap() == rwlock.WRITE_WAIT_CAP
    monkeypatch.setenv(rwlock.WRITE_WAIT_CAP_ENV, "0")
    assert rwlock.write_wait_cap() == rwlock.WRITE_WAIT_CAP
    monkeypatch.setenv(rwlock.WRITE_WAIT_CAP_ENV, "1.5")
    assert rwlock.write_wait_cap() == 1.5


async def test_write_wait_cap_fails_at_short_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写门超过短上限（缺省 5s）立即失败并点名持有者，不等 `DEFAULT_TIMEOUT`。"""
    monkeypatch.setattr(rwlock, "WRITE_WAIT_CAP", 0.05)
    monkeypatch.setattr(rwlock, "DEFAULT_TIMEOUT", 5.0)
    monkeypatch.delenv(rwlock.WRITE_WAIT_CAP_ENV, raising=False)
    path = tmp_path / "shared.lock"
    holder = rwlock.DbGate("holder", path)
    contender = rwlock.DbGate("contender", path)
    await holder.acquire_write()
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match="contender") as excinfo:
            await contender.acquire_write()
    finally:
        await holder.release_write()

    elapsed = time.monotonic() - started
    assert 0.04 <= elapsed < 1.5
    assert "等待数据库门超时" in str(excinfo.value)
    # 点名到任务：光有进程分不清「同进程另一协程也进了写门」
    assert "task=" in str(excinfo.value)


async def test_hold_over_threshold_prints_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """持门超过 1s（用例里缩短阈值）常开告警：直接打印并点名持有任务。"""
    monkeypatch.setattr(rwlock, "WARN_AFTER", 0.05)
    gate = _gate(tmp_path)
    token = await gate.acquire_read()
    try:
        await asyncio.sleep(0.15)
    finally:
        await gate.release_read(token)

    out = capsys.readouterr().out
    assert "[rwlock]" in out
    assert "已持有" in out
    assert "疑似长区间" in out


async def test_holder_description_lists_holder_and_clears_on_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """持有者诊断：未释放时按任务列出 pid/mode/用例名，释放后不再列为持有。"""
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/sample.py::test_holder (call)")
    gate = _gate(tmp_path)
    await gate.acquire_write()

    text = gate._describe_holder()
    assert "mode=write" in text
    assert "task=" in text
    assert "tests/sample.py::test_holder" in text

    await gate.release_write()
    assert "无（可能刚释放" in gate._describe_holder()


def test_pid_from_name_reads_trailing_number() -> None:
    """持有者文件名末段是 pid：非数字末段判不出，返回 None。"""
    assert rwlock._pid_from_name("db-gate-platform.holder-123") == 123
    assert rwlock._pid_from_name("db-gate-platform.taskholds-456") == 456
    assert rwlock._pid_from_name("db-gate-platform.holder-abc") is None


def test_pid_alive_rejects_non_positive() -> None:
    """非正数不是有效 pid（读不到文件末段时的兜底）。"""
    assert rwlock._pid_alive(0) is False


def test_pid_alive_reports_missing_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """进程已退出：`ProcessLookupError` 判为不存在。"""

    def _gone(pid: int, signal: int) -> None:
        """模拟目标进程已退出。"""
        del pid, signal
        raise ProcessLookupError

    monkeypatch.setattr(rwlock, "_IS_WINDOWS", False)
    monkeypatch.setattr(rwlock, "_pid_probe", _gone)

    assert rwlock._pid_alive(4242) is False


def test_pid_alive_treats_permission_error_as_alive(monkeypatch: pytest.MonkeyPatch) -> None:
    """无权探测（别人的进程）说明进程存在，判为存活。"""

    def _denied(pid: int, signal: int) -> None:
        """模拟无权限探测。"""
        del pid, signal
        raise PermissionError

    monkeypatch.setattr(rwlock, "_IS_WINDOWS", False)
    monkeypatch.setattr(rwlock, "_pid_probe", _denied)

    assert rwlock._pid_alive(1) is True


def test_pid_alive_accepts_live_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """探测成功即判存活（不真发信号：注入探针）。

    Windows 上绝不能真调 `os.kill(pid, 0)`——那会直接杀掉目标进程，故探针一律注入。
    """
    probes: ConcurrentStableList[tuple[int, int]] = ConcurrentStableList()

    def _probe(pid: int, signal: int) -> None:
        """记录探测参数，不发信号。"""
        probes.append((pid, signal))

    monkeypatch.setattr(rwlock, "_IS_WINDOWS", False)
    monkeypatch.setattr(rwlock, "_pid_probe", _probe)

    assert rwlock._pid_alive(4242) is True
    assert list(probes) == [(4242, 0)]


def test_pid_alive_windows_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows 走 `OpenProcess` 实现（注入替身，不真调系统接口）。"""

    def _only_42_alive(pid: int) -> bool:
        """替身：只把 42 判为存活。"""
        return pid == 42

    monkeypatch.setattr(rwlock, "_IS_WINDOWS", True)
    monkeypatch.setattr(rwlock, "_windows_pid_alive", _only_42_alive)

    assert rwlock._pid_alive(42) is True
    assert rwlock._pid_alive(43) is False


def test_test_id_falls_back_to_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """取不到用例名时给「未知」，不抛错。"""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    assert rwlock.DbGate._test_id() == "未知"


def test_holder_lines_skips_unreadable_and_released(tmp_path: Path) -> None:
    """记录行读取：读不到返回空清单；空行与「已释放」标记不算持有。"""
    assert len(rwlock._holder_lines(tmp_path / "missing")) == 0
    directory = tmp_path / "as-dir"
    directory.mkdir()
    assert len(rwlock._holder_lines(directory)) == 0

    record = tmp_path / "record"
    record.write_text("\npid=1 hold=0 test=x\npid=2 mode=read hold=1 test=y\n", encoding="utf-8")
    assert list(rwlock._holder_lines(record)) == ["pid=2 mode=read hold=1 test=y"]


def test_untrack_read_ignores_unknown_task(tmp_path: Path) -> None:
    """未知任务的读份额注销直接返回（收尾跨任务释放的兜底）。"""
    gate = _gate(tmp_path)

    gate._untrack_read(12345)

    assert len(gate._read_tasks) == 0


async def test_holder_tasks_lists_read_share(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """读持有者也参与点名：同任务多个份额合并成一条并按份额数计深度。"""
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/sample.py::test_read (call)")
    gate = _gate(tmp_path)
    first = await gate.acquire_read()
    second = await gate.acquire_read()

    holders = list(gate.holder_tasks())
    assert len(holders) == 1
    assert "mode=read" in holders[0]
    assert "depth=2" in holders[0]
    assert "tests/sample.py::test_read" in holders[0]

    await gate.release_read(first)
    assert "depth=1" in next(iter(gate.holder_tasks()))
    await gate.release_read(second)
    assert len(gate.holder_tasks()) == 0


async def test_describe_holder_ignores_legacy_line_when_tasks_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """有任务级记录时不再采信进程级那一行（避免同一次持有被点名两次）。"""
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/sample.py::test_dup (call)")
    gate = _gate(tmp_path)
    await gate.acquire_write()
    me = os.getpid()
    legacy = gate._holder_path.with_name(f"{gate._holder_path.name}-{me}")
    legacy.write_text(f"pid={me} mode=read hold=1 test=legacy at=00:00:00", encoding="utf-8")

    text = gate._describe_holder()
    assert "test=legacy" not in text
    assert "tests/sample.py::test_dup" in text

    await gate.release_write()


async def test_write_holders_name_only_owning_task(tmp_path: Path) -> None:
    """写门持有者按**任务**记：别的任务取写门必须排队，不会出现在持有者里。"""
    gate = _gate(tmp_path)
    await gate.acquire_write()
    assert len(gate.write_holders()) == 1

    entered = asyncio.Event()

    async def _contend() -> None:
        """另一任务取写门：必须等主任务释放。"""
        await gate.acquire_write()
        entered.set()
        await gate.release_write()

    contender = asyncio.create_task(_contend())
    await asyncio.sleep(0.05)
    assert not entered.is_set(), "别的任务不得重入写门"
    assert len(gate.write_holders()) == 1

    await gate.release_write()
    await asyncio.wait_for(contender, timeout=2.0)
    assert entered.is_set()
    # 全部释放：任务记录被清空（写空文件而不删，避免抹掉共用同一把锁的其它实例的记录）
    assert gate._task_hold_path().read_text(encoding="utf-8") == ""


def test_gate_close_removes_holder_files(tmp_path: Path) -> None:
    """关闭门顺手清掉本进程的两份持有者记录。"""
    gate = _gate(tmp_path, "closing")
    gate._task_hold_path().write_text("pid=1 mode=write\n", encoding="utf-8")
    gate._holder_file().write_text("pid=1 mode=read hold=1 test=x at=00:00:00", encoding="utf-8")

    gate.close()

    assert not gate._task_hold_path().exists()
    assert not gate._holder_file().exists()


def test_gate_close(tmp_path: Path) -> None:
    """关闭门不报错（会话结束路径），且可再次使用（重开会话）。"""
    gate = _gate(tmp_path, "close")

    gate.close()
    gate.close()


async def test_describe_holder_skips_unreadable_entry(tmp_path: Path) -> None:
    """持有者诊断遇到读不了的文件只跳过，不抛错。"""
    gate = _gate(tmp_path)
    broken = gate._holder_path.with_name(f"{gate._holder_path.name}-999")
    broken.mkdir(parents=True)

    assert "无（可能刚释放" in gate._describe_holder()


async def test_describe_holder_lists_live_entry(tmp_path: Path) -> None:
    """持有者诊断列出仍持有（hold=1）且 pid 存活的记录。"""
    gate = _gate(tmp_path)
    me = os.getpid()
    live = gate._holder_path.with_name(f"{gate._holder_path.name}-{me}")
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_text(f"pid={me} mode=read hold=1 test=x at=00:00:00", encoding="utf-8")

    assert f"pid={me}" in gate._describe_holder()


async def test_describe_holder_filters_dead_pid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """死进程留下的记录不参与点名（本轮实测 holder 目录残留 117 份死进程记录）。"""

    def _dead_only(stale_pid: int) -> bool:
        """替身：只把 999999 判为已退出（其余照常）。"""
        return stale_pid != 999999

    gate = _gate(tmp_path)
    stale = gate._holder_path.with_name(f"{gate._holder_path.name}-999999")
    stale.write_text("pid=999999 mode=write hold=1 test=gone at=00:00:00", encoding="utf-8")
    monkeypatch.setattr(rwlock, "_pid_alive", _dead_only)

    assert "无（可能刚释放" in gate._describe_holder()


async def test_release_write_without_hold_restores_outer_shares(tmp_path: Path) -> None:
    """未持写门却带了外层份额：只告警，并把份额补回来（取写门失败的收尾）。"""
    gate = _gate(tmp_path)
    token = await gate.acquire_read()
    await gate.release_read(token)

    await gate.release_write(ConcurrentStableList((token,)))

    assert gate.owns(token)
    await gate.release_read(token)
    assert gate.mode is None


async def test_release_write_now_is_sync_and_idempotent(tmp_path: Path) -> None:
    """同步释放写门：立即清账目与系统锁；未持有时只返回待恢复份额。"""
    gate = _gate(tmp_path)
    await gate.acquire_write()
    assert gate.release_write_now() == ()
    assert gate.mode is None

    restored = gate.release_write_now()
    assert list(restored) == []
    assert gate.mode is None


async def test_ensure_loop_reclaims_previous_loop_locks(tmp_path: Path) -> None:
    """事件循环切换时回收上一循环残留的系统锁（新循环从干净状态开始）。"""
    gate = _gate(tmp_path)
    leaked = await gate.acquire_read()
    assert gate._loop_ref is not None
    other_loop = asyncio.new_event_loop()
    gate._loop_ref = weakref.ref(other_loop)
    try:
        token = await asyncio.wait_for(gate.acquire_read(), timeout=2.0)
        assert gate.depth == 1, "上一循环的读份额必须被回收"
        assert not gate.owns(leaked)
        await gate.release_read(token)
    finally:
        other_loop.close()
    assert gate.mode is None


class _StaticBackend:
    """后端替身：恒授予给定锁。"""

    def __init__(self, held: _StubHeld) -> None:
        """记录要返回的锁。

        Args:
            held: 已持有锁替身。
        """
        self._held = held

    def acquire(self, *, write: bool) -> _StubHeld:
        """恒返回给定锁（记录模式）。

        Args:
            write: 写门 True。

        Returns:
            _StubHeld: 已持有锁替身。
        """
        del write
        return self._held


class _RaisingBackend:
    """后端替身：取锁即抛错（模拟系统调用失败）。"""

    def acquire(self, *, write: bool) -> _StubHeld:
        """抛错。

        Args:
            write: 写门 True。

        Raises:
            OSError: 固定异常。
        """
        del write
        raise OSError("boom")


def _lease(loop: asyncio.AbstractEventLoop, *, token: int = 1, write: bool = False) -> rwlock._Lease:
    """构造一条取门租约（用例直接驱动租约状态机）。

    Args:
        loop: 所属事件循环。
        token: 份额 / 租约编号。
        write: 写门 True。

    Returns:
        rwlock._Lease: 租约。
    """
    return rwlock._Lease(token=token, task=0, write=write, loop=loop, event=asyncio.Event(), started=time.monotonic())


async def test_gate_reuse_after_close_resets_state(tmp_path: Path) -> None:
    """`close()` 后再次使用：重置队列与工作线程（同一会话多次开关门不残留状态）。"""
    gate = _gate(tmp_path)
    gate.close()
    token = await asyncio.wait_for(gate.acquire_read(), timeout=2.0)
    await gate.release_read(token)
    gate.close()


def test_ensure_loop_reclaims_write_and_timer_of_closed_loop(tmp_path: Path) -> None:
    """上一循环留下的写门 + 告警定时器：新循环取门时一并回收（不残留系统锁）。"""
    gate = _gate(tmp_path)

    async def _hold_write() -> None:
        await gate.acquire_write()
        # 故意不释放：模拟任务在循环关闭前被中断

    asyncio.run(_hold_write())
    assert gate._write_depth == 1

    async def _take_read() -> None:
        token = await asyncio.wait_for(gate.acquire_read(), timeout=2.0)
        assert gate.depth == 1, "上一循环的写门必须被回收"
        await gate.release_read(token)

    asyncio.run(_take_read())
    assert gate.mode is None


async def test_reclaim_turns_borrowed_reads_into_retired(tmp_path: Path) -> None:
    """写门持有任务结束后回收：借用读转为「已退役」（之后释放只销账）。"""
    gate = _gate(tmp_path)

    async def _hold_and_finish() -> None:
        await gate.acquire_write()
        await gate.acquire_read()  # 借用份额（随写门作废）

    await asyncio.create_task(_hold_and_finish())
    assert gate._borrowed_reads

    token = await asyncio.wait_for(gate.acquire_read(), timeout=2.0)
    assert gate._retired_reads, "借用读须转为已退役，后续释放只销账"
    await gate.release_read(token)


async def test_backend_error_propagates_to_waiter(tmp_path: Path) -> None:
    """系统调用异常：由工作线程回传给等待方（协程按原异常抛出）。"""
    gate = _gate(tmp_path)
    gate._backend = cast("Any", _RaisingBackend())
    with pytest.raises(OSError, match="boom"):
        await asyncio.wait_for(gate.acquire_write(), timeout=3.0)


async def test_wait_granted_propagates_error_and_abandon(tmp_path: Path) -> None:
    """等待侧：租约带系统异常时抛出原异常；已放弃（授予 / 弃约并发）时报等待失败。"""
    gate = _gate(tmp_path)
    loop = asyncio.get_running_loop()

    failed = _lease(loop)
    failed.error = OSError("boom")
    failed.event.set()
    with pytest.raises(OSError, match="boom"):
        await gate._wait_granted(failed, 1.0)
    assert failed.error is None

    abandoned = _lease(loop, token=2)
    abandoned.abandoned = True
    abandoned.event.set()
    with pytest.raises(TimeoutError, match="租约已放弃"):
        await gate._wait_granted(abandoned, 1.0)


async def test_deliver_and_abandon_release_leftover_locks(tmp_path: Path) -> None:
    """租约已放弃 / 超时弃约：已授予的系统锁就地释放（不留残锁）。"""
    gate = _gate(tmp_path)
    loop = asyncio.get_running_loop()

    delivered = _StubHeld()
    delivered_lease = _lease(loop)
    delivered_lease.lock = cast("Any", delivered)
    delivered_lease.abandoned = True
    gate._deliver(delivered_lease)
    assert delivered.released

    abandoned = _StubHeld()
    abandoned_lease = _lease(loop, token=2)
    abandoned_lease.lock = cast("Any", abandoned)
    gate._abandon(abandoned_lease)
    assert abandoned.released


def test_acquire_blocking_releases_when_loop_closed(tmp_path: Path) -> None:
    """工作线程授予时循环已关闭：立即释放系统锁（不让锁跟着死循环留着）。"""
    gate = _gate(tmp_path)
    held = _StubHeld()
    gate._backend = cast("Any", _StaticBackend(held))
    loop = asyncio.new_event_loop()
    loop.close()
    gate._acquire_blocking(_lease(loop, write=True))
    assert held.released is True


async def test_write_failure_restores_reads_silently(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """取写门失败时补回已让出的读份额；补回本身失败也不掩盖原始错误。"""
    gate = _gate(tmp_path)
    token = await gate.acquire_read()

    async def _boom(tokens: object) -> None:
        del tokens
        raise RuntimeError("restore boom")

    monkeypatch.setattr(gate, "restore_reads", _boom)
    gate._backend = cast("Any", _RaisingBackend())
    with pytest.raises(OSError, match="boom"):
        await asyncio.wait_for(gate.acquire_write(), timeout=3.0)
    assert not gate.owns(token)


async def test_hold_warning_covers_live_and_stale(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """持门告警：写 / 读存活各打一行；账目已清则静默。"""
    gate = _gate(tmp_path)
    gate._write_depth = 1
    gate._write_owner = rwlock._task_key()
    gate._warn_hold(1, time.monotonic() - 2, read_only=False)

    gate._own_reads[2] = rwlock._task_key()
    gate._warn_hold(2, time.monotonic() - 2, read_only=True)
    gate._warn_hold(3, time.monotonic() - 2, read_only=True)  # 账目已清：静默

    assert capsys.readouterr().out.count("已持有") == 2


async def test_wait_warning_skips_settled_lease(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """等门告警：仍在等才打一行；已授予 / 已放弃静默。"""
    gate = _gate(tmp_path)
    lease = _lease(asyncio.get_running_loop(), write=True)
    gate._warn_wait(lease)
    lease.abandoned = True
    gate._warn_wait(lease)
    lease.abandoned = False
    lease.granted = True
    gate._warn_wait(lease)

    assert capsys.readouterr().out.count("等待门") == 1


async def test_close_releases_write_lock_and_timer(tmp_path: Path) -> None:
    """关闭门时释放仍持有的写门并取消告警定时器（会话结束不留锁）。"""
    gate = _gate(tmp_path)
    await gate.acquire_write()
    assert gate._write_lock is not None
    assert gate._write_timer is not None
    gate.close()
    assert gate.mode is None
    assert gate._write_lock is None
    assert gate._write_timer is None


async def test_schedule_hold_timer_registers_both_modes(tmp_path: Path) -> None:
    """持门告警定时器：读 / 写各自登记一份。"""
    gate = _gate(tmp_path)
    gate._schedule_hold_timer(1, time.monotonic(), read_only=True)
    gate._schedule_hold_timer(2, time.monotonic(), read_only=False)
    assert 1 in gate._read_timers
    assert gate._write_timer is not None
    gate.close()


async def test_ensure_loop_abandons_pending_leases(tmp_path: Path) -> None:
    """事件循环切换：尚未授予的租约统一标记放弃（旧循环的等待方不会再被唤起）。"""
    gate = _gate(tmp_path)
    lease = _lease(asyncio.get_running_loop(), token=99)
    gate._pending[lease.token] = lease
    other_loop = asyncio.new_event_loop()
    gate._loop_ref = weakref.ref(other_loop)
    try:
        token = await asyncio.wait_for(gate.acquire_read(), timeout=2.0)
        await gate.release_read(token)
    finally:
        other_loop.close()
    assert lease.abandoned is True
