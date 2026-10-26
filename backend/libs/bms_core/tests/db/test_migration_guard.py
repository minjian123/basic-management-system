"""迁移执行期校验反例（Kiwi 2354）：六项校验各拦一类「写错 / 撞上」，且不误伤合法清单。

口径见 07C `03_02` 详细设计 §3.8：静态可判的 1/2/3/5/6 项与库级互斥（第 7 项）都要有反例；
本用例直接构造清单定义与临时版本目录，不连库、不跑 Alembic。
"""

# pyright: reportUnusedFunction=false
from pathlib import Path
from types import SimpleNamespace

import pytest

import bms_core.db.migration as migration
from bms_core.core.concurrent import ConcurrentStableFrozenSet, ConcurrentStableList
from bms_core.db import migration_guard as guard
from bms_core.db.migration import MigrationSeries


def _series(domain: str, *tables: str, datasource: str = "tenant") -> MigrationSeries:
    """构造清单定义（表集与版本目录由参数决定）。

    Args:
        domain: 域标识（同时是版本目录一级名）。
        tables: 表名（变参）。
        datasource: 数据源段。

    Returns:
        MigrationSeries: 清单定义。
    """
    return MigrationSeries(
        name=f"{domain}:{datasource}",
        domain=domain,
        datasource=datasource,
        tables=ConcurrentStableFrozenSet(tables),
        scope=f"{domain} 域的库",
    )


