"""跨进程测试锁：共享测试库上的「先查后建 / 先查后写」必须串行。

为什么需要：单库化（04-6-2）后全 worker 共用一份 `.cache/test/*.db`。

- **先查后写**：SQLite 的「唯一约束含 `deleted_at`」在 NULL 上**不生效**（NULL ≠ NULL），两个 worker
  同时「查无此行 → 插入」会各插一行同码数据，后续 `scalar_one_or_none` 直接 `MultipleResultsFound`。
- **先查后建**：`create_all(checkfirst=True)` 的 `has_table` 看不到**他人未提交**的建表事务，两个 worker
  同时首次建同一张表，后提交的一方撞 `table ... already exists`。

SQLite 写锁不能拿来互斥（自己也要写库，会自锁），故用文件锁：`O_CREAT|O_EXCL` 原子创建，
跨进程有效、与数据库无关。
"""

import os
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path

from bms_core.testing.paths import project_root

DEFAULT_TIMEOUT = 300.0
"""默认等锁上限（秒）：超时即报错，不静默并行。

2026-11-14 由 120s 提到 300s：CI 慢机上导出 / 文件仓写入类用例持锁可超过 2 分钟（bms#1659 实测超时）。
"""

STALE_AFTER = 600.0
"""陈旧锁判定阈值（秒）：持锁超过该时长视为异常占用，直接清理重取。"""

_POSIX = os.name == "posix"
"""是否 POSIX（进程存活探测只在 POSIX 可用；Windows 交给时长判据）。"""


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
    """判断持锁进程是否仍存活（仅 POSIX；其他平台恒返回 `True`，交给时长判据兜底）。

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
    """判定锁文件是否陈旧（持锁进程已死，或持锁时长超 `STALE_AFTER`）。

    Args:
        path: 锁文件路径。

    Returns:
        bool: 陈旧 `True`。
    """
    try:
        stat = path.stat()
        content = path.read_text(encoding="utf-8")
    except OSError:
        return False
    pid = _holder_pid(content)
    if pid is not None and pid != os.getpid() and not _pid_alive(pid):
        return True
    return time.time() - stat.st_mtime > STALE_AFTER


@contextmanager
def file_lock(name: str, *, timeout: float = DEFAULT_TIMEOUT) -> Generator[None]:
    """取跨进程文件锁（`<工程根>/.cache/test/<name>.lock`）。

    锁文件记录 `pid|创建时间戳`；等锁时先判陈旧（持锁进程已死 / 持锁过久）并清理重取，
    避免 worker 被 xdist 杀掉或进程崩溃后残锁永久阻塞后续用例。

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
                with suppress(FileNotFoundError):
                    path.unlink()
                continue
            if time.monotonic() > deadline:
                raise TimeoutError(f"等待测试锁超时：{path}") from None
            time.sleep(0.05)
            continue
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(f"{os.getpid()}|{time.time():.0f}")
        break
    try:
        yield
    finally:
        with suppress(FileNotFoundError):
            path.unlink()
