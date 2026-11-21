"""跨进程测试锁：共享测试库上的「先查后建 / 先查后写」必须串行。

为什么需要：单库化（04-6-2）后全 worker 共用一份 `.cache/test/*.db`。

- **先查后写**：SQLite 的「唯一约束含 `deleted_at`」在 NULL 上**不生效**（NULL ≠ NULL），两个 worker
  同时「查无此行 → 插入」会各插一行同码数据，后续 `scalar_one_or_none` 直接 `MultipleResultsFound`。
- **先查后建**：`create_all(checkfirst=True)` 的 `has_table` 看不到**他人未提交**的建表事务，两个 worker
  同时首次建同一张表，后提交的一方撞 `table ... already exists`。

SQLite 写锁不能拿来互斥（自己也要写库，会自锁），故用文件锁：`O_CREAT|O_EXCL` 原子创建，
跨进程有效、与数据库无关。

**自愈口径（2026-11-15 收口）**：放锁时 `unlink` 在 Windows 上会被等待方的读句柄拒绝（实测
`EACCES`），残锁会让所有等待方一直等到超时。因此：

- 持锁方每 `HEARTBEAT_INTERVAL` 秒刷新锁文件 mtime（心跳），活锁永不因「持有太久」被误抢；
- 等待方按 `STALE_AFTER`（5s）判陈旧：超过约 3 个心跳周期未刷新，必然是进程被杀 / 线程卡死 / 残锁；
- 非 POSIX **不读锁文件内容**（读句柄正是让持锁方 `unlink` 失败的根因），只按 mtime 判；
- 放锁失败重试三次，仍失败交给 5s 陈旧判据，不再静默把整轮拖到等锁上限（10s）。
"""

import os
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from bms_core.testing.paths import project_root

DEFAULT_TIMEOUT = 10.0
"""默认等锁上限（秒）：超时即报错，不静默并行。

2026-11-21 由 180s 收到 10s：测试等待超过 10s 就是用例问题 / 残锁信号，快速失败并点名持有者。
"""

STALE_AFTER = 5.0
"""陈旧锁判定阈值（秒）：锁文件 mtime 超过该值即视为持有方已死 / 卡死，清理重取。

必须**小于**等锁上限（10s），否则等待方永远等不到清理时机；持锁方每
`HEARTBEAT_INTERVAL` 秒刷新 mtime，活锁不会被误判。
"""

HEARTBEAT_INTERVAL = 1.5
"""持锁期心跳间隔（秒）：取 `STALE_AFTER` 的约 1/3，允许连续两次心跳丢失。"""

_POSIX = os.name == "posix"
"""是否 POSIX。

Windows 不做进程存活探测（`os.kill(pid, 0)` 会走 `TerminateProcess`，真的结束进程），
且**不读锁文件内容**——读句柄会让持锁方的 `unlink` 抛 `EACCES`（实测 errno=13），
正是残锁的来源；残锁交给心跳 + 时长判据。
"""


def _holder_pid(content: str) -> int | None:
    """解析锁文件记录的持锁进程号（`pid|时间戳` 形态；兼容旧版纯数字 / 文本）。

    Args:
        content: 锁文件内容。

    Returns:
        int | None: 进程号；无法解析为 `None`（按未知持有者处理）。
    """
    head = content.split("|", 1)[0].strip()
    return int(head) if head.isdigit() else None


def _pid_alive(pid: int) -> bool:
    """判断持锁进程是否仍存活（仅 POSIX；其他平台恒返回 `True`，交给时长判据）。

    Args:
        pid: 进程号。

    Returns:
        bool: 存活 `True`。
    """
    if not _POSIX:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _is_stale(path: Path) -> bool:
    """判定锁文件是否陈旧（超时长阈值，或 POSIX 下持锁进程已死）。

    Windows 只按 mtime 判：读锁文件内容会与持锁方 `unlink` 抢共享句柄（`EACCES`），
    心跳已保证活锁的 mtime 持续新鲜，完全没有读内容的必要。

    Args:
        path: 锁文件路径。

    Returns:
        bool: 陈旧 `True`。
    """
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return False
    if time.time() - mtime > STALE_AFTER:
        return True
    if not _POSIX:
        return False
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return False
    pid = _holder_pid(content)
    return pid is not None and pid != os.getpid() and not _pid_alive(pid)


def _heartbeat(path: Path, token: str, stop: threading.Event) -> None:
    """持锁期心跳：按固定间隔刷新锁文件 mtime（锁已被他人接管即停）。

    Args:
        path: 锁文件路径。
        token: 本进程写入的锁内容（`pid|创建时间`），用于识别「锁已被清理重取」。
        stop: 停止信号（放锁时置位，立即唤醒）。
    """
    while not stop.wait(HEARTBEAT_INTERVAL):
        try:
            if path.read_text(encoding="utf-8") != token:
                return
            os.utime(path, None)
        except OSError:
            return


def _release(path: Path) -> None:
    """删除锁文件（共享冲突重试三次，仍失败交给陈旧判据）。

    Windows 上 `unlink` 会被他人的读句柄拒绝（`EACCES`）；重试只是降低概率，
    真正的兜底是 `STALE_AFTER` 超时清理。

    Args:
        path: 锁文件路径。
    """
    for delay in (0.0, 0.01, 0.05):
        if delay:
            time.sleep(delay)
        try:
            path.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError:
            continue


@contextmanager
def file_lock(name: str, *, timeout: float = DEFAULT_TIMEOUT) -> Generator[None]:
    """取跨进程文件锁（`<工程根>/.cache/test/<name>.lock`）。

    锁文件记录 `pid|创建时间戳`；持锁期间后台线程按 `HEARTBEAT_INTERVAL` 刷新 mtime；
    等锁时按 `_is_stale` 判陈旧（超 30s 未刷新 / POSIX 下持锁进程已死）并清理重取。

    Args:
        name: 锁名（建议语义化，如 `permission-admin-seed`）。
        timeout: 等锁上限（秒）。

    Yields:
        None: 持锁区间。

    Raises:
        TimeoutError: 等待超时（说明有进程长期占锁）。
    """
    path = project_root() / ".cache" / "test" / f"{name}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _is_stale(path):
                _release(path)
            if time.monotonic() > deadline:
                raise TimeoutError(f"等待测试锁超时：{path}") from None
            time.sleep(0.05)
            continue
        token = f"{os.getpid()}|{time.time():.6f}"
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(token)
        break
    stop = threading.Event()
    beat = threading.Thread(target=_heartbeat, args=(path, token, stop), daemon=True, name=f"lock-beat-{name}")
    beat.start()
    try:
        yield
    finally:
        stop.set()
        beat.join(timeout=1.0)
        _release(path)
