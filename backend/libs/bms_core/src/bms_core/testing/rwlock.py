"""跨进程数据库访问读写门（13_08）：读者共享、写者独占，等待是真阻塞。

**写门落锁即同步卡住读门**（硬不变量）：写门一旦被系统锁授予，内核保证此刻没有任何共享锁
持有者；写门持有期间，同进程其它任务与其它进程的读门都阻塞在系统调用上。唯一例外是写门
**持有任务自己**的读——走「借用读份额」，不取系统锁。

为什么必须由系统锁裁决：Windows 对同一句柄重复加锁会把共享 / 独占模式合并（一次解锁整体放掉），
POSIX 记录锁按**进程**生效（同进程不同 fd 不互斥）。两者都会在同进程内漏过读。故每次取门都
独立打开句柄，由 `LockFileEx` / `flock` 在「打开的文件描述」之间互斥，同进程与跨进程走同一条
系统锁队列。

等待方式（2026-11-22 按业主伪代码重做）：

- **真阻塞，不轮询**：阻塞系统调用放在每把门**一条专用守护线程**里（`queue.SimpleQueue` 取任务），
  协程只 `await` 结果；释放由持有方同步执行、不进队列（否则写者阻塞时放锁请求会排在它后面，
  构成自等待）；不用公共线程池——池满会变成新的排队点，退出时 join 还可能被阻塞线程卡住；
- **租约先分配后阻塞**：token 在发起取门前就登记，协程在任一 `await` 上被取消都能凭已知 token
  销账；线程拿到锁后若发现租约已放弃，立即解锁并关句柄；
- 超时由协程侧计时：写门 5s、读门 10s；超时只放弃租约，阻塞中的线程拿到锁后自行释放；
- 持门超过 1s 常开告警（门名 / 用例 / 持有者 / 已持时长 / 取门栈），不再依赖采样开关。

平台差异：

- Windows：`LockFileEx`（共享不带标志，独占带 `LOCKFILE_EXCLUSIVE_LOCK`；阻塞形式，不带
  `LOCKFILE_FAIL_IMMEDIATELY`），`UnlockFileEx` 后关闭句柄；
- POSIX：`flock`（`LOCK_SH` / `LOCK_EX` 阻塞形式），`LOCK_UN` 后关闭 fd。

进程退出内核自动释放，没有心跳线程、陈旧判定与放锁重试。
"""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import itertools
import logging
import os
import queue
import sys
import threading
import time
import weakref
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, Protocol, cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.testing import diagnostics
from bms_core.testing.paths import project_root

DEFAULT_TIMEOUT: Final = 10.0
"""读门等门上限（秒）：超过即报错，不静默降级。

测试等待超过 10s 本身就是「用例写得不好 / 有任务长期持门」的信号，报错比继续等更有用。
"""

WRITE_WAIT_CAP: Final = 5.0
"""写门等门上限（秒）：超过即失败并点名持有者。

正常写是毫秒级，等超过几秒就不是「排队」而是「有人长期持门」——报错比继续等更有用。
整段临界区（建表 / 用例级独占等）经显式 `cap` 放宽，不走本缺省。
"""

WRITE_WAIT_CAP_ENV: Final = "BMS_TEST_GATE_WRITE_WAIT"
"""写门等待上限的环境变量覆盖（秒；缺省用 `WRITE_WAIT_CAP`）。"""

WARN_AFTER: Final = 1.0
"""持门告警阈值（秒）：持有满 1s 立即打印一行并点名持有者（常开）。"""

DEFAULT_GATE_DIRNAME: Final = "test"
"""门文件所在目录名（`<工程根>/.cache/test/`，与共享测试库同区）。"""

_LOGGER = logging.getLogger(__name__)
"""门自身诊断日志（未持写门却释放等）。"""

Mode = Literal["read", "write"]
"""门模式（读共享 / 写独占）。"""

GATE_LABEL: ContextVar[str] = ContextVar("bms_db_gate_label", default="")
"""诊断标签（当前任务正在取哪把逻辑门：`platform` / `tenant`）。

全库共用一把内核门，门实例自己的名字恒为 `all`；日志与栈转储要写「用户视角的门名」才定位
得到现场，故由 `gate_scope` 在取门前按任务上下文设置，`_log_wait` / `_note_gate_wait` 读它、
缺省回落实例名。
"""


def gate_label(fallback: str) -> str:
    """取当前任务的逻辑门名（未设置时回落实例名）。

    Args:
        fallback: 实例名。

    Returns:
        str: 诊断用门名。
    """
    return GATE_LABEL.get() or fallback


READ: Final[Mode] = "read"
"""读门模式名。"""

WRITE: Final[Mode] = "write"
"""写门模式名。"""

_LOCKFILE_EXCLUSIVE_LOCK: Final = 0x0002
_ERROR_NOT_LOCKED: Final = 158
"""`UnlockFileEx` 报告「该区间本来就没加锁」（幂等释放时忽略）。"""

_IS_WINDOWS: Final = sys.platform == "win32"
"""是否 Windows（模块常量便于用例注入另一平台分支）。"""


class _Overlapped(ctypes.Structure):
    """Windows `OVERLAPPED` 结构（仅字节区间锁所需字段）。"""

    _fields_ = (
        ("Internal", ctypes.c_void_p),
        ("InternalHigh", ctypes.c_void_p),
        ("Offset", ctypes.c_uint32),
        ("OffsetHigh", ctypes.c_uint32),
        ("hEvent", ctypes.c_void_p),
    )


class HeldLock(Protocol):
    """一次取门拿到的系统锁（持有者凭它解锁并关闭本次句柄）。"""

    def release(self) -> None:
        """释放锁并关闭句柄（幂等）。"""
        ...


class _Backend(Protocol):
    """平台锁后端（Windows 字节锁 / POSIX flock）。"""

    def acquire(self, *, write: bool) -> HeldLock:
        """**阻塞**取锁，直到拿到为止。

        Args:
            write: 独占锁 True，共享锁 False。

        Returns:
            HeldLock: 已持有的系统锁。
        """
        ...


_windows_functions: tuple[Any, Any] | None = None
"""`LockFileEx` / `UnlockFileEx` 的配置缓存（模块级只配一次）。"""


