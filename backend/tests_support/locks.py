"""跨进程测试锁：共享测试库上「先查后写」的全局种子必须串行。

为什么需要：单库化（04-6-2）后全 worker 共用一份 `.cache/test/*.db`。SQLite 的「唯一约束含
`deleted_at`」在 NULL 上**不生效**（NULL ≠ NULL），两个 worker 同时「查无此行 → 插入」会各插一行
同码数据，后续 `scalar_one_or_none` 直接 `MultipleResultsFound`。SQLite 写锁不能拿来互斥
（自己也要写库，会自锁），故用文件锁：`O_CREAT|O_EXCL` 原子创建，跨进程有效、与数据库无关。
"""

import os
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress

from bms_core.testing.paths import project_root

DEFAULT_TIMEOUT = 120.0
"""默认等锁上限（秒）：超时即报错，不静默并行。"""


@contextmanager
def file_lock(name: str, *, timeout: float = DEFAULT_TIMEOUT) -> Generator[None]:
    """取跨进程文件锁（`<工程根>/.cache/test/<name>.lock`）。

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
            if time.monotonic() > deadline:
                raise TimeoutError(f"等待测试锁超时：{path}") from None
            time.sleep(0.05)
            continue
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(str(os.getpid()))
        break
    try:
        yield
    finally:
        with suppress(FileNotFoundError):
            path.unlink()
