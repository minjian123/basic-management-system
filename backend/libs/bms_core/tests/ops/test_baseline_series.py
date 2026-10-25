"""存量库基线写入（Kiwi 2354）：对账通过只写版本行、有差异即拒绝、无脚本清单跳过、`--dry-run` 不落库。

口径见 07C `03_02` 详细设计 §3.6「存量库切换」：先结构对账（期望表集 vs 库现状），通过后写
`alembic_version_{domain}` 基线行、**不执行 DDL**；任一差异（缺表 / 多表）都不写任何行。
"""

from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine

import ops.baseline_series as baseline
from bms_core.core.concurrent import ConcurrentStableFrozenSet, ConcurrentStableList
from bms_core.db.migration import MigrationSeries


def _metadata(*names: str) -> MetaData:
    """构造含指定表的元数据（替代真实单元表集，聚焦对账与写入逻辑）。

    Args:
        names: 表名。

    Returns:
        MetaData: 元数据。
    """
    metadata = MetaData()
    for name in names:
        Table(name, metadata, Column("id", Integer, primary_key=True))
    return metadata


def _series(domain: str = "demo", *tables: str) -> MigrationSeries:
    """构造清单定义（不经归属登记，避免耦合真实域集）。

    Args:
        domain: 域标识。
        tables: 表名（变参）。

    Returns:
        MigrationSeries: 清单定义。
    """
    return MigrationSeries(
        name=f"{domain}:tenant",
        domain=domain,
        datasource="tenant",
        tables=ConcurrentStableFrozenSet(tables or ("demo_a", "demo_b")),
        scope=f"{domain} 域的服务租户库",
    )


def _prepare_db(path: Path, metadata: MetaData, *extra: str) -> None:
    """按元数据建库（可附加额外表，模拟「多表」差异）。

    Args:
        path: 库文件路径。
        metadata: 期望元数据。
        extra: 额外表名。
    """
    engine = create_engine(f"sqlite:///{path}")
    try:
        metadata.create_all(engine)
        with engine.begin() as connection:
            for name in extra:
                connection.exec_driver_sql(f"CREATE TABLE {name} (id INTEGER PRIMARY KEY)")
    finally:
        engine.dispose()


def _version_rows(path: Path, table: str) -> ConcurrentStableList[str]:
    """读版本记录表（不存在返回空列表）。

    Args:
        path: 库文件路径。
        table: 版本记录表名。

    Returns:
        ConcurrentStableList[str]: 版本行（首列字符串）。
    """
    engine = create_engine(f"sqlite:///{path}")
    try:
        with engine.connect() as connection:
            names = connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'").scalars().all()
            if table not in names:
                return ConcurrentStableList()
            rows = connection.exec_driver_sql(f"SELECT version_num FROM {table}").scalars().all()
            return ConcurrentStableList(str(row) for row in rows)
    finally:
        engine.dispose()


def _patch(monkeypatch: pytest.MonkeyPatch, metadata: MetaData, head: str | None, series: MigrationSeries) -> None:
    """注入期望表集 / 清单序列 / head（不走真实 alembic.ini 与归属登记）。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
        metadata: 期望表集元数据。
        head: head 版本号（None 表示无脚本）。
        series: 清单定义。
    """

    def _metadata_of(unit: str, datasource: str) -> MetaData:
        """替身：期望表集恒为给定元数据。"""
        del unit, datasource
        return metadata

    def _series_of(unit: str, datasource: str) -> ConcurrentStableList[MigrationSeries]:
        """替身：该库只有一条清单。"""
        del unit, datasource
        return ConcurrentStableList([series])

    monkeypatch.setattr(baseline, "unit_metadata", _metadata_of)
    monkeypatch.setattr(baseline, "unit_series", _series_of)

    def _head(item: MigrationSeries) -> str | None:
        """替身 head：恒为给定值。"""
        del item
        return head

    monkeypatch.setattr(baseline, "head_revision", _head)


