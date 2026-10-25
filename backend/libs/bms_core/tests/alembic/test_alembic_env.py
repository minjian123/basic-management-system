"""迁移环境与版本记录表（Kiwi 1079 / 2353）：每清单独立版本表、元数据子集、升级参数透传。

`alembic/env.py` 按清单显式设置 `version_table = alembic_version_{domain}`（07C `03_02`）：
多域同库时各清单各写自己的表，互不覆盖；未迁移（表不存在）视为未执行。
"""

import asyncio
import sqlite3
from pathlib import Path

import pytest

import bms_core.db.migration as migration
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableSet
from bms_core.db.migration import (
    DATASOURCE_TENANT,
    current_revision,
    resolve_series,
    series_metadata,
    upgrade_series,
)


def _make_db(path: Path, *tables: str) -> None:
    """建一个空 SQLite 库并可选建若干版本记录表。

    Args:
        path: 库文件路径。
        tables: 要创建的版本记录表名。
    """
    connection = sqlite3.connect(path)
    try:
        for table in tables:
            connection.execute(f"CREATE TABLE {table} (version_num VARCHAR(32) NOT NULL)")
        connection.commit()
    finally:
        connection.close()


def _write_version(path: Path, table: str, value: str) -> None:
    """向指定版本记录表写入一行版本号。

    Args:
        path: 库文件路径。
        table: 版本记录表名。
        value: 版本号。
    """
    connection = sqlite3.connect(path)
    try:
        connection.execute(f"INSERT INTO {table} (version_num) VALUES (?)", (value,))
        connection.commit()
    finally:
        connection.close()


@pytest.mark.kiwi_id(1079)
def test_current_revision_per_version_table(tmp_path: Path) -> None:
    """未迁移返回 None；各清单版本记录表**互不覆盖**（多域同库各读各的）。"""
    path = tmp_path / "series.db"
    _make_db(path, "alembic_version_user", "alembic_version_role")
    _write_version(path, "alembic_version_user", "0002_add_col")
    _write_version(path, "alembic_version_role", "0001_init")
    url = f"sqlite+aiosqlite:///{path}"
    assert asyncio.run(current_revision(url, version_table="alembic_version_user")) == "0002_add_col"
    assert asyncio.run(current_revision(url, version_table="alembic_version_role")) == "0001_init"
    assert asyncio.run(current_revision(url, version_table="alembic_version_tenant")) is None


@pytest.mark.kiwi_id(1079)
def test_series_metadata_intersects_models() -> None:
    """清单元数据子集 = 域表集 ∩ 已有模型（未落模型的登记表不参与建表）。"""
    series = resolve_series("user:tenant")
    metadata = series_metadata(series)
    assert ConcurrentStableSet(metadata.tables) <= ConcurrentStableSet(series.tables)
    assert "sys_user" in metadata.tables


@pytest.mark.kiwi_id(2353)
def test_upgrade_series_passes_x_args(monkeypatch: pytest.MonkeyPatch) -> None:
    """升级时连接串与达梦模式经 `-x url=` / `-x schema=` 透传（不写死、不进日志）。"""
    captured: ConcurrentStableDict[str, object] = ConcurrentStableDict()

    def fake_upgrade(config: object, revision: str) -> None:
        captured["revision"] = revision
        captured["x"] = getattr(getattr(config, "cmd_opts", None), "x", None)

    def fake_config(series: object) -> object:
        """替身：配置对象只需可挂 `cmd_opts`。"""
        del series
        return type("C", (), {})()

    monkeypatch.setattr(migration.command, "upgrade", fake_upgrade)
    monkeypatch.setattr(migration, "alembic_config", fake_config)
    upgrade_series(resolve_series("user:tenant"), "dm+dmPython://SYSDBA:p@127.0.0.1:5236", schema="BMS_X")
    assert captured["revision"] == "head"
    assert captured["x"] == ["url=dm+dmPython://SYSDBA:p@127.0.0.1:5236", "schema=BMS_X"]


@pytest.mark.kiwi_id(2353)
def test_has_revisions_and_version_location() -> None:
    """空清单（无脚本）视为无 revision；版本目录按 `{domain}/{datasource}` 两级。"""
    series = resolve_series("user:tenant")
    assert series.datasource == DATASOURCE_TENANT
    assert series.version_location.name == "tenant"
    assert series.version_location.parent.name == "user"
    assert migration.has_revisions(series) is False
