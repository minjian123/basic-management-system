"""跨进程数据库访问读写门（13_08）：读者共享、写者独占，进程退出由内核回收。

为什么换掉文件锁：现有 `file_lock` 用「创建锁文件 + 50ms 轮询 + 心跳线程 + 30s 陈旧判定」模拟互斥，
实测取放 0.30ms、等锁平均多 25ms、进程被杀即留残锁。操作系统原生字节锁实测取放 **0.0031ms**，
3 个读者各持 20ms 共享锁总耗时 **21.2ms**（真并发），读者持续请求时写者 **3.3ms** 拿到独占锁
（不被饿死），且进程退出内核自动释放——心跳、陈旧判定、放锁重试整套补丁可删。

平台差异：

- Windows：`LockFileEx` 共享锁不带 `LOCKFILE_EXCLUSIVE_LOCK`、独占锁带上；`UnlockFileEx` 释放；
- POSIX：`fcntl.lockf` 的 `F_RDLCK` / `F_WRLCK` / `F_UNLCK`。

两者都按「文件 + 字节区间」加锁，跨进程争用天然互斥。POSIX 的记录锁按进程生效，同进程内的读/写
不互斥，故进程内由本模块按深度计数独占（见下）。

口径（《测试规范》「并行与隔离」节）：

- 读门与写门的作用域都是**一次数据库操作**（一次会话），不是整条用例；
- 写门与所有读门互斥；写者等待期间新读者由内核排在写者之后（写者优先）；
- 禁止「持读门原地升级」——多个写者同时升级会互相等对方释放读份额而死锁；升级由
  `bms_core.testing.gates` 的写门上下文按「放读份额 → 取写门 → 放写门 → 取回读份额」完成；
- 进程内重入按深度计数放行，嵌套同一模式不重复走系统调用。
"""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import itertools
import logging
import os
import sys
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, Protocol, cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.testing import diagnostics
from bms_core.testing.paths import project_root

DEFAULT_TIMEOUT: Final = 10.0
"""等门上限（秒）：超时即报错，不静默降级。

13_08 T7 由 180s 收到 30s，2026-11-21 再收到 10s：测试等待超过 10s 本身就是「用例写得不好 /
有任务长期持门」的信号，报错比继续等更有用。
"""

WRITE_WAIT_CAP: Final = 5.0
"""写门等待上限（秒）：超过即失败并点名持有者（13_08 T7 起恢复短上限）。

正常写是毫秒级，等超过几秒就不是「排队」而是「有人长期持门」——报错比继续等更有用。
整段临界区（建表 / 用例级独占等）经显式 `cap`（`GATE_CRITICAL_WAIT`）放宽，不走本缺省。
"""

WRITE_WAIT_CAP_ENV: Final = "BMS_TEST_GATE_WRITE_WAIT"
"""写门等待上限的环境变量覆盖（秒；缺省用 `WRITE_WAIT_CAP`）。"""

WARN_AFTER: Final = 10.0
"""等门告警阈值（秒）：超过即打印一行，便于定位长期占用。"""

DEFAULT_GATE_DIRNAME: Final = "test"
"""门文件所在目录名（`<工程根>/.cache/test/`，与共享测试库同区）。"""

_LOGGER = logging.getLogger(__name__)
"""门自身诊断日志（未持写门却释放等）。"""

Mode = Literal["read", "write"]
"""门模式（读共享 / 写独占）。"""

