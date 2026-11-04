"""SQLite 引擎统一口径：写独占排队 + 并发读（测试 / 开发共用）。

**为什么需要**：SQLite 写只能单写者。默认事务是 deferred——先读后写时写锁在**中途**升级，
升级失败会报 `database is locked`；共享测试库全 worker 叠加时尤甚。本模块统一两件事：

1. 所有 SQLite 连接带 `timeout=30`（驱动层忙等上限；不再是默认 5s）；
2. 所有 SQLite 连接统一 `timeout=30`（驱动层忙等上限；不再是默认 5s）。
   `immediate=True` 可额外在事务起点发 `BEGIN IMMEDIATE`（写锁先排队），但当前测试的
   「外层回滚事务 + 应用连接」模型会互相等锁，故缺省关闭，待事务模型重做后启用。

口径只作用于 `sqlite` 方言；MySQL / PostgreSQL / 达梦原样返回，不引入任何连接参数。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext import asyncio as sa_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

__all__ = [
    "SQLITE_BUSY_TIMEOUT_SECONDS",
    "create_async_engine",
    "is_sqlite_url",
]

SQLITE_BUSY_TIMEOUT_SECONDS = 30
"""SQLite 写锁忙等上限（秒）；与共享库建表时的 `PRAGMA busy_timeout` 同值。"""


def is_sqlite_url(url: str) -> bool:
    """连接串是否 SQLite 方言（`sqlite` / `sqlite+aiosqlite`）。

    Args:
        url: 数据库连接串。

    Returns:
        bool: SQLite 方言返回 True。
    """
    return url.split(":", 1)[0].split("+", 1)[0] == "sqlite"


def create_async_engine(url: str, **kwargs: Any) -> AsyncEngine:
    """创建异步引擎；SQLite 追加写排队口径，其它方言原样透传。

    Args:
        url: 数据库连接串。
        **kwargs: `create_async_engine` 关键字参数；另支持 `immediate`（SQLite 是否在事务
            起点发 `BEGIN IMMEDIATE`；缺省 False——与「外层回滚事务 + 应用连接」的测试隔离
            模型不兼容，需重做事务模型后再启用）。`connect_args` 会与 SQLite 口径合并。

    Returns:
        AsyncEngine: 引擎实例。
    """
    immediate = bool(kwargs.pop("immediate", False))
    if not is_sqlite_url(url):
        return sa_asyncio.create_async_engine(url, **kwargs)
    connect_args = dict(kwargs.pop("connect_args", {}) or {})
    connect_args.setdefault("timeout", SQLITE_BUSY_TIMEOUT_SECONDS)
    if immediate:
        # `isolation_level=None`：由 SQLAlchemy 显式发 `BEGIN`，begin 钩子才能换成
        # `BEGIN IMMEDIATE`；仅在启用写队列时设置，避免改变默认事务语义。
        connect_args.setdefault("isolation_level", None)
    engine = sa_asyncio.create_async_engine(url, connect_args=connect_args, **kwargs)
    dialect = getattr(engine, "dialect", None)
    if immediate and dialect is not None and dialect.name == "sqlite":
        _install_begin_immediate(engine)
    return engine


def _install_begin_immediate(engine: AsyncEngine) -> None:
    """给 SQLite 引擎挂 `begin` 钩子：事务起点发 `BEGIN IMMEDIATE`。

    Args:
        engine: SQLite 异步引擎。
    """

    @event.listens_for(engine.sync_engine, "begin")
    def _begin_immediate(connection: Any) -> None:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
