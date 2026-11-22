"""可选诊断探针（`BMS_TEST_LOCK_PROBE=1`）：记录 SQLite 语句、连接与门区间，定位 `database is locked` 竞争方。

默认关闭、零开销；只在排查「谁在门外写」时打开。开关与落点见 `plugin.pytest_configure`
（`BMS_TEST_LOCK_PROBE_DIR` 可改落点，缺省 `tmp/lock-probe/`）。诊断代码不参与覆盖率判定，
函数级豁免理由见各函数。
"""

from __future__ import annotations

import contextlib
import itertools
import os
import sqlite3
import threading
import time
import traceback
from pathlib import Path
from typing import Any

_enabled = False
"""是否已安装（幂等）。"""

_path: Path | None = None
"""本进程探针文件路径。"""

_WRITE_HEADS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "REPLACE",
    "CREATE",
    "DROP",
    "ALTER",
    "BEGIN",
    "COMMIT",
    "ROLLBACK",
    "SAVEPOINT",
    "RELEASE",
)
"""需要记录的语句开头（读语句不记，否则日志量爆炸）。"""

_LOCK = threading.Lock()
"""同进程多线程写同一文件的互斥。"""

_SEQ = itertools.count(1)
"""连接编号。"""


def _emit(line: str) -> None:  # pragma: no cover - 默认关闭，正常测试不写探针日志
    """追加一行（失败即静默：探针不得影响被测行为）。

    Args:
        line: 待写内容（不含换行）。
    """
    path = _path
    if path is None:
        return
    with _LOCK:
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass


def note(event: str, detail: str = "") -> None:  # pragma: no cover - 默认关闭，门内只走一次布尔判断即返回
    """记录一个门 / 错误事件。

    Args:
        event: 事件名（`gate+` / `gate-` / `error` / `rebuild`）。
        detail: 说明。
    """
    if not _enabled:
        return
    _emit(f"{time.time():.6f}\t{os.getpid()}\t{threading.get_ident()}\t{event}\t{detail}")


def install() -> None:  # pragma: no cover - 仅诊断期按环境变量手工安装
    """安装 sqlite3 语句记录（必须在任何连接建立之前调用）与「门外写」调用栈抓取。"""
    global _enabled, _path
    if _enabled:
        return
    root = Path(os.environ.get("BMS_TEST_LOCK_PROBE_DIR", "D:/Develop/bizs/tmp/lock-probe"))
    root.mkdir(parents=True, exist_ok=True)
    _path = root / f"probe-{os.getpid()}.log"
    _enabled = True
    _install_sqlite_trace()
    _install_session_probe()


def _install_sqlite_trace() -> None:  # pragma: no cover - 由 install() 在诊断期调用
    """给每个 sqlite 连接挂语句 trace（记录库文件名与连接号）。"""
    original = sqlite3.connect

    def _connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        """包装 `sqlite3.connect`。

        Args:
            *args: 透传。
            **kwargs: 透传。

        Returns:
            sqlite3.Connection: 已挂 trace 的连接。
        """
        target = str(args[0]) if args else str(kwargs.get("database", "?"))
        label = Path(target).name or target
        conn_id = next(_SEQ)
        connection = original(*args, **kwargs)

        def _trace(sql: str) -> None:
            """trace 回调（在 aiosqlite 线程执行）。

            Args:
                sql: 执行中的语句。
            """
            head = sql.lstrip()[:12].upper()
            if head.startswith(_WRITE_HEADS):
                _emit(
                    f"{time.time():.6f}\t{os.getpid()}\t{threading.get_ident()}\tSQL\t{label}|c{conn_id}|{sql.strip()[:180]}"
                )

        with contextlib.suppress(AttributeError, sqlite3.Error):
            connection.set_trace_callback(_trace)
        _emit(f"{time.time():.6f}\t{os.getpid()}\t{threading.get_ident()}\tOPEN\t{label}|c{conn_id}")
        return connection

    sqlite3.connect = _connect  # type: ignore[assignment]


def _install_session_probe() -> None:  # pragma: no cover - 由 install() 在诊断期调用
    """在 `AsyncSession` 上抓「不在门内的写」调用栈（`GATE_LABEL` 为空即门外）。"""
    from sqlalchemy.ext.asyncio import AsyncSession

    from bms_core.testing.gates import GATE_LABEL

    def _is_write(statement: object) -> bool:
        """判断语句是否写操作（按 SQLAlchemy 构造名）。

        Args:
            statement: 待执行语句。

        Returns:
            bool: 写语句 True。
        """
        return type(statement).__name__ in {"Insert", "Update", "Delete"}

    def _stack(event: str, detail: str) -> None:
        """记录调用栈（只留业务帧）。

        Args:
            event: 事件名。
            detail: SQL / 方法说明。
        """
        if GATE_LABEL.get():
            return
        frames = [
            line.strip()
            for line in traceback.format_stack()[:-2]
            if ("\\tests\\" in line or "tests_support" in line) and "conftest.py" not in line
        ]
        _emit(
            f"{time.time():.6f}\t{os.getpid()}\t{threading.get_ident()}\tOUTSIDE\t{event} "
            f"{' '.join(detail.split())[:80]} || {' <- '.join(frames[-4:])[:400]}"
        )

    original_execute = AsyncSession.execute
    original_flush = AsyncSession.flush
    original_commit = AsyncSession.commit

    async def _execute(self: AsyncSession, statement: Any, *args: Any, **kwargs: Any) -> Any:
        """包一层 `execute`（写语句门外即记栈）。"""
        if _is_write(statement):
            _stack("execute", str(statement))
        return await original_execute(self, statement, *args, **kwargs)

    async def _flush(self: AsyncSession, objects: Any = None) -> None:
        """包一层 `flush`（ORM 写在这里落库）。"""
        _stack("flush", "session.flush")
        await original_flush(self, objects)

    async def _commit(self: AsyncSession) -> None:
        """包一层 `commit`（提交前的未提交写同样可能持锁）。"""
        _stack("commit", "session.commit")
        await original_commit(self)

    AsyncSession.execute = _execute  # type: ignore[method-assign]
    AsyncSession.flush = _flush  # type: ignore[method-assign]
    AsyncSession.commit = _commit  # type: ignore[method-assign]