def _win_functions() -> tuple[Any, Any]:
    """取并配置 `LockFileEx` / `UnlockFileEx`。

    Returns:
        tuple[object, object]: （加锁函数, 解锁函数）。
    """
    global _windows_functions
    if _windows_functions is not None:
        return _windows_functions
    windll = cast("Any", ctypes).WinDLL
    kernel32 = windll("kernel32", use_last_error=True)
    lock = kernel32.LockFileEx
    lock.argtypes = (
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.POINTER(_Overlapped),
    )
    lock.restype = ctypes.c_int
    unlock = kernel32.UnlockFileEx
    unlock.argtypes = (
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.POINTER(_Overlapped),
    )
    unlock.restype = ctypes.c_int
    _windows_functions = (lock, unlock)
    return _windows_functions


class _WindowsHeld:  # pragma: no cover - 仅 Windows 可达（CI 与覆盖率门禁在 Linux）
    """Windows 已持有的字节区间锁（解锁后关闭本次句柄）。"""

    def __init__(self, fd: int, handle: int) -> None:
        """初始化。

        Args:
            fd: 本次取门独立打开的文件描述符。
            handle: 对应的系统句柄。
        """
        self._fd = fd
        self._handle = handle
        self._released = False

    def release(self) -> None:
        """释放锁并关闭句柄（幂等）。"""
        if self._released:
            return
        self._released = True
        _, unlock = _win_functions()
        overlapped = _Overlapped()
        released = unlock(self._handle, 0, 1, 0, ctypes.byref(overlapped))  # pyright: ignore[reportCallIssue]
        if not released:
            last_error = cast("Any", ctypes).get_last_error()
            if last_error != _ERROR_NOT_LOCKED:
                _LOGGER.warning("windows_unlock_failed", extra={"error": last_error})
        with contextlib.suppress(OSError):
            os.close(self._fd)


class _WindowsLock:  # pragma: no cover - 仅 Windows 可达（CI 与覆盖率门禁在 Linux）
    """Windows 字节区间锁（`LockFileEx` 阻塞形式，每次取门独立句柄）。"""

    def __init__(self, path: Path) -> None:
        """记录锁文件路径。

        Args:
            path: 锁文件路径（内容为空，仅作锁载体）。
        """
        self._path = path

    def acquire(self, *, write: bool) -> HeldLock:
        """阻塞取锁。

        Args:
            write: 独占锁 True，共享锁 False。

        Returns:
            HeldLock: 已持有的系统锁。

        Raises:
            OSError: 系统调用失败。
        """
        import msvcrt

        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            handle = int(cast("Any", msvcrt).get_osfhandle(fd))
            lock, _ = _win_functions()
            flags = _LOCKFILE_EXCLUSIVE_LOCK if write else 0
            overlapped = _Overlapped()
            # 不带 `LOCKFILE_FAIL_IMMEDIATELY`：系统调用阻塞到锁被授予为止。
            acquired = lock(handle, flags, 0, 1, 0, ctypes.byref(overlapped))  # pyright: ignore[reportCallIssue]
            if not acquired:
                last_error = cast("Any", ctypes).get_last_error()
                raise cast("Any", ctypes).WinError(last_error)
        except BaseException:
            with contextlib.suppress(OSError):
                os.close(fd)
            raise
        return _WindowsHeld(fd, handle)


class _PosixHeld:
    """POSIX 已持有的 `flock`（解锁后关闭本次 fd）。"""

    def __init__(self, fd: int, module: Any) -> None:
        """初始化。

        Args:
            fd: 本次取门独立打开的文件描述符。
            module: `fcntl` 模块。
        """
        self._fd = fd
        self._fcntl = module
        self._released = False

    def release(self) -> None:
        """释放锁并关闭 fd（幂等）。"""
        if self._released:
            return
        self._released = True
        with contextlib.suppress(OSError):
            self._fcntl.flock(self._fd, self._fcntl.LOCK_UN)
        with contextlib.suppress(OSError):
            os.close(self._fd)


class _PosixLock:
    """POSIX `flock`（阻塞形式；按打开的文件描述互斥，同进程不同任务也真正互斥）。

    为什么不用 `fcntl.lockf`：记录锁按**进程**生效，同进程不同 fd 之间不互斥，24 路下同一
    进程内的读写会互相穿透；`flock` 按打开文件描述生效，正好满足「同进程也要读写互斥」。
    """

    def __init__(self, path: Path, module: Any | None = None) -> None:
        """记录锁文件路径。

        Args:
            path: 锁文件路径。
            module: `fcntl` 模块（测试注入替身用；None 取真实模块）。
        """
        if module is None:
            import fcntl

            module = fcntl
        self._path = path
        self._fcntl: Any = module

    def acquire(self, *, write: bool) -> HeldLock:
        """阻塞取锁。

        Args:
            write: 独占锁 True，共享锁 False。

        Returns:
            HeldLock: 已持有的系统锁。
        """
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            operation = self._fcntl.LOCK_EX if write else self._fcntl.LOCK_SH
            self._fcntl.flock(fd, operation)
        except BaseException:
            with contextlib.suppress(OSError):
                os.close(fd)
            raise
        return _PosixHeld(fd, self._fcntl)


def _make_backend(path: Path) -> _Backend:
    """按平台创建锁后端。

    Args:
        path: 锁文件路径。

    Returns:
        _Backend: 平台锁实现。
    """
    if _IS_WINDOWS:
        return _WindowsLock(path)
    return _PosixLock(path)


def write_wait_cap() -> float:
    """写门等待上限（秒）：环境变量优先，缺省 `WRITE_WAIT_CAP`；超过即失败并点名持有者。

    Returns:
        float: 上限秒数。
    """
    raw = os.environ.get(WRITE_WAIT_CAP_ENV, "").strip()
    try:
        value = float(raw)
    except ValueError:
        return WRITE_WAIT_CAP
    return value if value > 0 else WRITE_WAIT_CAP


def gate_path(name: str) -> Path:
    """门文件路径（`<工程根>/.cache/test/db-gate-<name>.lock`）。

    Args:
        name: 门名（`platform` / `tenant` / `all`）。

    Returns:
        Path: 锁文件路径（父目录已创建）。
    """
    directory = project_root() / ".cache" / DEFAULT_GATE_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"db-gate-{name}.lock"


def _task_key() -> int:
    """当前 asyncio 任务的身份（无任务时为 0）。

    Returns:
        int: 任务对象 id。
    """
    task = asyncio.current_task()
    return id(task) if task is not None else 0


_pid_probe: Final = os.kill
"""进程存活探测（模块级别名：用例可注入 `PermissionError` 分支；Windows 不走它）。"""


def _pid_from_name(name: str) -> int | None:
    """从持有者文件名末段取 pid。

    Args:
        name: 文件名（形如 `db-gate-platform.holder-12345`）。

    Returns:
        int | None: pid；末段不是数字时为 None。
    """
    suffix = name.rsplit("-", 1)[-1]
    return int(suffix) if suffix.isdigit() else None