def _script(tmp_path: Path, domain: str, name: str, body: str, datasource: str = "tenant") -> None:
    """在临时版本目录写一个迁移脚本。

    Args:
        tmp_path: 临时根（充当 `versions/`）。
        domain: 域标识。
        name: 脚本文件名。
        body: 脚本正文（`upgrade()` 内语句）。
        datasource: 数据源段。
    """
    location = tmp_path / domain / datasource
    location.mkdir(parents=True, exist_ok=True)
    (location / name).write_text(
        f'revision = "0001_x"\n\n\ndef upgrade() -> None:\n    {body}\n',
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def _versions_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把清单版本根指向临时目录（`version_location` 由此派生）。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。

    Returns:
        Path: 临时版本根。
    """
    monkeypatch.setattr(migration, "VERSIONS_ROOT", tmp_path)
    return tmp_path


@pytest.mark.kiwi_id(2354)
def test_script_tables_and_revisions(_versions_root: Path) -> None:
    """脚本解析：建表 / 加列 / 批量改表的表名与 revision 字面均被提取。"""
    _script(_versions_root, "demo", "0001_x.py", 'op.create_table("demo_a")')
    item = _series("demo", "demo_a")

    assert guard.script_tables(item) == ConcurrentStableFrozenSet({"demo_a"})
    assert "0001_x" in guard.script_revisions(item)


@pytest.mark.kiwi_id(2354)
def test_check_script_ownership_blocks_cross_domain(_versions_root: Path) -> None:
    """校验 1：脚本操作了不属于该域的表 → 拦截；归属正确 → 放行。"""
    _script(_versions_root, "demo", "0001_x.py", 'op.create_table("other_b")')

    assert guard.check_script_ownership(_series("demo", "demo_a"))
    assert not guard.check_script_ownership(_series("demo", "other_b"))


@pytest.mark.kiwi_id(2354)
def test_check_series_disjoint(_versions_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """校验 2：同库两条清单表集相交 → 拦截；表集互斥 → 放行。"""
    left = _series("demo", "demo_a")
    right = _series("other", "demo_a")

    def _overlap(unit: str, datasource: str) -> ConcurrentStableList[MigrationSeries]:
        """替身：返回表集相交的两条清单。"""
        del unit, datasource
        return ConcurrentStableList([left, right])

    monkeypatch.setattr(guard, "unit_series", _overlap)
    assert guard.check_series_disjoint("platform", "tenant")

    def _disjoint(unit: str, datasource: str) -> ConcurrentStableList[MigrationSeries]:
        """替身：返回表集互斥的两条清单。"""
        del unit, datasource
        return ConcurrentStableList([left, _series("other", "other_b")])

    monkeypatch.setattr(guard, "unit_series", _disjoint)
    assert guard.check_series_disjoint("platform", "tenant") == []


@pytest.mark.kiwi_id(2354)
def test_check_version_known_and_monotonic(_versions_root: Path) -> None:
    """校验 3 / 5：未知 revision 与不在清单内的当前版本（多 head / 跨库污染）均被拦截。"""
    _script(_versions_root, "demo", "0001_x.py", 'op.create_table("demo_a")')
    item = _series("demo", "demo_a")

    assert guard.check_version_known(item, None) == []
    assert guard.check_version_known(item, "0001_x") == []
    assert guard.check_version_known(item, "9999_unknown")

    assert guard.check_monotonic(item, "0001_x", "0001_x") == []
    assert guard.check_monotonic(item, "9999_unknown", "0001_x")
    assert guard.check_monotonic(item, None, None) == []


@pytest.mark.kiwi_id(2354)
def test_check_destructive_requires_explicit_allow(_versions_root: Path) -> None:
    """校验 6：`drop table` / `drop column` 默认拒绝，显式放行后通过。"""
    _script(
        _versions_root,
        "demo",
        "0001_x.py",
        'op.create_table("demo_a")\n    op.drop_table("demo_old")\n    op.drop_column("demo_a", "legacy")',
    )
    item = _series("demo", "demo_a", "demo_old")

    assert guard.check_destructive(item, allow_destructive=False)
    assert guard.check_destructive(item, allow_destructive=True) == []


@pytest.mark.kiwi_id(2354)
def test_guard_preflight_combines_checks(_versions_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """预检汇总：越域脚本 + 破坏性操作同时命中时，问题清单一次列全。"""
    _script(_versions_root, "demo", "0001_x.py", 'op.create_table("other_b")\n    op.drop_table("demo_old")')
    item = _series("demo", "demo_a")

    def _single(unit: str, datasource: str) -> ConcurrentStableList[MigrationSeries]:
        """替身：该库只有一条清单。"""
        del unit, datasource
        return ConcurrentStableList([item])

    monkeypatch.setattr(guard, "unit_series", _single)

    problems = guard.MigrationGuard("platform", "tenant").preflight()

    assert len(problems) >= 2


@pytest.mark.kiwi_id(2354)
def test_library_lock_passes_on_dialect_without_advisory_lock(tmp_path: Path) -> None:
    """校验 7：无咨询锁方言（SQLite）直接放行（按部署串行，不阻塞）。"""
    with guard.library_lock(f"sqlite:///{tmp_path / 'lock.db'}") as acquired:
        assert acquired


@pytest.mark.kiwi_id(2359)
def test_script_scans_return_empty_without_version_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """版本目录不存在：脚本表名 / revision / 破坏性操作三个扫描入口均返空、不抛错。"""
    monkeypatch.setattr(migration, "VERSIONS_ROOT", tmp_path / "absent")
    series = _series("demo", "demo_a")

    assert series.version_location.is_dir() is False
    assert guard.script_tables(series) == set()
    assert guard.script_revisions(series) == set()
    assert guard.destructive_statements(series) == []
    assert guard.versions_dir(series) == series.version_location


class _LockConnection:
    """库级锁连接替身（记录 SQL；`scalar()` 按构造返回是否拿到锁）。"""

    def __init__(self, *, locked: bool) -> None:
        """初始化。

        Args:
            locked: `scalar()` 的返回值（是否拿到锁）。
        """
        self.statements = ConcurrentStableList[str]()
        self._locked = locked

    def execute(self, statement: object, parameters: object) -> object:
        """记录 SQL 并返回带 `scalar()` 的结果替身。

        Args:
            statement: SQL 语句对象（`text(...)`）。
            parameters: 绑定参数。

        Returns:
            object: 结果替身（`scalar()` 返回锁状态）。
        """
        del parameters
        self.statements.add(str(statement))
        return SimpleNamespace(scalar=lambda: 1 if self._locked else 0)

    def __enter__(self) -> _LockConnection:
        """进入上下文（模拟 `engine.connect()`）。

        Returns:
            _LockConnection: 自身。
        """
        return self

    def __exit__(self, *args: object) -> bool:
        """退出上下文（不抑制异常）。

        Args:
            *args: 异常三元组。

        Returns:
            bool: 恒 False。
        """
        del args
        return False


class _LockEngine:
    """引擎替身（返回固定连接；记录是否释放）。"""

    def __init__(self, connection: _LockConnection) -> None:
        """初始化。

        Args:
            connection: 连接替身。
        """
        self.connection = connection
        self.disposed = False

    def connect(self) -> _LockConnection:
        """取连接（模拟 `engine.connect()`）。

        Returns:
            _LockConnection: 连接替身。
        """
        return self.connection

    def dispose(self) -> None:
        """标记已释放。"""
        self.disposed = True


def _run_library_lock(monkeypatch: pytest.MonkeyPatch, url: str, *, locked: bool) -> ConcurrentStableList[str]:
    """以替身引擎跑一次库级锁，返回执行的 SQL 序列。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
        url: 连接串（决定方言与锁语句）。
        locked: 是否拿到锁。

    Returns:
        ConcurrentStableList[str]: 执行的 SQL 序列。
    """
    connection = _LockConnection(locked=locked)
    engine = _LockEngine(connection)

    def _engine(*args: object, **kwargs: object) -> _LockEngine:
        """替身：无论连接串与参数一律返回固定引擎。"""
        del args, kwargs
        return engine

    monkeypatch.setattr(guard, "create_engine", _engine)
    with guard.library_lock(url) as acquired:
        assert acquired is locked
    assert engine.disposed is True
    return connection.statements


@pytest.mark.kiwi_id(2359)
def test_library_lock_postgres_try_lock_and_unlock(monkeypatch: pytest.MonkeyPatch) -> None:
    """PostgreSQL：拿到咨询锁后成对解锁；未拿到则只尝试、不解锁（不排队等待）。"""
    locked = _run_library_lock(monkeypatch, "postgresql+asyncpg://u:p@h:5432/db", locked=True)
    assert len(locked) == 2
    assert locked[0].startswith("SELECT pg_try_advisory_lock")
    assert locked[1].startswith("SELECT pg_advisory_unlock")

    unlocked = _run_library_lock(monkeypatch, "postgresql+asyncpg://u:p@h:5432/db", locked=False)
    assert len(unlocked) == 1
    assert unlocked[0].startswith("SELECT pg_try_advisory_lock")


@pytest.mark.kiwi_id(2359)
def test_library_lock_mysql_named_lock_and_release(monkeypatch: pytest.MonkeyPatch) -> None:
    """MySQL：命名锁成对获取 / 释放；未拿到则只尝试、不释放。"""
    locked = _run_library_lock(monkeypatch, "mysql+aiomysql://u:p@h:3306/db", locked=True)
    assert len(locked) == 2
    assert locked[0].startswith("SELECT GET_LOCK")
    assert locked[1].startswith("SELECT RELEASE_LOCK")

    unlocked = _run_library_lock(monkeypatch, "mysql+aiomysql://u:p@h:3306/db", locked=False)
    assert len(unlocked) == 1
    assert unlocked[0].startswith("SELECT GET_LOCK")
