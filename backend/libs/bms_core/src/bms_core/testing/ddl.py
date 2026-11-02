"""测试期 DDL 串行化（04-6-2）：并发 worker 首次建同一张表不再撞 `table ... already exists`。

问题：`MetaData.create_all(checkfirst=True)` 的存在性判断查的是已提交的库目录，**看不到**他人尚未
提交的建表事务。单库叠加后多 worker 共用一份 SQLite，两个 worker 同时首次建同一张表时，双方
`has_table` 都为假 → 都发 `CREATE TABLE` → 后提交的一方收到 `table ... already exists`。

为什么不在各用例里改：用例侧 `create_all` 有 80+ 处（fixture 补表、临时库建表、种子准备），
逐处换实现既改不完也易漏；DDL 本身就该串行，统一在 `MetaData.create_all` 上挂钩最稳。

为什么锁名按库区分：各用例的临时库（`tmp_path`）互不相关，串行它们只会拖慢并行；只有**同一个库
文件**上的建表才需要互斥。故按 `database` 路径取摘要做锁名，内存库不取锁。
"""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import MetaData, inspect
from sqlalchemy.exc import OperationalError

from bms_core.testing.locks import file_lock

_ALREADY_EXISTS = "already exists"
"""并发建表的幂等信号（`table ... already exists`）。"""

DDL_LOCK_TIMEOUT = 300.0
"""建表等锁上限（秒）：建表含全表 DDL，比普通写锁给得更宽。"""

_ORIGINAL_CREATE_ALL = MetaData.create_all


def _sqlite_database(bind: Any) -> str | None:
    """取 `create_all` 目标库的 SQLite 文件路径（非 SQLite / 内存库返回 None）。

    Args:
        bind: `create_all` 的绑定对象（`Engine` 或 `Connection`）。

    Returns:
        str | None: 库文件路径；不取锁的情形返回 None。
    """
    url = getattr(getattr(bind, "engine", None), "url", None) or getattr(bind, "url", None)
    if url is None or url.get_backend_name() != "sqlite":
        return None
    database = url.database or ""
    if not database or ":memory:" in database or database == "":
        return None
    return database


def _locked_create_all(
    self: MetaData,
    bind: Any,
    tables: Any = None,
    checkfirst: bool = True,
) -> None:
    """`MetaData.create_all` 的串行化包装（同一库文件上的建表跨进程互斥）。

    Args:
        self: 元数据。
        bind: 连接或引擎。
        tables: 建表集（None 表示全部）。
        checkfirst: 调用方原语义；**在锁内一律按存在性重判**（见下）。
    """
    database = _sqlite_database(bind)
    targets = list(tables) if tables is not None else list(self.sorted_tables)
    if database is None:
        _ORIGINAL_CREATE_ALL(self, bind, tables=tables, checkfirst=checkfirst)
        return
    digest = hashlib.sha1(database.encode("utf-8")).hexdigest()[:12]
    with file_lock(f"ddl-{digest}", timeout=DDL_LOCK_TIMEOUT):
        # 为什么不能把 `tables` / `checkfirst` 直接透传：服务启动的自动建表
        # （`bms_core.db.bootstrap`）会**在锁外先算出缺失集**，再以 `checkfirst=False` 建表；
        # 锁只能让两个 worker 排队，第二方手里仍是进锁前算好的清单，照样发 `CREATE` 撞
        # `already exists`。故锁内逐表重判存在性，并对并发下的同名建表做幂等容错。
        inspector = inspect(bind)
        for table in targets:
            if inspector.has_table(table.name):
                continue
            try:
                _ORIGINAL_CREATE_ALL(self, bind, tables=[table], checkfirst=False)
            except OperationalError as exc:
                if _ALREADY_EXISTS not in str(exc.orig):
                    raise


def serialize_ddl() -> None:
    """安装 DDL 串行化（幂等：已装着直接返回）。"""
    if MetaData.create_all is _locked_create_all:
        return
    MetaData.create_all = _locked_create_all  # type: ignore[method-assign]
