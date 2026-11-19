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
import os
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Final, Literal, Protocol, cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.testing import diagnostics
from bms_core.testing.paths import project_root

DEFAULT_TIMEOUT: Final = 180.0
"""等门上限（秒）：超时即报错，不静默降级。"""

WARN_AFTER: Final = 10.0
"""等门告警阈值（秒）：超过即打印一行，便于定位长期占用。"""

DEFAULT_GATE_DIRNAME: Final = "test"
"""门文件所在目录名（`<工程根>/.cache/test/`，与共享测试库同区）。"""

Mode = Literal["read", "write"]
"""门模式（读共享 / 写独占）。"""

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
        """释放锁。

        Raises:
            OSError: 系统调用失败（句柄已失效等）。
        """
        overlapped = _Overlapped()
        released = self._unlock(  # pyright: ignore[reportCallIssue]
            self._handle, 0, 1, 0, ctypes.byref(overlapped)
        )
        if not released:
            raise ctypes.WinError(ctypes.get_last_error())

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
        self._kernel_read = False
        self._next_token = itertools.count(1)
        # 计数是跨协程 / 跨事件循环共享的进程级状态：`acquire` / `release` 在改计数前后有 await 点
        # （取放系统调用），不加锁会让并发读者互相覆盖计数（表现为提前放掉内核锁或永久泄漏）。
        # 用 `threading.Lock` 而非 `asyncio.Lock`：门是进程级单例，而 pytest-asyncio 每个用例一个新
        # 事件循环，`asyncio.Lock` 会绑死在首个循环上。
        self._count_lock = threading.Lock()

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

        写门持有期间取的读门是**借用**（不取内核共享锁，随写门作废），token 同样返回。

        Returns:
            int: 读份额 token。

        Raises:
            TimeoutError: 等待超时。
        """
        with self._count_lock:
            if self._write_depth:
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
            del self._own_reads[token]
            drop_kernel = not self._own_reads and not self._write_depth
            if drop_kernel:
                self._kernel_read = False
        if drop_kernel:
            self._backend.release()

    def owns(self, token: int) -> bool:
        """该读份额 token 是否仍被本门持有（含借用 / 已退役）。

        Args:
            token: `acquire_read` 返回的 token。

        Returns:
            bool: 仍持有返回 True。
        """
        with self._count_lock:
            return token in self._own_reads or token in self._borrowed_reads or token in self._retired_reads

    async def acquire_write(self) -> ConcurrentStableList[int]:
        """取写门（独占；同一进程内可重入）。

        若本任务仍持读份额（嵌套升级），先**只释放本任务的**份额再取写门，返回被释放的
        token 供 `release_write` 恢复；其它任务的读份额一律不动（动了对方的 SQLite 读事务
        还开着，写者提交时会被它挡住并互等超时）。

        Returns:
            ConcurrentStableList[int]: 本次升级临时让出的读份额 token（无则空）。

        Raises:
            RuntimeError: 本进程的**其它任务**仍持读份额（并发读不能原地升级成写）。
            TimeoutError: 等待超时。
        """
        with self._count_lock:
            if self._write_depth:
                self._write_depth += 1
                return ConcurrentStableList()
            mine = _task_key()
            others = [token for token, owner in self._own_reads.items() if owner != mine]
            if others:
                raise RuntimeError(
                    f"门 {self.name} 还有其它任务的读份额：禁止原地升级；写操作必须在没有并发读事务时进行"
                )
            released: ConcurrentStableList[int] = ConcurrentStableList(self._own_reads)
            for token in released:
                del self._own_reads[token]
            drop_kernel = bool(released) and not self._write_depth
            if drop_kernel:
                self._kernel_read = False
        if drop_kernel:
            # 先让出共享锁，再排队取独占锁（顺序不能反）。
            self._backend.release()
        await self._wait_and_lock(True)
        with self._count_lock:
            self._write_depth = 1
        self._record_holder(True)
        return released

    async def release_write(self, restore: ConcurrentStableList[int] | None = None) -> None:
        """释放写门，并恢复升级时让出的读份额。

        **解锁一律同步执行**（不走 `asyncio.to_thread`）：释放常发生在事件循环收尾阶段，
        此时线程池已关闭，`to_thread` 会抛 `RuntimeError: cannot schedule new futures after
        shutdown`，内核锁因此永久泄漏。

        Args:
            restore: `acquire_write` 返回的 token 清单（升级路径传入；None 表示无）。

        Raises:
            RuntimeError: 当前未持写门。
        """
        with self._count_lock:
            if not self._write_depth:
                raise RuntimeError(f"门 {self.name} 释放模式不匹配：当前 {self.mode}，请求释放 {WRITE}")
            self._write_depth -= 1
            remaining = self._write_depth
            if not remaining:
                for token in list(self._borrowed_reads):
                    del self._borrowed_reads[token]
                    self._retired_reads[token] = None
        if remaining:
            return
        self._backend.release()
        if not restore:
            return
        await self._wait_and_lock(False)
        with self._count_lock:
            self._kernel_read = True
            for token in restore:
                self._own_reads[token] = _task_key()
        self._record_holder(False)

    def close(self) -> None:
        """关闭门（会话或进程退出时调用）。"""
        self._backend.close()
        with self._count_lock:
            self._own_reads.clear()
            self._borrowed_reads.clear()
            self._retired_reads.clear()
            self._write_depth = 0
            self._kernel_read = False
        with contextlib.suppress(OSError):
            self._holder_path.unlink()

    def _record_holder(self, write: bool) -> None:
        """记录当前持有者（诊断：等门告警 / 超时时打印持有者进程与获取位置）。

        写独立文件而不是锁文件本体：字节锁区间与文件内容共用同一 fd 时，写入会移动偏移、影响
        `UnlockFileEx` 的区间语义。诊断写盘失败不影响加解锁（失败即静默跳过）。

        Args:
            write: 独占 True，共享 False。
        """
        stack = traceback.format_stack()[-8:-2]
        frames = " <- ".join(line.strip().splitlines()[0] for line in stack if line.strip())
        payload = f"pid={os.getpid()} mode={WRITE if write else READ} at={time.strftime('%H:%M:%S')} | {frames}"
        with contextlib.suppress(OSError):
            self._holder_path.write_text(payload, encoding="utf-8")

    def _describe_holder(self) -> str:
        """读取持有者诊断信息（读不到时返回「未知」）。

        Returns:
            str: 持有者描述。
        """
        try:
            return self._holder_path.read_text(encoding="utf-8")[:600]
        except OSError:
            return "未知（诊断文件不可读）"

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
            gate_name=self.name,
            waited=waited,
            reason=reason,
            holder=self._describe_holder(),
        )

    async def _wait_and_lock(self, write: bool) -> None:
        """阻塞等待直到拿到门（在工作线程中执行，不阻塞事件循环）。

        Args:
            write: 独占 True，共享 False。

        Raises:
            TimeoutError: 等待超过 `DEFAULT_TIMEOUT`。
        """
        started = time.monotonic()
        deadline = started + DEFAULT_TIMEOUT
        warned = False
        delay = _RETRY_MIN
        while not self._backend.try_acquire(write=write):
            now = time.monotonic()
            if not warned and now - started >= WARN_AFTER:
                warned = True
                message = f"[rwlock] 等待门 {self.name} 已 {now - started:.1f}s；持有者：{self._describe_holder()}"
                print(message, flush=True)
                self._log_wait(message)
                self._note_gate_wait(now - started, "warn")
            if now >= deadline:
                message = f"等待数据库门超时（{DEFAULT_TIMEOUT:.0f}s）：{self.name}；持有者：{self._describe_holder()}"
                self._log_wait(message)
                self._note_gate_wait(now - started, "timeout")
                raise TimeoutError(message)
            await asyncio.sleep(min(delay, max(deadline - now, 0.0)))
            delay = min(delay * 2, _RETRY_MAX)