@pytest.mark.kiwi_id(2354)
async def test_baseline_writes_head_when_reconciled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """对账通过：写 head 基线行、不执行 DDL（表由库现状提供）。"""
    db = tmp_path / "tenant.db"
    metadata = _metadata("demo_a", "demo_b")
    _prepare_db(db, metadata)
    _patch(monkeypatch, metadata, "0001_demo", _series())

    outcome = await baseline.write_baseline("platform", "tenant", f"sqlite+aiosqlite:///{db}")

    assert outcome.ok
    assert outcome.written == ["demo:tenant"]
    assert outcome.skipped == []
    assert _version_rows(db, "alembic_version_demo") == ["0001_demo"]


@pytest.mark.kiwi_id(2354)
async def test_baseline_refuses_on_missing_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """缺表：拒绝写入，且不建版本记录表（不落半改状态）。"""
    db = tmp_path / "tenant.db"
    metadata = _metadata("demo_a", "demo_b")
    _prepare_db(db, _metadata("demo_a"))
    _patch(monkeypatch, metadata, "0001_demo", _series())

    outcome = await baseline.write_baseline("platform", "tenant", f"sqlite+aiosqlite:///{db}")

    assert not outcome.ok
    assert outcome.missing == ["demo_b"]
    assert outcome.written == []
    assert _version_rows(db, "alembic_version_demo") == []


@pytest.mark.kiwi_id(2354)
async def test_baseline_refuses_on_extra_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """多表：拒绝写入并指出多余表（防表归属登记漏项）。"""
    db = tmp_path / "tenant.db"
    metadata = _metadata("demo_a", "demo_b")
    _prepare_db(db, metadata, "stray_table")
    _patch(monkeypatch, metadata, "0001_demo", _series())

    outcome = await baseline.write_baseline("platform", "tenant", f"sqlite+aiosqlite:///{db}")

    assert not outcome.ok
    assert outcome.extra == ["stray_table"]
    assert _version_rows(db, "alembic_version_demo") == []


@pytest.mark.kiwi_id(2354)
async def test_baseline_skips_series_without_scripts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """无脚本清单：跳过且不建版本记录表；空清单不报错。"""
    db = tmp_path / "tenant.db"
    metadata = _metadata("demo_a", "demo_b")
    _prepare_db(db, metadata)
    _patch(monkeypatch, metadata, None, _series())

    outcome = await baseline.write_baseline("platform", "tenant", f"sqlite+aiosqlite:///{db}")

    assert outcome.ok
    assert outcome.skipped == ["demo:tenant"]
    assert outcome.written == []
    assert _version_rows(db, "alembic_version_demo") == []


@pytest.mark.kiwi_id(2354)
async def test_baseline_dry_run_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--dry-run`：只对账，不写任何行。"""
    db = tmp_path / "tenant.db"
    metadata = _metadata("demo_a", "demo_b")
    _prepare_db(db, metadata)
    _patch(monkeypatch, metadata, "0001_demo", _series())

    outcome = await baseline.write_baseline("platform", "tenant", f"sqlite+aiosqlite:///{db}", dry_run=True)

    assert outcome.ok
    assert outcome.dry_run
    assert outcome.written == []
    assert _version_rows(db, "alembic_version_demo") == []


@pytest.mark.kiwi_id(2354)
async def test_baseline_sync_driver_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """同步驱动（SQLite 无异步前缀）：走同步写入分支，幂等重跑结果一致。"""
    db = tmp_path / "tenant.db"
    metadata = _metadata("demo_a", "demo_b")
    _prepare_db(db, metadata)
    _patch(monkeypatch, metadata, "0001_demo", _series())

    url = f"sqlite:///{db}"
    first = await baseline.write_baseline("platform", "tenant", url)
    second = await baseline.write_baseline("platform", "tenant", url)

    assert first.ok and second.ok
    assert _version_rows(db, "alembic_version_demo") == ["0001_demo"]
