"""跨进程读写门语义用例（Kiwi 2533）：多读并发 / 写独占 / 重入 / 超时诊断 / 后端分支。

口径见 `bms_core.testing.rwlock` 模块文档与《测试规范》「并行与隔离」节。
"""

# pyright: reportPrivateUsage=false
# 本文件直接验证模块私有后端（平台分支与超时路径），私有访问是本意。

from __future__ import annotations

import asyncio
import os
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
    await asyncio.to_thread(lambda: None)
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
        assert restored == (token,)
        assert gate.mode == rwlock.WRITE
    finally:
        await gate.release_write(restored)

    assert gate.mode == rwlock.READ
    assert gate.depth == 1
    await gate.release_read(token)
    assert gate.mode is None


async def test_release_read_token_mismatch_raises(tmp_path: Path) -> None:
    """释放不属于本门的读份额 token 报错（写门未持有时则只告警，见后一条）。"""
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
    """两个句柄同时持读门：总耗时接近单个，而不是两倍。"""
    path = tmp_path / "shared.lock"
    first = rwlock.DbGate("first", path)
    second = rwlock.DbGate("second", path)

    async def _hold(gate: rwlock.DbGate) -> None:
        """持读门 50ms。"""
        token = await gate.acquire_read()
        try:
            await asyncio.sleep(0.05)
        finally:
            await gate.release_read(token)

    started = time.monotonic()
    await asyncio.gather(_hold(first), _hold(second))

    assert time.monotonic() - started < 0.095


async def test_write_gate_blocks_other_task_reads(tmp_path: Path) -> None:
    """写门持有期间，**同一进程的其它任务**取读门必须等它释放（不能读到写一半的数据）。"""
    gate = _gate(tmp_path)
    await gate.acquire_write()
    reader = asyncio.create_task(gate.acquire_read())
    await asyncio.to_thread(lambda: None)
    assert not reader.done(), "写门持有期间其它任务不得拿到读门"

    await gate.release_write()
    token = await asyncio.wait_for(reader, timeout=2.0)
    assert gate.mode == rwlock.READ
    await gate.release_read(token)
    assert gate.mode is None


async def test_write_gate_reentrant(tmp_path: Path) -> None:
    """写门同任务重入只加深度，不重复取内核锁。"""
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


async def test_read_acquire_timeout_resets_kernel_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """读门等锁超时后，内核占位必须复位，下一次取读门仍可成功。"""
    monkeypatch.setattr(rwlock, "DEFAULT_TIMEOUT", 0.2)
    monkeypatch.setattr(rwlock, "WARN_AFTER", 0.05)
    path = tmp_path / "shared.lock"
    holder = rwlock.DbGate("holder", path)
    contender = rwlock.DbGate("contender", path)
    await holder.acquire_write()
    try:
        with pytest.raises(TimeoutError):
            await contender.acquire_read()
    finally:
        await holder.release_write()
    assert contender._kernel_read is False
    token = await contender.acquire_read()
    await contender.release_read(token)
    assert contender.mode is None


async def test_gate_timeout_reports_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """等门超过告警阈值先打印一行，超过上限抛 `TimeoutError`（按任务点名持有者）。"""
    monkeypatch.setattr(rwlock, "DEFAULT_TIMEOUT", 0.3)
    monkeypatch.setattr(rwlock, "WRITE_WAIT_CAP", 0.3)
    monkeypatch.setattr(rwlock, "WARN_AFTER", 0.05)
    path = tmp_path / "shared.lock"
    holder = rwlock.DbGate("holder", path)
    contender = rwlock.DbGate("contender", path)
    await holder.acquire_write()
    try:
        with pytest.raises(TimeoutError, match="contender") as excinfo:
            await contender.acquire_write()
    finally:
        await holder.release_write()

    assert "等待门" in capsys.readouterr().out
    # 点名到任务：光有进程分不清「同进程另一协程也进了写门」
    assert "task=" in str(excinfo.value)


async def test_write_wait_fails_fast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """写门等超过上限立即报错（不再默默等 180s）。"""
    monkeypatch.setattr(rwlock, "WRITE_WAIT_CAP", 0.2)
    monkeypatch.delenv(rwlock.WRITE_WAIT_CAP_ENV, raising=False)
    path = tmp_path / "shared.lock"
    holder = rwlock.DbGate("holder", path)
    contender = rwlock.DbGate("contender", path)
    await holder.acquire_write()
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match="contender"):
            await contender.acquire_write()
    finally:
        await holder.release_write()

    assert time.monotonic() - started < 2.0


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


async def test_write_holders_name_tasks_of_same_process(tmp_path: Path) -> None:
    """写门持有者按**任务**记：同进程两个协程重入时两条都在，先退出的那条即消失。"""
    gate = _gate(tmp_path)
    await gate.acquire_write()
    assert len(gate.write_holders()) == 1

    async def _reenter() -> None:
        """另一任务重入写门并立即退出。"""
        await gate.acquire_write()
        assert len(gate.write_holders()) == 2
        await gate.release_write()

    await asyncio.create_task(_reenter())

    holders = list(gate.write_holders())
    assert len(holders) == 1
    assert "mode=write" in holders[0]
    assert len(gate._describe_holder().split(" | ")) == 1

    await gate.release_write()
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