def _windows_pid_alive(pid: int) -> bool:  # pragma: no cover - 仅 Windows 可达（CI 与覆盖率门禁在 Linux）
    """Windows 进程存活判定（`OpenProcess` + `GetExitCodeProcess`）。

    不能用 `os.kill(pid, 0)`：Windows 上非控制信号的 `os.kill` 会直接 `TerminateProcess`。

    Args:
        pid: 进程号。

    Returns:
        bool: 仍存活返回 True。
    """
    kernel32 = cast("Any", ctypes).WinDLL("kernel32", use_last_error=True)
    process_query_limited_information = 0x1000
    still_active = 259
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _pid_alive(pid: int) -> bool:
    """进程是否仍存在（死进程留下的持有者记录不得参与点名）。

    Args:
        pid: 进程号。

    Returns:
        bool: 存活返回 True。
    """
    if pid <= 0:
        return False
    if _IS_WINDOWS:
        return _windows_pid_alive(pid)
    try:
        _pid_probe(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # 进程存在但属别的用户：存活。
        return True
    return True


def _holder_lines(path: Path) -> ConcurrentStableList[str]:
    """读一个持有者记录文件里的有效行（跳过空行与「已释放」标记）。

    Args:
        path: 记录文件。

    Returns:
        ConcurrentStableList[str]: 有效行；读不到时返回空清单。
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ConcurrentStableList()
    lines: ConcurrentStableList[str] = ConcurrentStableList()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or "hold=0" in line:
            continue
        lines.add(line)
    return lines


@dataclass(frozen=True, slots=True)
class _TaskHold:
    """门持有者的**任务级**记录（诊断用，不参与互斥判定）。

    Attributes:
        mode: `read` / `write`。
        pid: 进程号。
        task: asyncio 任务身份（`id(task)`）。
        test_id: 取门时的用例名（`PYTEST_CURRENT_TEST`）。
        at: 首次取门时刻（`HH:MM:SS`）。
        depth: 该任务在同一模式上的重入深度（读为份额数）。
    """

    mode: Mode
    pid: int
    task: int
    test_id: str
    at: str
    depth: int

    def render(self) -> str:
        """渲染为一行诊断文本。

        Returns:
            str: 形如 `pid=1 task=2 mode=write depth=1 test=x at=12:00:01`。
        """
        return f"pid={self.pid} task={self.task} mode={self.mode} depth={self.depth} test={self.test_id} at={self.at}"


@dataclass(slots=True)
class _Lease:
    """一次取门的租约（token 在阻塞前分配，取消时凭它销账）。

    Attributes:
        token: 份额 / 写租约编号。
        task: 发起取门的 asyncio 任务身份。
        write: 写门 True，读门 False。
        loop: 发起取门的事件循环。
        event: 授予通知（在事件循环线程里 `set`）。
        started: 发起时刻（`time.monotonic()`）。
        granted_at: 授予时刻（持门告警从这一刻起算）。
        lock: 已拿到的系统锁（由工作线程填入）。
        granted: 系统锁是否已授予。
        abandoned: 发起方是否已放弃（超时 / 取消）。
        error: 系统调用异常（授予失败时回传）。
    """

    token: int
    task: int
    write: bool
    loop: asyncio.AbstractEventLoop
    event: asyncio.Event
    started: float
    granted_at: float = 0.0
    lock: HeldLock | None = None
    granted: bool = False
    abandoned: bool = False
    error: BaseException | None = None


class DbGate:
    """跨进程读写门（一个库文件一把）。

    Attributes:
        name: 门名（用于诊断）。
    """

    def __init__(self, name: str, path: Path) -> None:
        """初始化门。

        Args:
            name: 门名。
            path: 锁文件路径。
        """
        self.name = name
        self._path = path
        self._holder_path = path.with_suffix(".holder")
        self._hold_base = path.with_suffix(".taskholds")
        """门持有任务记录的基准名（每进程一份：`db-gate-<name>.taskholds-<pid>`，与锁文件同源）。"""
        self._backend = _make_backend(path)
        # 读份额按**持有者**记账：每个取读者拿一个 token，释放时只放自己那份。
        # 不能用「进程级读深度」——同进程多个并发会话共用一个计数器时，一个会话的升级会把
        # 别的会话的份额一起放掉，对方还在读、写者又已经拿到独占，就会互相等。
        self._own_reads: ConcurrentStableDict[int, int] = ConcurrentStableDict()
        self._read_locks: ConcurrentStableDict[int, HeldLock] = ConcurrentStableDict()
        self._read_timers: ConcurrentStableDict[int, asyncio.TimerHandle] = ConcurrentStableDict()
        # 写门内取的读门是借用（没有独立的内核共享锁）；写门释放后转「已退役」，
        # 调用方稍后再释放时只销账、不报错（FastAPI 的 yield 依赖会晚于写门释放）。
        self._borrowed_reads: ConcurrentStableDict[int, None] = ConcurrentStableDict()
        self._retired_reads: ConcurrentStableDict[int, None] = ConcurrentStableDict()
        self._write_depth = 0
        self._write_owner = 0
        self._write_lock: HeldLock | None = None
        self._write_timer: asyncio.TimerHandle | None = None
        # 写门的**任务级**持有记录（任务 id → 记录）：只用于诊断点名。
        self._write_tasks: ConcurrentStableDict[int, _TaskHold] = ConcurrentStableDict()
        # 读门的任务级持有记录（同上）：写者超时时要点名「谁还在读」。
        self._read_tasks: ConcurrentStableDict[int, _TaskHold] = ConcurrentStableDict()
        self._pending: ConcurrentStableDict[int, _Lease] = ConcurrentStableDict()
        """尚未授予的租约（用于循环切换时统一放弃）。"""
        self._next_token = itertools.count(1)
        # 计数是跨协程 / 跨事件循环共享的进程级状态，用 `threading.Lock` 而非 `asyncio.Lock`：
        # pytest-asyncio 每个用例一个新事件循环，`asyncio.Lock` 会绑死在首个循环上。
        self._lock = threading.RLock()
        """门状态互斥（**可重入**：持有者快照 / 账目诊断会在持锁路径里被调用）。"""
        self._holder_lock = threading.Lock()
        """持有者文件的读改写互斥（诊断落盘，不与 `_lock` 混用）。"""
        self._requests: queue.SimpleQueue[_Lease | None] = queue.SimpleQueue()
        """门专用阻塞线程的任务队列（FIFO；释放不进队列，由持有方同步执行）。"""
        self._worker: threading.Thread | None = None
        self._closed = False
        self._loop_ref: weakref.ref[asyncio.AbstractEventLoop] | None = None
        """当前租约所属事件循环（弱引用）：pytest-asyncio 每用例一个新循环，切换时回收残留。"""

    # ------------------------------------------------------------------ 生命周期

    def _ensure_loop(self) -> None:
        """事件循环切换时回收上一循环的残留门（租约与系统锁）。

        为什么必须回收：pytest-asyncio 默认每用例新建事件循环。旧循环关闭时若某个任务在释放
        之前被取消，系统锁会随进程句柄留着——账目已清零，新循环却「持有者：无却永远取不到门」。
        这里把上一循环的持有全部释放，新循环从干净状态开始。

        用弱引用而不是 `id(loop)`：旧循环释放后 `id` 会被新循环复用，按 id 比较会把新循环误判
        成旧循环，残留锁永远不回收。
        """
        loop = asyncio.get_running_loop()
        with self._lock:
            current = self._loop_ref() if self._loop_ref is not None else None
            if current is loop and not self._closed:
                return
            stale = self._loop_ref is not None
            if self._closed:
                # 关闭后被重新使用：换一条新队列，避免读到上次 close 留下的停止哨兵。
                self._closed = False
                self._requests = queue.SimpleQueue()
                self._worker = None
            self._loop_ref = weakref.ref(loop)
            abandoned = ConcurrentStableList(self._pending.values())
            self._pending.clear()
            held_locks: ConcurrentStableList[HeldLock] = ConcurrentStableList(self._read_locks.values())
            self._read_locks.clear()
            if self._write_lock is not None:
                held_locks.add(self._write_lock)
                self._write_lock = None
            timers: ConcurrentStableList[asyncio.TimerHandle] = ConcurrentStableList(self._read_timers.values())
            self._read_timers.clear()
            if self._write_timer is not None:
                timers.add(self._write_timer)
                self._write_timer = None
            self._own_reads.clear()
            self._borrowed_reads.clear()
            self._retired_reads.clear()
            self._write_tasks.clear()
            self._read_tasks.clear()
            self._write_depth = 0
            self._write_owner = 0
        for lease in abandoned:
            lease.abandoned = True
        for handle in timers:
            handle.cancel()
        for lock in held_locks:
            lock.release()
        if stale and not held_locks:
            # 旧循环的残留门已清空；持有者记录同步清掉，避免点名到已经退出循环的任务。
            self._release_holder()
        self._ensure_worker()

    def _reclaim_dead_owners(self, *, reason: str) -> None:
        """回收「持有任务已结束」的读写租约（用例收尾漏放 / 任务被回收的兜底）。

        为什么必须有：任务结束却没走到 `gate_scope` 的 `finally`（循环关闭时 pending 任务不会被
        自动取消）时，账目与系统锁会一直留着；**别的进程**只能等满上限。旧实现在等门循环里按
        `asyncio.all_tasks()` 回收写权，换成本实现后必须补回同样的兜底，并把回收从「等门方
        轮询」改成「持有方自查」——持门 1s 的告警定时器与下一次取门都会触发。

        只回收**任务已不在当前循环**的租约：仍存活的任务（含后台任务）不回收，长持有仍由
        1s 告警点名。

        Args:
            reason: 触发来源（`hold` / `acquire`，仅日志用）。
        """
        loop = asyncio.get_running_loop()
        live = {id(task) for task in asyncio.all_tasks(loop)}
        held_locks: ConcurrentStableList[HeldLock] = ConcurrentStableList()
        timers: ConcurrentStableList[asyncio.TimerHandle] = ConcurrentStableList()
        reclaimed = False
        with self._lock:
            if self._write_depth and self._write_owner != 0 and self._write_owner not in live:
                if self._write_lock is not None:
                    held_locks.add(self._write_lock)
                self._write_lock = None
                if self._write_timer is not None:
                    timers.add(self._write_timer)
                    self._write_timer = None
                self._write_owner = 0
                self._write_depth = 0
                self._write_tasks.clear()
                for token in list(self._borrowed_reads):
                    del self._borrowed_reads[token]
                    self._retired_reads[token] = None
                reclaimed = True
            for token, owner in list(self._own_reads.items()):
                if owner in live:
                    continue
                del self._own_reads[token]
                held = self._read_locks.pop(token, None)
                if held is not None:
                    held_locks.add(held)
                timer = self._read_timers.pop(token, None)
                if timer is not None:
                    timers.add(timer)
                self._untrack_read(owner)
                reclaimed = True
        if not reclaimed:
            return
        for timer in timers:
            timer.cancel()
        for held in held_locks:
            held.release()
        _LOGGER.warning("gate_reclaim_dead_owner", extra={"gate": self.name, "reason": reason})
        self._release_holder()

    def _ensure_worker(self) -> None:
        """确保门专用阻塞线程在运行（每把门一条，守护线程，进程退出即结束）。"""
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            worker = threading.Thread(target=self._run_worker, name=f"dbgate-{self.name}", daemon=True)
            self._worker = worker
        worker.start()

    def _run_worker(self) -> None:
        """阻塞线程主体：逐条取任务，在系统调用上阻塞直到锁被授予。"""
        requests = self._requests
        while True:
            lease = requests.get()
            if lease is None:
                return
            try:
                self._acquire_blocking(lease)
            except BaseException:  # pragma: no cover - 防御：工作线程不得因单条租约退出
                _LOGGER.exception("gate_worker_failed", extra={"gate": self.name, "token": lease.token})

    def _acquire_blocking(self, lease: _Lease) -> None:
        """在工作线程内阻塞取锁，并把结果交付给事件循环。

        Args:
            lease: 取门租约。
        """
        try:
            held = self._backend.acquire(write=lease.write)
        except BaseException as exc:
            self._fail_lease(lease, exc)
            return
        with self._lock:
            if lease.abandoned:
                drop = held
                held = None
            else:
                lease.lock = held
                lease.granted = True
                lease.granted_at = time.monotonic()
                drop = None
        if drop is not None:
            drop.release()
            return
        try:
            lease.loop.call_soon_threadsafe(self._deliver, lease)
        except RuntimeError:
            # 循环已关闭：没人来取，立即释放。
            with self._lock:
                leftover = lease.lock
                lease.lock = None
                lease.abandoned = True
            if leftover is not None:
                leftover.release()

    def _deliver(self, lease: _Lease) -> None:
        """在事件循环线程里通知授予（租约已放弃则就地释放）。

        Args:
            lease: 取门租约。
        """
        with self._lock:
            leftover = lease.lock if lease.abandoned else None
            if leftover is not None:
                lease.lock = None
        if leftover is not None:
            leftover.release()
            return
        lease.event.set()

    def _fail_lease(self, lease: _Lease, exc: BaseException) -> None:
        """把系统调用异常回传给等待方。

        Args:
            lease: 取门租约。
            exc: 系统调用异常。
        """
        with self._lock:
            lease.error = exc
            lease.abandoned = True
        with contextlib.suppress(RuntimeError):
            lease.loop.call_soon_threadsafe(lease.event.set)

    def _abandon(self, lease: _Lease) -> None:
        """放弃租约（超时 / 取消）：已授予的系统锁就地释放。

        Args:
            lease: 取门租约。
        """
        with self._lock:
            lease.abandoned = True
            self._pending.pop(lease.token, None)
            leftover = lease.lock
            lease.lock = None
            lease.granted = False
        if leftover is not None:
            leftover.release()

    def close(self) -> None:
        """关闭门（会话或进程退出时调用）。"""
        with self._lock:
            self._closed = True
            pending = ConcurrentStableList(self._pending.values())
            self._pending.clear()
            held_locks: ConcurrentStableList[HeldLock] = ConcurrentStableList(self._read_locks.values())
            self._read_locks.clear()
            if self._write_lock is not None:
                held_locks.add(self._write_lock)
                self._write_lock = None
            timers: ConcurrentStableList[asyncio.TimerHandle] = ConcurrentStableList(self._read_timers.values())
            self._read_timers.clear()
            if self._write_timer is not None:
                timers.add(self._write_timer)
                self._write_timer = None
            self._own_reads.clear()
            self._borrowed_reads.clear()
            self._retired_reads.clear()
            self._write_tasks.clear()
            self._read_tasks.clear()
            self._write_depth = 0
            self._write_owner = 0
        for lease in pending:
            lease.abandoned = True
        for handle in timers:
            handle.cancel()
        for lock in held_locks:
            lock.release()
        self._requests.put(None)
        with contextlib.suppress(OSError):
            self._holder_file().unlink()
            self._task_hold_path().unlink()

    # ------------------------------------------------------------------ 读门

    async def acquire_read(self, *, wait: float | None = None) -> int:
        """取读门，返回本次份额的 token（释放时凭它销账）。

        **只有持写门的那个任务**取读门才走「借用」（不取系统锁、随写门作废）；同一进程里的
        **其它任务**必须走系统锁排队——写门独占期间它们的共享锁加不上，读不到写了一半的数据。

        Args:
            wait: 等门上限（秒）；None 用 `DEFAULT_TIMEOUT`。

        Returns:
            int: 读份额 token。

        Raises:
            TimeoutError: 等待超时。
        """
        return await self._acquire_read(wait=wait)

    async def _acquire_read(self, *, wait: float | None = None, token: int | None = None) -> int:
        """取读门（可指定 token，供升级后补回原份额）。

        Args:
            wait: 等门上限（秒）。
            token: 指定份额编号（补回升级时让出的份额）；None 新建。

        Returns:
            int: 读份额 token。
        """
        mine = _task_key()
        self._ensure_loop()
        self._reclaim_dead_owners(reason="acquire")
        loop = asyncio.get_running_loop()
        borrowed_token = token
        with self._lock:
            borrowed = self._write_depth > 0 and self._write_owner == mine
            if borrowed:
                borrowed_token = token if token is not None else next(self._next_token)
                self._borrowed_reads[borrowed_token] = None
                self._track_read()
        if borrowed:
            self._record_holder(False)
            assert borrowed_token is not None
            return borrowed_token
        lease = self._new_lease(token, mine, False, loop)
        limit = DEFAULT_TIMEOUT if wait is None else min(DEFAULT_TIMEOUT, wait)
        await self._wait_granted(lease, limit)
        with self._lock:
            self._pending.pop(lease.token, None)
            self._own_reads[lease.token] = mine
            if lease.lock is not None:
                self._read_locks[lease.token] = lease.lock
            self._track_read()
        self._record_holder(False)
        self._schedule_hold_timer(lease.token, lease.granted_at, read_only=True)
        return lease.token

    async def release_read(self, token: int) -> None:
        """释放指定读份额（只放自己那份；已退役的借用份额只销账）。

        Args:
            token: `acquire_read` 返回的 token。

        Raises:
            RuntimeError: token 未被本门持有（重复释放 / 释放错对象）。
        """
        with self._lock:
            if token in self._borrowed_reads:
                del self._borrowed_reads[token]
                return
            if token in self._retired_reads:
                del self._retired_reads[token]
                return
            owner = self._own_reads.get(token)
            if owner is None:
                raise RuntimeError(f"门 {self.name} 释放读份额失败：token {token} 未被持有")
            del self._own_reads[token]
            held = self._read_locks.pop(token, None)
            timer = self._read_timers.pop(token, None)
            self._untrack_read(owner)
            idle = not self._own_reads and not self._borrowed_reads and not self._write_depth
        if timer is not None:
            timer.cancel()
        if held is not None:
            held.release()
        if idle:
            self._release_holder()

    def owns(self, token: int) -> bool:
        """该读份额 token 是否仍被本门持有（含借用 / 已退役）。

        Args:
            token: `acquire_read` 返回的 token。

        Returns:
            bool: 仍持有返回 True。
        """
        with self._lock:
            return token in self._own_reads or token in self._borrowed_reads or token in self._retired_reads

    # ------------------------------------------------------------------ 写门

    async def acquire_write(self, *, wait: float | None = None) -> ConcurrentStableList[int]:
        """取写门（独占；**同一任务**可重入）。

        **写门落锁即同步卡住读门**：系统锁独占形式一旦被授予，内核保证此刻没有任何共享锁；
        同进程其它任务与其它进程的读门都在系统调用上阻塞。

        Returns:
            ConcurrentStableList[int]: 让出的读份额 token（写完后由 `release_write` 原样补回）。

        Raises:
            TimeoutError: 等待超时。
        """
        mine = _task_key()
        self._ensure_loop()
        self._reclaim_dead_owners(reason="acquire")
        loop = asyncio.get_running_loop()
        released: ConcurrentStableList[int] = ConcurrentStableList()
        reentered = False
        with self._lock:
            if self._write_depth and self._write_owner == mine:
                self._write_depth += 1
                self._track_write()
                reentered = True
        if reentered:
            self._flush_task_holders()
            return released
        released = self._drop_own_reads(mine)
        lease = self._new_lease(None, mine, True, loop)
        limit = write_wait_cap() if wait is None else min(DEFAULT_TIMEOUT, wait)
        try:
            await self._wait_granted(lease, limit)
        except BaseException:
            # 取写门失败：让出的读份额就地补回（`gate_scope` 的 finally 只能补回它自己知道的
            # token；直接调用本方法的调用方不会收到返回值，不能把份额留在半空）。
            if released:
                with contextlib.suppress(BaseException):
                    await self.restore_reads(released)
            raise
        with self._lock:
            self._pending.pop(lease.token, None)
            self._write_owner = mine
            self._write_depth = 1
            self._write_lock = lease.lock
            self._track_write()
        self._record_holder(True)
        self._schedule_hold_timer(lease.token, lease.granted_at, read_only=False)
        return released

    def _drop_own_reads(self, mine: int) -> ConcurrentStableList[int]:
        """让出本任务持有的全部读份额（升级前置；释放系统锁在锁外执行）。

        Args:
            mine: 当前任务身份。

        Returns:
            ConcurrentStableList[int]: 让出的 token 清单。
        """
        released: ConcurrentStableList[int] = ConcurrentStableList()
        held_locks: ConcurrentStableList[HeldLock] = ConcurrentStableList()
        timers: ConcurrentStableList[asyncio.TimerHandle] = ConcurrentStableList()
        with self._lock:
            for token, owner in list(self._own_reads.items()):
                if owner != mine:
                    continue
                del self._own_reads[token]
                released.add(token)
                held = self._read_locks.pop(token, None)
                if held is not None:
                    held_locks.add(held)
                timer = self._read_timers.pop(token, None)
                if timer is not None:
                    timers.add(timer)
                self._untrack_read(mine)
        for timer in timers:
            timer.cancel()
        for held in held_locks:
            held.release()
        return released

    def release_write_now(
        self, restore: ConcurrentStableList[int] | None = None, *, expect_held: bool = True
    ) -> ConcurrentStableList[int]:
        """**同步**释放写门：账目与系统解锁立即完成（取消 / 收尾阶段也一定生效）。

        为什么拆出同步版：用例被取消时 `finally` 里的 `await` 可能立刻再抛 `CancelledError`，
        异步释放就走不完——写门深度永久多一层，之后整批任务在门口等满上限。

        Args:
            restore: `acquire_write` 返回的 token 清单（升级路径传入；None 表示无）。
            expect_held: 调用方**自认为**持有写门。取写门超时时 `gate_scope` 也会走到本方法，
                此时「未持有」是预期的，不该刷告警（否则每轮超时都多一条假警告，排障先要排除它）；
                真正的重复释放 / 租约泄漏仍传 True，照常告警。

        Returns:
            ConcurrentStableList[int]: 需要补回的读份额（调用方异步恢复；无则空）。
        """
        with self._lock:
            was_held = bool(self._write_depth)
            held: HeldLock | None = None
            timer: asyncio.TimerHandle | None = None
            retired: ConcurrentStableList[int] = ConcurrentStableList()
            if not was_held:
                remaining = 0
            else:
                self._write_depth -= 1
                remaining = self._write_depth
                if remaining:
                    self._untrack_write()
                else:
                    held = self._write_lock
                    self._write_lock = None
                    timer = self._write_timer
                    self._write_timer = None
                    self._write_owner = 0
                    self._write_tasks.clear()
                    retired = ConcurrentStableList(self._borrowed_reads)
                    for token in retired:
                        del self._borrowed_reads[token]
                    for token in retired:
                        self._retired_reads[token] = None
        if timer is not None:
            timer.cancel()
        if not was_held:
            # 结构要求：取写门失败也走这里。预期的「未持有」（取门超时）不告警，只补回份额；
            # 其余情况（重复释放 / 租约丢了）留痕，便于定位「谁把门弄丢了」。
            if expect_held:
                _LOGGER.warning(
                    "gate_release_without_write",
                    extra={"gate": self.name, "restore": len(restore or ())},
                )
            self._flush_task_holders()
            return ConcurrentStableList(restore or ())
        if remaining:
            self._flush_task_holders()
            return ConcurrentStableList()
        if held is not None:
            held.release()
        self._release_holder()
        return ConcurrentStableList(restore or ())

    async def release_write(
        self, restore: ConcurrentStableList[int] | None = None, *, expect_held: bool = True
    ) -> None:
        """释放写门，并恢复升级时让出的读份额。

        **未持写门时不抛错**：`gate_scope` 的 `finally` 无论取写门是否成功都会走到这里，
        抛错会把真正的失败（如等门超时）盖掉。未持有时按 `expect_held` 决定是否告警，
        并尽力补回让出的份额。

        Args:
            restore: `acquire_write` 返回的 token 清单（升级路径传入；None 表示无）。
            expect_held: 调用方自认为持有写门（见 `release_write_now`）。
        """
        pending = self.release_write_now(restore, expect_held=expect_held)
        if pending:
            await self.restore_reads(pending)

    async def restore_reads(self, restore: ConcurrentStableList[int]) -> None:
        """把让出的读份额补回（重新取系统共享锁并登记回原 token）。

        Args:
            restore: 要补回的 token 清单。
        """
        for token in restore:
            await self._acquire_read(token=int(token))

    # ------------------------------------------------------------------ 租约

    def _new_lease(
        self,
        token: int | None,
        task: int,
        write: bool,
        loop: asyncio.AbstractEventLoop,
    ) -> _Lease:
        """创建并登记租约，交给阻塞线程。

        Args:
            token: 指定编号（补回份额）；None 新建。
            task: 发起任务身份。
            write: 写门 True。
            loop: 事件循环。

        Returns:
            _Lease: 已登记的租约。
        """
        lease = _Lease(
            token=token if token is not None else next(self._next_token),
            task=task,
            write=write,
            loop=loop,
            event=asyncio.Event(),
            started=time.monotonic(),
        )
        with self._lock:
            self._pending[lease.token] = lease
        self._ensure_worker()
        self._requests.put(lease)
        return lease

    async def _wait_granted(self, lease: _Lease, limit: float) -> None:
        """等待租约授予；超时 / 取消即放弃租约并抛错。

        Args:
            lease: 租约。
            limit: 等待上限（秒）。

        Raises:
            TimeoutError: 超过上限。
            BaseException: 系统调用异常或调用方取消。
        """
        timer = lease.loop.call_later(WARN_AFTER, self._warn_wait, lease)
        try:
            await asyncio.wait_for(lease.event.wait(), timeout=limit)
        except TimeoutError:
            self._abandon(lease)
            message = (
                f"等待数据库门超时（{limit:.1f}s）：{gate_label(self.name)}；"
                f"持有者：{self._describe_holder()}；{self._describe_local_ledger()}；"
                "等满硬上限说明有任务长期持门（读会话未释放 / 进程卡住）"
            )
            self._log_wait(message)
            self._note_gate_wait(limit, "timeout")
            raise TimeoutError(message) from None
        except BaseException:
            self._abandon(lease)
            raise
        finally:
            timer.cancel()
        if lease.error is not None:
            error = lease.error
            lease.error = None
            raise error
        if lease.abandoned:
            # 授予与放弃同时发生时 `_deliver` 已就地释放；这里只销账。
            raise TimeoutError(f"等待数据库门失败：{gate_label(self.name)} 租约已放弃")

    # ------------------------------------------------------------------ 诊断

    @property
    def mode(self) -> Mode | None:
        """当前持有模式（写优先；未持有为 None）。

        Returns:
            Mode | None: 模式。
        """
        if self._write_depth:
            return WRITE
        if self._own_reads or self._borrowed_reads:
            return READ
        return None

    @property
    def depth(self) -> int:
        """当前重入深度（有效读份额 + 写深度；已退役份额不计）。

        Returns:
            int: 深度（0 表示未持有）。
        """
        return len(self._own_reads) + len(self._borrowed_reads) + self._write_depth

    def write_holders(self) -> ConcurrentStableList[str]:
        """当前持有**写门**的任务清单（诊断：区分「独占到门」与「同进程另一协程重入」）。

        Returns:
            ConcurrentStableList[str]: 每条形如 `pid=1 task=2 mode=write depth=1 test=x at=12:00:01`。
        """
        with self._lock:
            return ConcurrentStableList(hold.render() for hold in self._write_tasks.values())

    def holder_tasks(self) -> ConcurrentStableList[str]:
        """当前持有本门（读或写）的任务清单（诊断：写者进门前采样，看谁在挡）。

        Returns:
            ConcurrentStableList[str]: 写持有者在前、读持有者在后。
        """
        holders = self.write_holders()
        with self._lock:
            for hold in self._read_tasks.values():
                holders.add(hold.render())
        return holders

    @staticmethod
    def _test_id() -> str:
        """取当前用例名（`PYTEST_CURRENT_TEST` 去掉阶段后缀）。

        Returns:
            str: 用例名；取不到给「未知」。
        """
        return os.environ.get("PYTEST_CURRENT_TEST", "").split(" (")[0] or "未知"

    def _track_write(self) -> None:
        """登记本任务持有写门（**必须在 `_lock` 内调用**）。

        首次取门记下用例名与时刻，重入只加深度——点名时关心的是「谁最早拿到、拿了多久」。
        """
        task = _task_key()
        existing = self._write_tasks.get(task)
        self._write_tasks[task] = _TaskHold(
            mode=WRITE,
            pid=os.getpid(),
            task=task,
            test_id=existing.test_id if existing is not None else self._test_id(),
            at=existing.at if existing is not None else time.strftime("%H:%M:%S"),
            depth=(existing.depth if existing is not None else 0) + 1,
        )

    def _untrack_write(self) -> None:
        """注销本任务的一次写持有（在 `_lock` 内调用；深度归零即删记录）。"""
        task = _task_key()
        existing = self._write_tasks.get(task)
        if existing is None:
            return
        if existing.depth <= 1:
            del self._write_tasks[task]
            return
        self._write_tasks[task] = _TaskHold(
            mode=WRITE,
            pid=existing.pid,
            task=task,
            test_id=existing.test_id,
            at=existing.at,
            depth=existing.depth - 1,
        )

    def _track_read(self) -> None:
        """登记本任务持有一个读份额（**必须在 `_lock` 内调用**）。"""
        task = _task_key()
        existing = self._read_tasks.get(task)
        self._read_tasks[task] = _TaskHold(
            mode=READ,
            pid=os.getpid(),
            task=task,
            test_id=existing.test_id if existing is not None else self._test_id(),
            at=existing.at if existing is not None else time.strftime("%H:%M:%S"),
            depth=(existing.depth if existing is not None else 0) + 1,
        )

    def _untrack_read(self, task: int) -> None:
        """注销某个任务的一个读份额（在 `_lock` 内调用；份额归零即删记录）。

        Args:
            task: 份额的持有任务身份（不一定等于当前任务：收尾可能跨任务释放）。
        """
        existing = self._read_tasks.get(task)
        if existing is None:
            return
        if existing.depth <= 1:
            del self._read_tasks[task]
            return
        self._read_tasks[task] = _TaskHold(
            mode=READ,
            pid=existing.pid,
            task=task,
            test_id=existing.test_id,
            at=existing.at,
            depth=existing.depth - 1,
        )

    def _schedule_hold_timer(self, key: int, started: float, *, read_only: bool) -> None:
        """登记「持有满 1s」告警定时器（常开）。

        Args:
            key: 读 token 或写租约编号。
            started: 取门开始时刻。
            read_only: 读区间 True。
        """
        loop = asyncio.get_running_loop()
        handle = loop.call_later(WARN_AFTER, self._warn_hold, key, started, read_only)
        with self._lock:
            if read_only:
                self._read_timers[key] = handle
            else:
                self._write_timer = handle

    def _warn_hold(self, key: int, started: float, read_only: bool) -> None:
        """持有满 1s 时告警（常开；持有者当场点名）。

        Args:
            key: 读 token 或写租约编号。
            started: 取门开始时刻。
            read_only: 读区间 True。
        """
        with contextlib.suppress(RuntimeError):
            self._reclaim_dead_owners(reason="hold")
        with self._lock:
            if read_only:
                alive = key in self._own_reads
                self._read_timers.pop(key, None)
            else:
                alive = self._write_depth > 0
                self._write_timer = None
        if not alive:
            return
        held = time.monotonic() - started
        message = (
            f"[rwlock] 门 {gate_label(self.name)} 已持有 {held:.1f}s（超过 {WARN_AFTER:g}s，疑似长区间）："
            f"持有者：{self._describe_holder()}；{self._describe_locked_identity()}"
        )
        print(message, flush=True)
        self._log_wait(message)
        self._note_gate_wait(held, "hold")

    def _warn_wait(self, lease: _Lease) -> None:
        """等门满 1s 时打一行告警（仍继续等，直到 5s / 10s 上限）。

        Args:
            lease: 等待中的租约。
        """
        with self._lock:
            if lease.abandoned or lease.granted:
                return
        message = (
            f"[rwlock] 等待门 {gate_label(self.name)} 已 {WARN_AFTER:g}s；"
            f"持有者：{self._describe_holder()}；{self._describe_local_ledger()}"
        )
        print(message, flush=True)
        self._log_wait(message)
        self._note_gate_wait(WARN_AFTER, "warn")

    def _record_holder(self, write: bool) -> None:
        """记录本进程持有门（诊断：等门 / 超时时列出真实持有者与用例名）。

        每进程一份独立文件、释放时把 `hold` 置 0：卡住时可以读出**所有仍持有**的进程，
        不会被后来者覆盖。

        Args:
            write: 独占 True，共享 False。
        """
        self._write_holder(write, held=True)
        self._flush_task_holders()

    def _release_holder(self) -> None:
        """标记本进程已不持有任何门（保留最后用例名，便于事后追）。"""
        self._write_holder(False, held=False)
        self._flush_task_holders()

    def _write_holder(self, write: bool, *, held: bool) -> None:
        """写持有者记录。

        Args:
            write: 独占 True，共享 False。
            held: 仍持有 True；已释放 False。
        """
        test_id = os.environ.get("PYTEST_CURRENT_TEST", "").split(" (")[0]
        payload = (
            f"pid={os.getpid()} mode={WRITE if write else READ} hold={1 if held else 0} "
            f"test={test_id or '未知'} at={time.strftime('%H:%M:%S')}"
        )
        with self._holder_lock, contextlib.suppress(OSError):
            self._holder_file().write_text(payload, encoding="utf-8")

    def _flush_task_holders(self) -> None:
        """把任务级持有记录整体落盘（快照：读 / 写持有任务一行一条；无持有任务即写空）。

        用「整体重写」而不是追加：点名要的是**当前**持有者，追加版会把已释放的任务一直算进去。
        无持有者时写空文件而不是删文件——同一把锁可能被多个门实例共写（用例刻意造两个实例验互斥），
        删除会把别人刚写下的持有记录一起抹掉。
        """
        lines = self.holder_tasks()
        path = self._task_hold_path()
        with self._holder_lock, contextlib.suppress(OSError):
            path.write_text((chr(10).join(lines) + chr(10)) if lines else "", encoding="utf-8")

    def _holder_file(self) -> Path:
        """本进程的持有者记录文件（每进程一份，互不覆盖）。

        Returns:
            Path: `.cache/test/db-gate-<name>.holder-<pid>`。
        """
        return self._holder_path.with_name(f"{self._holder_path.name}-{os.getpid()}")

    def _task_hold_path(self) -> Path:
        """本进程的**写门任务记录**文件（一行一个持有任务，释放即删）。

        Returns:
            Path: `.cache/test/db-gate-<name>.taskholds-<pid>`。
        """
        return self._hold_base.with_name(f"{self._hold_base.name}-{os.getpid()}")

    def _describe_holder(self) -> str:
        """列出**当前仍持有**本门的任务（跨进程扫描各 pid 的记录文件）。

        两类记录合并：进程级（`hold=1` 一行，旧版遗留）与任务级（读 / 写各一行）。**写门只认
        任务级**——进程级那行只说得清「某个进程在写」，而并发问题恰恰出在「同进程哪个协程也在写」。

        **死进程的记录一律过滤**——进程被强杀时记录留在盘上，不判存活就会把早已退出的进程当
        持有者点名，误导排查。

        Returns:
            str: 形如 `pid=123 task=456 mode=write depth=1 test=a.py::t at=12:00:01`；没有时给「未知」。
        """
        directory = self._holder_path.parent
        entries: ConcurrentStableList[str] = ConcurrentStableList()
        covered: ConcurrentStableSet[int] = ConcurrentStableSet()
        for path in directory.glob(f"{self._hold_base.name}-*"):
            pid = _pid_from_name(path.name)
            if pid is None or not _pid_alive(pid):
                continue
            # 任务级记录是权威口径：该进程只要有持有任务，就不再采信进程级那行（避免重复点名）
            covered.add(pid)
            for line in _holder_lines(path):
                entries.append(line)
        for path in directory.glob(f"{self._holder_path.name}-*"):
            pid = _pid_from_name(path.name)
            if pid is None or pid in covered or not _pid_alive(pid):
                continue
            for line in _holder_lines(path):
                entries.append(line)
        return " | ".join(entries) if entries else "无（可能刚释放或记录未落盘）"

    def _describe_local_ledger(self) -> str:
        """本进程账目（读份额数 / 写深度 / 未授予租约数），补上磁盘记录看不到的泄漏。

        为什么需要：持有记录按「任务 → 文件」落盘，任务被取消 / 收尾异常时**文件可能已删**
        而账目里的读份额还在——现象是「持有者：无」却一直等门。这里直接读内存账目，
        一行说清是本进程还压着读份额（真泄漏），还是账目也空（跨进程争用）。

        Returns:
            str: 形如 `本进程账目：read_tokens=2 write_depth=0 pending=0`。
        """
        with self._lock:
            read_tokens = len(self._own_reads)
            borrowed = len(self._borrowed_reads)
            write_depth = self._write_depth
            pending = len(self._pending)
        return f"本进程账目：read_tokens={read_tokens} borrowed={borrowed} write_depth={write_depth} pending={pending}"

    def _describe_locked_identity(self) -> str:
        """告警行里的任务身份（持门超 1s 时点名到具体任务）。

        Returns:
            str: 形如 `task=123 pid=456 test=a.py::t`。
        """
        task = _task_key()
        test_id = os.environ.get("PYTEST_CURRENT_TEST", "").split(" (")[0] or "未知"
        return f"task={task} pid={os.getpid()} test={test_id}"

    def _log_wait(self, message: str) -> None:
        """把等门 / 持门告警追加到诊断文件（pytest 会捕获 stdout，落文件才留得住）。

        Args:
            message: 告警内容。
        """
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n"
        with (
            contextlib.suppress(OSError),
            self._holder_path.with_name("gate-wait.log").open("a", encoding="utf-8") as handle,
        ):
            handle.write(line)

    def _note_gate_wait(self, waited: float, reason: str) -> None:
        """等门 / 持门告警 / 超时时抓一份全进程栈（开关与节流由诊断工具决定）。

        Args:
            waited: 已等待 / 已持有秒数。
            reason: 触发原因（`warn` / `hold` / `timeout`）。
        """
        diagnostics.note_gate_wait(
            self._holder_path.with_name(f"gate-stacks-{os.getpid()}.log"),
            gate_name=gate_label(self.name),
            waited=waited,
            reason=reason,
            holder=self._describe_holder(),
        )
