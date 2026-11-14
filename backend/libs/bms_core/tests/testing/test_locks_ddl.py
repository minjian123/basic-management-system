"""测试基座：跨进程文件锁与 DDL 串行化（04-6-2）。

这两块是单库叠加的并发设施，本身就是被测对象：

- `file_lock`：`O_CREAT|O_EXCL` 原子建锁文件，持有期间他人必须等待；超时要报错而不是静默并行；
  持锁方退出时若锁文件已被他人清掉，不得因此报错。
- `serialize_ddl`：把 `MetaData.create_all` 挂上同库互斥，避免两个 worker 同时首次建表撞
  `already exists`；内存库 / 非 SQLite 不取锁（它们不共享文件，串行只会拖慢）。

**分支用替身验、真实建表用共享库验**：加锁 / 放行两条分支只跟 bind 的库路径有关，把
`_ORIGINAL_CREATE_ALL` 换成替身即可判断「这次建表有没有在锁内」，不必真的建两个库
（真建库会被 G1「测试自建 SQLite」护栏拦下，也没必要）；「安装后真实建表仍可用」则由共享平台库
上的幂等 `create_all` 覆盖（表已在即跳过，不写数据）。

`_sqlite_database` / `_locked_create_all` 是模块私有的判定核心，用例直接调用并标注私有访问豁免。
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import MetaData, Table
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.config.models import SysConfig
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing import ddl
from bms_core.testing import locks as locks_module
from bms_core.testing.locks import file_lock
from bms_core.testing.paths import project_root

_TABLES: ConcurrentStableList[Table] = ConcurrentStableList((cast("Table", SysConfig.__table__),))
"""真实建表用例用的表（系统参数：单表、无外键依赖）。"""


def _lock_path(name: str) -> Any:
    """锁文件路径（与 `file_lock` 实现同口径）。

    Args:
        name: 锁名。

    Returns:
        Any: 锁文件路径对象。
    """
    return project_root() / ".cache" / "test" / f"{name}.lock"


def _raise_process_lookup_error(pid: int, sig: int) -> None:
    """替身 `os.kill`：持锁进程不存在。

    Args:
        pid: 进程号。
        sig: 信号号。

    Raises:
        ProcessLookupError: 恒抛（模拟进程已死）。
    """
    raise ProcessLookupError(pid, sig)


def _raise_permission_error(pid: int, sig: int) -> None:
    """替身 `os.kill`：进程存在但无权限探测（按存活处理）。

    Args:
        pid: 进程号。
        sig: 信号号。

    Raises:
        PermissionError: 恒抛（模拟权限不足）。
    """
    raise PermissionError(pid, sig)


def _noop_kill(pid: int, sig: int) -> None:
    """替身 `os.kill`：进程存在且可探测（成功路径）。

    Args:
        pid: 进程号。
        sig: 信号号。
    """


def _ddl_lock_path(database: str) -> Any:
    """按库路径推出 DDL 锁文件路径（与 `ddl._locked_create_all` 的锁名同口径）。

    Args:
        database: SQLite 库文件路径。

    Returns:
        Any: 锁文件路径对象。
    """
    digest = hashlib.sha1(database.encode("utf-8")).hexdigest()[:12]
    return _lock_path(f"ddl-{digest}")


@pytest.mark.kiwi_id(2317)
def test_file_lock_excludes_then_releases() -> None:
    """持锁期间锁文件在册，退出后清掉（他人可取）。"""
    path = _lock_path("ddl-test-exclusive")
    with file_lock("ddl-test-exclusive", timeout=5):
        assert path.is_file()
    assert not path.exists()


@pytest.mark.kiwi_id(2317)
def test_file_lock_times_out_when_held() -> None:
    """他人持锁且超过等待上限 → `TimeoutError`（不静默并行）。"""
    name = "ddl-test-timeout"
    path = _lock_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("other", encoding="utf-8")
    try:
        with pytest.raises(TimeoutError, match="等待测试锁超时"), file_lock(name, timeout=0.05):
            pass
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.kiwi_id(2317)
def test_file_lock_tolerates_lock_file_removed_by_other() -> None:
    """持锁方退出时锁文件已不在 → 不报错（清理路径容错）。"""
    name = "ddl-test-removed"
    with file_lock(name, timeout=5):
        _lock_path(name).unlink(missing_ok=True)
    assert not _lock_path(name).exists()


@pytest.mark.kiwi_id(2317)
def test_file_lock_reclaims_dead_holder(monkeypatch: pytest.MonkeyPatch) -> None:
    """持锁进程已死 → 判为陈旧并清理重取（xdist 杀 worker / 进程崩溃的残锁不再阻塞）。"""
    name = "ddl-test-dead-holder"
    path = _lock_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("999999|0", encoding="utf-8")
    monkeypatch.setattr(locks_module, "_POSIX", True)
    monkeypatch.setattr(locks_module.os, "kill", _raise_process_lookup_error)
    try:
        with file_lock(name, timeout=1):
            assert path.is_file()
        assert not path.exists()
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.kiwi_id(2317)
def test_file_lock_reclaims_aged_lock() -> None:
    """未知持有者但锁文件已超陈旧阈值 → 清理重取（Windows 等无进程探测时兜底）。"""
    name = "ddl-test-aged"
    path = _lock_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("other", encoding="utf-8")
    aged = time.time() - locks_module.STALE_AFTER - 5
    os.utime(path, (aged, aged))
    try:
        with file_lock(name, timeout=1):
            assert path.is_file()
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.kiwi_id(2317)
def test_lock_helpers_cover_holder_parsing_and_liveness(monkeypatch: pytest.MonkeyPatch) -> None:
    """持有者解析 / 存活探测 / 陈旧判定：非法内容不判陈旧、自身 pid 不判陈旧、权限错误按存活。"""
    assert locks_module._holder_pid("123|456") == 123  # pyright: ignore[reportPrivateUsage]
    assert locks_module._holder_pid("other") is None  # pyright: ignore[reportPrivateUsage]

    pid = os.getpid()
    # `_POSIX` 真值 + 替身成功路径：覆盖「探测到存活」分支（Windows 上真调 `os.kill(pid, 0)`
    # 会走 TerminateProcess，不能真调）
    monkeypatch.setattr(locks_module, "_POSIX", True)
    monkeypatch.setattr(locks_module.os, "kill", _noop_kill)
    assert locks_module._pid_alive(pid)  # pyright: ignore[reportPrivateUsage]
    path = _lock_path("ddl-test-helpers")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{pid}|{time.time():.0f}", encoding="utf-8")
    try:
        # 自身 pid（同进程重入）不算陈旧；锁文件不存在也不算陈旧
        assert not locks_module._is_stale(path)  # pyright: ignore[reportPrivateUsage]
        assert not locks_module._is_stale(path.with_name("ddl-test-missing"))  # pyright: ignore[reportPrivateUsage]
    finally:
        path.unlink(missing_ok=True)

    monkeypatch.setattr(locks_module, "_POSIX", True)
    monkeypatch.setattr(locks_module.os, "kill", _raise_permission_error)
    assert locks_module._pid_alive(999999)  # pyright: ignore[reportPrivateUsage]

    # 非 POSIX 平台：不做进程探测，按存活处理（交给时长判据）
    monkeypatch.setattr(locks_module, "_POSIX", False)
    assert locks_module._pid_alive(999999)  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2317)
def test_serialize_ddl_is_idempotent() -> None:
    """重复安装只挂一次（第二次直接返回）。"""
    ddl.serialize_ddl()
    installed = ddl.MetaData.create_all
    ddl.serialize_ddl()
    assert ddl.MetaData.create_all is installed
    assert installed is ddl._locked_create_all  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2317)
def test_sqlite_database_branches() -> None:
    """库识别：文件库取路径；内存库 / 非 SQLite / 无 URL 一律不取锁。"""
    file_bind = SimpleNamespace(engine=SimpleNamespace(url=URL.create("sqlite+aiosqlite", database="C:/tmp/a.db")))
    assert ddl._sqlite_database(file_bind) == "C:/tmp/a.db"  # pyright: ignore[reportPrivateUsage]

    direct_bind = SimpleNamespace(url=URL.create("sqlite+aiosqlite", database="C:/tmp/b.db"))
    assert ddl._sqlite_database(direct_bind) == "C:/tmp/b.db"  # pyright: ignore[reportPrivateUsage]

    memory_bind = SimpleNamespace(url=URL.create("sqlite+aiosqlite", database=":memory:"))
    assert ddl._sqlite_database(memory_bind) is None  # pyright: ignore[reportPrivateUsage]

    bare_bind = SimpleNamespace(url=URL.create("sqlite+aiosqlite"))
    assert ddl._sqlite_database(bare_bind) is None  # pyright: ignore[reportPrivateUsage]

    pg_bind = SimpleNamespace(
        url=URL.create("postgresql+asyncpg", username="u", password="p", host="h", port=5432, database="db")
    )
    assert ddl._sqlite_database(pg_bind) is None  # pyright: ignore[reportPrivateUsage]

    assert ddl._sqlite_database(object()) is None  # pyright: ignore[reportPrivateUsage]


class _FakeInspector:
    """`inspect(bind).has_table` 替身：按给定既有表集回答，并记录被问到的表名。"""

    def __init__(self, existing: ConcurrentStableList[str]) -> None:
        self.existing = existing
        self.asked: ConcurrentStableList[str] = ConcurrentStableList()

    def has_table(self, name: str) -> bool:
        """表是否已存在。

        Args:
            name: 表名。

        Returns:
            bool: 在既有表集内返回 True。
        """
        self.asked.add(name)
        return name in self.existing


def _make_inspect(inspector: _FakeInspector) -> Callable[[Any], _FakeInspector]:
    """构造 `inspect` 替身（忽略入参，恒返回给定 inspector）。

    Args:
        inspector: 假 inspector。

    Returns:
        Callable[[Any], _FakeInspector]: 入参被忽略的 inspect 替身。
    """

    def _inspect(bind: Any) -> _FakeInspector:
        del bind
        return inspector

    return _inspect


@pytest.mark.kiwi_id(2317)
def test_create_all_skips_existing_table(monkeypatch: pytest.MonkeyPatch) -> None:
    """表已存在（他人已建并提交）：不再发 CREATE。

    这条是并发收口的关键：服务启动的自动建表在锁外算缺失集，锁内必须重判，
    否则第二个 worker 仍按旧清单发 `CREATE` 撞 `already exists`。
    """
    database = "C:/tmp/ddl-skip-probe.db"
    built: ConcurrentStableList[str] = ConcurrentStableList()

    def _fake_create_all(self: MetaData, bind: Any, tables: Any = None, checkfirst: bool = True) -> None:
        del self, bind, checkfirst
        for table in tables or ():
            built.add(str(table.name))

    inspector = _FakeInspector(ConcurrentStableList((SysConfig.__tablename__,)))
    monkeypatch.setattr(ddl, "inspect", _make_inspect(inspector))
    monkeypatch.setattr(ddl, "_ORIGINAL_CREATE_ALL", _fake_create_all)
    bind = SimpleNamespace(engine=SimpleNamespace(url=URL.create("sqlite+aiosqlite", database=database)))
    ddl._locked_create_all(SysConfig.metadata, bind, tables=_TABLES)  # pyright: ignore[reportPrivateUsage]
    assert list(built) == [], "已存在的表不该再建"
    assert list(inspector.asked) == [SysConfig.__tablename__]


@pytest.mark.kiwi_id(2317)
def test_create_all_builds_missing_table_under_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    """表不存在：在**持锁**状态下建表，退出后释放。"""
    database = "C:/tmp/ddl-build-probe.db"
    held: ConcurrentStableList[bool] = ConcurrentStableList()

    def _fake_create_all(self: MetaData, bind: Any, tables: Any = None, checkfirst: bool = True) -> None:
        del self, bind, tables, checkfirst
        held.add(_ddl_lock_path(database).is_file())

    monkeypatch.setattr(ddl, "inspect", _make_inspect(_FakeInspector(ConcurrentStableList())))
    monkeypatch.setattr(ddl, "_ORIGINAL_CREATE_ALL", _fake_create_all)
    bind = SimpleNamespace(engine=SimpleNamespace(url=URL.create("sqlite+aiosqlite", database=database)))
    ddl._locked_create_all(SysConfig.metadata, bind, tables=_TABLES)  # pyright: ignore[reportPrivateUsage]
    assert list(held) == [True], "建表必须发生在锁内"
    assert not _ddl_lock_path(database).exists(), "退出后必须释放"


@pytest.mark.kiwi_id(2317)
def test_create_all_tolerates_concurrent_already_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    """并发下另一方抢先建好：吞掉 `already exists`（等价于成功），不炸整个建表流程。"""
    database = "C:/tmp/ddl-exists-probe.db"

    def _boom(self: MetaData, bind: Any, tables: Any = None, checkfirst: bool = True) -> None:
        del self, bind, tables, checkfirst
        raise OperationalError(
            "CREATE TABLE sys_config (...)",
            {},
            sqlite3.OperationalError("table sys_config already exists"),
        )

    monkeypatch.setattr(ddl, "inspect", _make_inspect(_FakeInspector(ConcurrentStableList())))
    monkeypatch.setattr(ddl, "_ORIGINAL_CREATE_ALL", _boom)
    bind = SimpleNamespace(engine=SimpleNamespace(url=URL.create("sqlite+aiosqlite", database=database)))
    ddl._locked_create_all(SysConfig.metadata, bind, tables=_TABLES)  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2317)
def test_create_all_propagates_other_operational_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """其它 `OperationalError`（如 database is locked）必须照抛，不掩盖真问题。"""
    database = "C:/tmp/ddl-locked-probe.db"

    def _boom(self: MetaData, bind: Any, tables: Any = None, checkfirst: bool = True) -> None:
        del self, bind, tables, checkfirst
        raise OperationalError("CREATE TABLE sys_config (...)", {}, sqlite3.OperationalError("database is locked"))

    monkeypatch.setattr(ddl, "inspect", _make_inspect(_FakeInspector(ConcurrentStableList())))
    monkeypatch.setattr(ddl, "_ORIGINAL_CREATE_ALL", _boom)
    bind = SimpleNamespace(engine=SimpleNamespace(url=URL.create("sqlite+aiosqlite", database=database)))
    with pytest.raises(OperationalError):
        ddl._locked_create_all(SysConfig.metadata, bind, tables=_TABLES)  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2317)
def test_create_all_passes_through_for_memory_library(monkeypatch: pytest.MonkeyPatch) -> None:
    """内存库：不占锁直接调用（共享文件才需要串行）。"""
    seen: ConcurrentStableList[bool] = ConcurrentStableList()

    def _fake_create_all(self: MetaData, bind: Any, tables: Any = None, checkfirst: bool = True) -> None:
        del self, bind, tables, checkfirst
        seen.add(True)

    monkeypatch.setattr(ddl, "_ORIGINAL_CREATE_ALL", _fake_create_all)
    bind = SimpleNamespace(url=URL.create("sqlite+aiosqlite", database=":memory:"))
    ddl._locked_create_all(MetaData(), bind, tables=_TABLES)  # pyright: ignore[reportPrivateUsage]
    assert list(seen) == [True]


@pytest.mark.kiwi_id(2317)
async def test_create_all_works_on_shared_library(shared_platform_engine: AsyncEngine) -> None:
    """安装后真实建表仍可用（共享平台库上幂等：表已在即跳过，不写数据）。"""
    ddl.serialize_ddl()
    async with shared_platform_engine.begin() as connection:
        await connection.run_sync(lambda conn: SysConfig.metadata.create_all(conn, tables=_TABLES))
        exists = await connection.run_sync(lambda conn: conn.dialect.has_table(conn, SysConfig.__tablename__))
    assert exists is True


@pytest.mark.kiwi_id(2317)
def test_lock_module_exposes_timeout_default() -> None:
    """默认等锁上限对外可见（用例侧按需覆盖）。"""
    assert locks_module.DEFAULT_TIMEOUT > 0
