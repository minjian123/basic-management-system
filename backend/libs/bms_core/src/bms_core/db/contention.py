"""数据库锁争用识别：把「并发争用」与「主库故障」分开。

为什么需要：`OperationalError` 是两者的公共通道。锁等待 / 死锁重试即可恢复，主库不可用则要
触发**只读降级**（本进程后续写请求全被拒）。混为一谈会把一次几十毫秒的锁冲突放大成整段只读
窗口——05_02 推送复盘实证：一条 `database is locked` 让一个 worker 的后续写请求全部 503，
随机打死无关用例。

口径：按方言白名单匹配异常文本与驱动错误码，**未命中一律按真故障处理**（fail-safe 到旧行为：
宁可信其有，不能把真故障漏成「可重试」）。
"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableList

__all__ = ["RETRY_AFTER_SECONDS", "contention_driver", "is_lock_contention"]

RETRY_AFTER_SECONDS = 1
"""`Retry-After` 秒数：一次瞬时冲突的典型恢复时间；退避策略归客户端（本层只给下限提示）。"""

_MARKERS: ConcurrentStableList[tuple[str, str]] = ConcurrentStableList(
    (
        ("sqlite", "database is locked"),
        ("sqlite", "database table is locked"),
        ("mysql", "lock wait timeout exceeded"),
        ("mysql", "deadlock found"),
        ("mysql", "try restarting transaction"),
        ("postgresql", "deadlock detected"),
        ("postgresql", "could not obtain lock"),
    )
)
"""方言 → 争用标记（小写匹配；`mysql` 另有错误码兜底，见 `_MYSQL_CONTENTION_ERRNOS`）。"""

_MYSQL_CONTENTION_ERRNOS: ConcurrentStableList[int] = ConcurrentStableList((1205, 1213))
"""MySQL 争用错误码：1205 锁等待超时、1213 死锁回滚（文本可能被本地化，故按码兜底）。"""


def _original(exc: BaseException) -> BaseException:
    """取 SQLAlchemy 包装的 DBAPI 原始异常（无 `orig` 时返回自身）。"""
    original = getattr(exc, "orig", None)
    return original if isinstance(original, BaseException) else exc


def _errno(exc: BaseException) -> int | None:
    """取 DBAPI 异常的首个参数（MySQL / pymysql 在这里放错误码）。"""
    args = getattr(_original(exc), "args", ())
    first = args[0] if args else None
    return first if isinstance(first, int) else None


def contention_driver(exc: BaseException) -> str | None:
    """判断异常是否属于锁争用，并给出方言标签。

    Args:
        exc: 待判定异常（SQLAlchemy 包装或 DBAPI 原始异常均可）。

    Returns:
        str | None: 争用命中的方言（`sqlite` / `mysql` / `postgresql`）；非争用返回 `None`。
    """
    errno = _errno(exc)
    if errno is not None and any(errno == code for code in _MYSQL_CONTENTION_ERRNOS):
        return "mysql"
    text = str(_original(exc)).lower()
    for driver, marker in _MARKERS:
        if marker in text:
            return driver
    return None


def is_lock_contention(exc: BaseException) -> bool:
    """异常是否为锁争用（重试可恢复，不等于主库故障）。

    Args:
        exc: 待判定异常。

    Returns:
        bool: 争用为 `True`。
    """
    return contention_driver(exc) is not None