GATE_LABEL: ContextVar[str] = ContextVar("bms_db_gate_label", default="")
"""诊断标签（当前任务正在取哪把逻辑门：`platform` / `tenant`）。

13_08 T7 起全库共用一把内核门，门实例自己的名字恒为 `all`；日志与栈转储要写「用户视角
的门名」才定位得到现场，故由 `gate_scope` 在取门前按任务上下文设置，`_log_wait` /
`_note_gate_wait` 读它、缺省回落实例名。
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

_RETRY_MIN: Final = 0.0005
"""首次重试间隔（秒）：争用少时尽快拿到门。"""

_RETRY_MAX: Final = 0.005
"""重试间隔上限（秒）：比原文件锁的 50ms 轮询低一个数量级。"""

_LOCKFILE_FAIL_IMMEDIATELY: Final = 0x0001
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


class _Backend(Protocol):
    """平台锁后端（Windows 字节锁 / POSIX 记录锁）。"""

    def try_acquire(self, *, write: bool) -> bool:
        """尝试加锁（非阻塞）。

        Args:
            write: 独占锁 True，共享锁 False。

        Returns:
            bool: 拿到锁 True，被占用 False。
        """
        ...

    def release(self) -> None:
        """释放当前持有的锁。"""
        ...

    def close(self) -> None:
        """关闭句柄（会话结束调用）。"""
        ...


class _WindowsLock:  # pragma: no cover - 仅 Windows 可达（CI 与覆盖率门禁在 Linux）
    """Windows 字节区间锁（`LockFileEx`）。"""

    def __init__(self, path: Path) -> None:
        """打开锁文件并取系统句柄。

        Args:
            path: 锁文件路径（内容为空，仅作锁载体）。
        """
        self._fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
        self._handle = self._os_handle(self._fd)
        self._lock, self._unlock = self._functions()

    @staticmethod
    def _os_handle(fd: int) -> int:
        """把文件描述符转成 Windows 系统句柄。

        Args:
            fd: 文件描述符。

        Returns:
            int: 系统句柄。
        """
        import msvcrt

        return int(msvcrt.get_osfhandle(fd))

    @staticmethod
    def _functions() -> tuple[Any, Any]:
        """取并配置 `LockFileEx` / `UnlockFileEx`（模块级只配一次）。

        Returns:
            tuple[object, object]: （加锁函数, 解锁函数）。
        """
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
        return lock, unlock

    def try_acquire(self, *, write: bool) -> bool:
        """尝试加锁（不等待）。

        Args:
            write: 独占锁 True，共享锁 False。

        Returns:
            bool: 拿到锁 True。
        """
        flags = _LOCKFILE_FAIL_IMMEDIATELY | (_LOCKFILE_EXCLUSIVE_LOCK if write else 0)
        overlapped = _Overlapped()
        acquired = self._lock(  # pyright: ignore[reportCallIssue]
            self._handle, flags, 0, 1, 0, ctypes.byref(overlapped)
        )
        return bool(acquired)

    def release(self) -> None:
        """释放锁（**幂等**：内核报告「未加锁」视为已释放）。

        为什么容忍 `ERROR_NOT_LOCKED`（158）：升级路径曾在「本进程还有别的读者」时保留共享锁
        再取独占锁，同一句柄重复加锁会把两种模式合并，解锁一次就把区域整体放掉，后续再释放
        会报「段已解除锁定」，把 `_kernel_read` 与内核状态弄脱节——表现为「持有者：无」却
        一直等门。幂等释放让这类历史状态自然收敛；真正的锁覆盖由账目（`_kernel_read` /
        `_write_depth`）修正保证。

        Raises:
            OSError: 系统调用失败（句柄已失效等）。
        """
        overlapped = _Overlapped()
        released = self._unlock(  # pyright: ignore[reportCallIssue]
            self._handle, 0, 1, 0, ctypes.byref(overlapped)
        )
        if released:
            return
        error = ctypes.get_last_error()
        if error == _ERROR_NOT_LOCKED:
            return
        raise ctypes.WinError(error)

    def close(self) -> None:
        """关闭文件描述符（进程退出时内核同时释放锁）。"""
        os.close(self._fd)


class _PosixLock:
    """POSIX 记录锁（`fcntl.lockf`）。"""

    def __init__(self, path: Path, module: Any | None = None) -> None:
        """打开锁文件。

        Args:
            path: 锁文件路径。
            module: `fcntl` 模块（测试注入替身用；None 取真实模块）。
        """
        if module is None:
            import fcntl

            module = fcntl
        self._fcntl: Any = module
        self._fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)

    def try_acquire(self, *, write: bool) -> bool:
        """尝试加锁（不等待）。

        Args:
            write: 独占锁 True，共享锁 False。

        Returns:
            bool: 拿到锁 True。
        """
        operation = self._fcntl.LOCK_EX if write else self._fcntl.LOCK_SH
        try:
            self._fcntl.lockf(self._fd, operation | self._fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def release(self) -> None:
        """释放锁。"""
        self._fcntl.lockf(self._fd, self._fcntl.LOCK_UN)

    def close(self) -> None:
        """关闭文件描述符。"""
        os.close(self._fd)


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
        name: 门名（`platform` / `tenant`）。

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
        # 不能用「进程级读深度」——同一进程里多个并发会话共用一个计数器时，一个会话的升级
        # 会把别的会话的份额一起放掉；对方的 SQLite 读事务还开着，写者提交时被它挡住、
        # 它又在等门，互等到 `busy_timeout` 超时（13_08 实测的整轮卡死）。
        self._own_reads: ConcurrentStableDict[int, int] = ConcurrentStableDict()
        # 写门内取的读门是借用（没有独立的内核共享锁）；写门释放后转「已退役」，
        # 调用方稍后再释放时只销账、不报错（FastAPI 的 yield 依赖会晚于写门释放）。
        self._borrowed_reads: ConcurrentStableDict[int, None] = ConcurrentStableDict()
        self._retired_reads: ConcurrentStableDict[int, None] = ConcurrentStableDict()
        self._write_depth = 0
        self._write_owner = 0
        # 写门的**任务级**持有记录（任务 id → 记录）：只用于诊断点名，与 `_write_depth` 同步维护，
        # 不参与任何判定。进程级深度分不清「谁在写」，而并发问题恰恰出在「同进程另一协程也进了写门」，
        # 故按任务记账，超时时才能点到具体用例。
        self._write_tasks: ConcurrentStableDict[int, _TaskHold] = ConcurrentStableDict()
        # 读门的任务级持有记录（同上）：读事务在 SQLite rollback journal 下会挡住写者的提交，
        # 「写者拿到门却实占 5s」只有看到**读持有者**才能解释。
        self._read_tasks: ConcurrentStableDict[int, _TaskHold] = ConcurrentStableDict()
        self._kernel_read = False
        self._next_token = itertools.count(1)
        # 计数是跨协程 / 跨事件循环共享的进程级状态：`acquire` / `release` 在改计数前后有 await 点
        # （取放系统调用），不加锁会让并发读者互相覆盖计数（表现为提前放掉内核锁或永久泄漏）。
        # 用 `threading.Lock` 而非 `asyncio.Lock`：门是进程级单例，而 pytest-asyncio 每个用例一个新
        # 事件循环，`asyncio.Lock` 会绑死在首个循环上。
        self._count_lock = threading.Lock()
        self._holder_lock = threading.Lock()
        """持有者文件的读改写互斥（诊断落盘，不与 `_count_lock` 混用，避免把文件 I/O 塞进取门热路径）。"""

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

    async def acquire_read(self) -> int:
        """取读门，返回本次份额的 token（释放时凭它销账）。

        **只有持写门的那个任务**取读门才走「借用」（不取内核共享锁、随写门作废）；
        同一进程里的**其它任务**必须排队等写门释放——否则会读到写了一半的数据。

        Returns:
            int: 读份额 token。

        Raises:
            TimeoutError: 等待超时。
        """
        with self._count_lock:
            if self._write_depth and self._write_owner == _task_key():
                token = next(self._next_token)
                self._borrowed_reads[token] = None
                return token
            need_kernel = not self._kernel_read
            if need_kernel:
                # 先占位再出锁：否则并发读者会各取一次内核锁（同一句柄重复加锁会失败）。
                self._kernel_read = True
        if need_kernel:
            try:
                await self._wait_and_lock(False)
            except BaseException:
                with self._count_lock:
                    self._kernel_read = False
                raise
        with self._count_lock:
            token = next(self._next_token)
            self._own_reads[token] = _task_key()
            self._track_read()
        self._record_holder(False)
        return token

    async def release_read(self, token: int) -> None:
        """释放指定读份额（只放自己那份；已退役的借用份额只销账）。

        Args:
            token: `acquire_read` 返回的 token。

        Raises:
            RuntimeError: token 未被本门持有（重复释放 / 释放错对象）。
        """
        with self._count_lock:
            if token in self._borrowed_reads:
                del self._borrowed_reads[token]
                return
            if token in self._retired_reads:
                del self._retired_reads[token]
                return
            if token not in self._own_reads:
                raise RuntimeError(f"门 {self.name} 释放读份额失败：token {token} 未被持有")
            self._untrack_read(self._own_reads[token])
            del self._own_reads[token]
            drop_kernel = not self._own_reads and not self._write_depth and self._kernel_read
            if drop_kernel:
                self._kernel_read = False
        if drop_kernel:
            self._backend.release()
            self._release_holder()

    def owns(self, token: int) -> bool:
        """该读份额 token 是否仍被本门持有（含借用 / 已退役）。

        Args:
            token: `acquire_read` 返回的 token。

        Returns:
            bool: 仍持有返回 True。
        """
        with self._count_lock:
            return token in self._own_reads or token in self._borrowed_reads or token in self._retired_reads

    async def acquire_write(self, *, wait: float | None = None) -> ConcurrentStableList[int]:
        """取写门（独占；同一进程内可重入）。

        本任务持有的读份额先让出（不还内核共享锁，除非本进程已无其它读者），再去排队取
        独占锁；**别的任务**的读份额一律不动——它们收尾后本任务自然拿到写门，这就是
        「并发写排队」，不报错。

        Returns:
            ConcurrentStableList[int]: 让出的读份额 token（写完后由 `release_write` 原样补回）。

        Raises:
            TimeoutError: 等待超时。
        """
        reentered = False
        drop_kernel = False
        released: ConcurrentStableList[int] = ConcurrentStableList()
        with self._count_lock:
            if self._write_depth:
                self._write_depth += 1
                self._track_write()
                reentered = True
            else:
                mine = _task_key()
                released = ConcurrentStableList(token for token, owner in self._own_reads.items() if owner == mine)
                for token in released:
                    del self._own_reads[token]
                    self._untrack_read(mine)
                # **无论本进程还有没有别的读者，都要先让出内核共享锁**：Windows 上同一句柄
                # 对同一区间重复加锁会把模式合并，一次解锁就把整个区间放掉（后续再释放报
                # `ERROR_NOT_LOCKED`），账目与内核状态随即脱节。升级完由 `release_write`
                # 按剩余读份额重新取共享锁。
                drop_kernel = self._kernel_read
                if drop_kernel:
                    self._kernel_read = False
        if reentered:
            # 写门已由本进程持有：不重复取内核锁，只补一条任务级记录（诊断点名用）。
            self._flush_task_holders()
            return released
        if drop_kernel:
            # 先让出共享锁，再排队取独占锁（顺序不能反）。
            self._backend.release()
        await self._wait_and_lock(True, cap=wait)
        with self._count_lock:
            self._write_depth = 1
            self._write_owner = _task_key()
            self._track_write()
        self._record_holder(True)
        return released

    async def release_write(self, restore: ConcurrentStableList[int] | None = None) -> None:
        """释放写门，并恢复升级时让出的读份额。

        **未持写门时不抛错**：`gate_scope` 的 `finally` 无论取写门是否成功都会走到这里，
        抛错会把真正的失败（如等锁超时）盖掉。未持有时只记一条告警，并尽力补回让出的份额。

        **解锁一律同步执行**（不走 `asyncio.to_thread`）：释放常发生在事件循环收尾阶段，
        此时线程池已关闭，`to_thread` 会抛 `RuntimeError: cannot schedule new futures after
        shutdown`，内核锁因此永久泄漏。

        Args:
            restore: `acquire_write` 返回的 token 清单（升级路径传入；None 表示无）。
        """
        with self._count_lock:
            if not self._write_depth:
                held = False
                remaining = 0
            else:
                held = True
                self._write_depth -= 1
                remaining = self._write_depth
                if not remaining:
                    self._write_owner = 0
                    self._write_tasks.clear()
                else:
                    self._untrack_write()
                if not remaining:
                    for token in list(self._borrowed_reads):
                        del self._borrowed_reads[token]
                        self._retired_reads[token] = None
        if not held:
            # 结构要求：取写门失败也走这里。留痕后把让出的份额补回，保证读状态不失衡。
            _LOGGER.warning(
                "gate_release_without_write",
                extra={"gate": self.name, "restore": len(restore or ())},
            )
            self._flush_task_holders()
            if restore:
                await self._restore_reads(restore)
            return
        if remaining:
            self._flush_task_holders()
            return
        self._backend.release()
        self._release_holder()
        # 升级期间让掉的内核共享锁：别的任务仍持有读份额时要补回来，否则它们后续的
        # `release_read` 会去释放一把并不存在的共享锁（Windows 报 158，账目脱节）。
        with self._count_lock:
            need_shared = bool(self._own_reads) and not self._kernel_read
            if need_shared:
                self._kernel_read = True
        if need_shared:
            await self._wait_and_lock(False)
        if restore:
            await self._restore_reads(restore)

    async def _restore_reads(self, restore: ConcurrentStableList[int]) -> None:
        """把让出的读份额补回（需要时重新取内核共享锁并登记 token）。

        Args:
            restore: 要补回的 token 清单。
        """
        with self._count_lock:
            need_kernel = not self._kernel_read
            if need_kernel:
                self._kernel_read = True
        if need_kernel:
            await self._wait_and_lock(False)
        with self._count_lock:
            for token in restore:
                self._own_reads[token] = _task_key()
                self._track_read()
        self._record_holder(False)

    def close(self) -> None:
        """关闭门（会话或进程退出时调用）。"""
        self._backend.close()
        with self._count_lock:
            self._own_reads.clear()
            self._borrowed_reads.clear()
            self._retired_reads.clear()
            self._write_tasks.clear()
            self._read_tasks.clear()
            self._write_depth = 0
            self._kernel_read = False
        with contextlib.suppress(OSError):
            self._holder_file().unlink()
            self._task_hold_path().unlink()

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

    def write_holders(self) -> ConcurrentStableList[str]:
        """当前持有**写门**的任务清单（诊断：区分「独占到门」与「同进程另一协程重入」）。

        Returns:
            ConcurrentStableList[str]: 每条形如 `pid=1 task=2 mode=write depth=1 test=x at=12:00:01`。
        """
        return ConcurrentStableList(hold.render() for hold in self._write_tasks.values())

    def holder_tasks(self) -> ConcurrentStableList[str]:
        """当前持有本门（读或写）的任务清单（诊断：写者进门前采样，看谁在挡）。

        Returns:
            ConcurrentStableList[str]: 写持有者在前、读持有者在后。
        """
        holders = self.write_holders()
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
        """登记本任务持有写门（**必须在 `_count_lock` 内调用**）。

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
        """注销本任务的一次写持有（在 `_count_lock` 内调用；深度归零即删记录）。"""
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
        """登记本任务持有一个读份额（**必须在 `_count_lock` 内调用**）。"""
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
        """注销某个任务的一个读份额（在 `_count_lock` 内调用；份额归零即删记录）。

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

    def _record_holder(self, write: bool) -> None:
        """记录本进程持有门（诊断：等门 / 超时时列出真实持有者与用例名）。

        每进程一份独立文件、释放时把 `hold` 置 0：卡住时可以读出**所有仍持有**的进程，
        不会被后来者覆盖（单文件版本只能看到最后一次取锁，实测误导过排查）。

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

    def _describe_holder(self) -> str:
        """列出**当前仍持有**本门的任务（跨进程扫描各 pid 的记录文件）。

        两类记录合并：进程级（`hold=1` 一行，旧版遗留）与任务级（读 / 写各一行）。**写门只认任务级**
        ——进程级那行只说得清「某个进程在写」，而并发问题恰恰出在「同进程哪个协程也在写」。

        **死进程的记录一律过滤**——进程被强杀时记录留在盘上，本轮实测残留 117 份，
        不判存活就会把早已退出的进程当持有者点名，误导排查。

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

    def _log_wait(self, message: str) -> None:
        """把等门告警 / 超时追加到诊断文件（pytest 会捕获 stdout，落文件才留得住）。

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
        """等门告警 / 超时时抓一份全进程栈（开关与节流由诊断工具决定）。

        Args:
            waited: 已等待秒数。
            reason: 触发原因（`warn` / `timeout`）。
        """
        diagnostics.note_gate_wait(
            self._holder_path.with_name(f"gate-stacks-{os.getpid()}.log"),
            gate_name=gate_label(self.name),
            waited=waited,
            reason=reason,
            holder=self._describe_holder(),
        )

    async def _wait_and_lock(self, write: bool, *, cap: float | None = None) -> None:
        """排队等待直到拿到门（事件循环内异步轮询，不占线程池）。

        **上限**（13_08 T7）：写门缺省 `write_wait_cap()`（5s，超时即失败并点名持有者）；
        读门缺省 `DEFAULT_TIMEOUT`；调用方显式传 `cap` 时按 `min(DEFAULT_TIMEOUT, cap)`
        （整段临界区的等门预算，如 `GATE_CRITICAL_WAIT`）。

        为什么写门要短上限：正常写是毫秒级，等超过几秒说明有任务长期持门（整条用例持门 /
        读会话未释放 / 进程卡住），继续等只会把卡点拖成整批超时——立即失败才能定位持锁用例。

        Args:
            write: 独占 True，共享 False。
            cap: 显式硬上限（秒）；None 走缺省上限。

        Raises:
            TimeoutError: 超过上限（写门 `write_wait_cap()` / 读门 `DEFAULT_TIMEOUT` / 显式 `cap`）。
        """
        started = time.monotonic()
        if cap is not None:
            limit = min(DEFAULT_TIMEOUT, cap)
        elif write:
            limit = write_wait_cap()
        else:
            limit = DEFAULT_TIMEOUT
        deadline = started + limit
        warned = False
        delay = _RETRY_MIN
        while not self._backend.try_acquire(write=write):
            now = time.monotonic()
            if not warned and now - started >= WARN_AFTER:
                warned = True
                message = (
                    f"[rwlock] 等待门 {gate_label(self.name)} 已 {now - started:.1f}s；"
                    f"持有者：{self._describe_holder()}"
                )
                print(message, flush=True)
                self._log_wait(message)
                self._note_gate_wait(now - started, "warn")
            if now >= deadline:
                message = (
                    f"等待数据库门超时（{limit:.1f}s）：{gate_label(self.name)}；"
                    f"持有者：{self._describe_holder()}；"
                    "等满硬上限说明有任务长期持门（整条用例持门 / 读会话未释放 / 进程卡住）"
                )
                self._log_wait(message)
                self._note_gate_wait(now - started, "timeout")
                raise TimeoutError(message)
            await asyncio.sleep(min(delay, max(deadline - now, 0.0)))
            delay = min(delay * 2, _RETRY_MAX)
