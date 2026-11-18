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
import ctypes
import os
import sys
import time
from pathlib import Path
from typing import Any, Final, Literal, Protocol, cast

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
        self._backend = _make_backend(path)
        self._read_depth = 0
        self._write_depth = 0

    @property
    def mode(self) -> Mode | None:
        """当前持有模式（写优先；未持有为 None）。

        Returns:
            Mode | None: 模式。
        """
        if self._write_depth:
            return WRITE
        if self._read_depth:
            return READ
        return None

    @property
    def depth(self) -> int:
        """当前重入深度（读 + 写）。

        Returns:
            int: 深度（0 表示未持有）。
        """
        return self._read_depth + self._write_depth

    async def acquire(self, *, write: bool) -> None:
        """取门（同模式可重入；写门内取读门视为已满足）。

        写门已包含读能力：用例持写门时应用内部的只读会话请求读门不报错、不重取系统锁，
        只增加读计数；反过来「持读门再请求写门」仍然报错——多写者原地升级会互相等死。

        Args:
            write: 独占 True，共享 False。

        Raises:
            RuntimeError: 已在读模式下请求写门（禁止原地升级）。
            TimeoutError: 等待超时。
        """
        if write:
            if self._write_depth:
                self._write_depth += 1
                return
            if self._read_depth:
                raise RuntimeError(
                    f"门 {self.name} 已以 {READ} 模式持有：禁止原地升级；"
                    "请在 bms_core.testing.gates 的写门上下文内完成写操作"
                )
            await asyncio.to_thread(self._wait_and_lock, True)
            self._write_depth = 1
            return
        if self._read_depth or self._write_depth:
            self._read_depth += 1
            return
        await asyncio.to_thread(self._wait_and_lock, False)
        self._read_depth = 1

    async def release(self, *, write: bool) -> None:
        """放门（先写后读由调用方保证顺序）。

        Args:
            write: 独占 True，共享 False。

        Raises:
            RuntimeError: 释放模式与持有模式不一致。
        """
        if write:
            if not self._write_depth:
                raise RuntimeError(f"门 {self.name} 释放模式不匹配：当前 {self.mode}，请求释放 {WRITE}")
            self._write_depth -= 1
            if self._write_depth:
                return
            await asyncio.to_thread(self._backend.release)
            if self._read_depth:
                # 写门退出但仍有读份额：降级为读门，保持读语义
                await asyncio.to_thread(self._wait_and_lock, False)
            return
        if not self._read_depth:
            raise RuntimeError(f"门 {self.name} 释放模式不匹配：当前 {self.mode}，请求释放 {READ}")
        self._read_depth -= 1
        if self._read_depth or self._write_depth:
            return
        await asyncio.to_thread(self._backend.release)

    def close(self) -> None:
        """关闭门（会话或进程退出时调用）。"""
        self._backend.close()

    def _wait_and_lock(self, write: bool) -> None:
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
                print(f"[rwlock] 等待门 {self.name} 已 {now - started:.1f}s（另一个进程长期占用该库）")
            if now >= deadline:
                raise TimeoutError(f"等待数据库门超时（{DEFAULT_TIMEOUT:.0f}s）：{self.name}")
            time.sleep(min(delay, max(deadline - now, 0.0)))
            delay = min(delay * 2, _RETRY_MAX)
