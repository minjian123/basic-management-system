"""ops 显式建表入口用例（Kiwi 2304）：批量 / 单库 / dry-run / 空表集跳过 / 失败汇总。"""

import sqlite3
from pathlib import Path

import pytest

import ops.init_schema as init_schema
from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.config import get_settings


def _prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把平台服务库 / 服务租户库 / 归档库指向临时目录并刷新配置。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}.db")
    monkeypatch.setenv(
        "BMS_DATABASE__TENANTS__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}_{{tenant}}.db"
    )
    monkeypatch.setenv("BMS_DATABASE__ARCHIVE__URL", f"sqlite+aiosqlite:///{tmp_path}/archive.db")
    get_settings.cache_clear()
    get_settings().app.service = "platform"


def _table_names(path: Path) -> ConcurrentStableSet[str]:
    """取 SQLite 文件表名集合。

    Args:
        path: 库文件路径。

    Returns:
        ConcurrentStableSet[str]: 表名集合。
    """
    connection = sqlite3.connect(path)
    try:
        return ConcurrentStableSet(
            row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        )
    finally:
        connection.close()


@pytest.mark.kiwi_id(2304)
def test_init_schema_dry_run_lists_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--dry-run`：输出「服务 × 数据源 × 库」清单与库数量统计，不建连、不建文件。"""
    _prepare(tmp_path, monkeypatch)
    args = ["--service", "platform", "--code", "demo", "--code", "acme", "--dry-run"]
    assert init_schema.main(ConcurrentStableList(args)) == 0
    out = capsys.readouterr().out
    for label in ("platform:platform", "platform_platform", "tenant_platform_demo", "archive", "库数量", "dry-run"):
        assert label in out
    assert not (tmp_path / "bms_platform_demo.db").exists()


@pytest.mark.kiwi_id(2304)
def test_init_schema_batch_builds_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """批量建表：逐库输出「新建 N / 已存在 M」；重复执行全部「已存在」且退出 0。"""
    _prepare(tmp_path, monkeypatch)
    args = ["--service", "platform", "--target", "tenants", "--code", "demo", "--code", "acme"]
    assert init_schema.main(ConcurrentStableList(args)) == 0
    out = capsys.readouterr().out
    assert "新建" in out and "汇总：成功 2、跳过 0、失败 0" in out
    demo_tables = _table_names(tmp_path / "bms_platform_demo.db")
    assert {"sys_data_scope", "sys_query_scheme", "sys_outbox"} <= demo_tables
    assert {"sys_data_scope"} <= _table_names(tmp_path / "bms_platform_acme.db")

    assert init_schema.main(ConcurrentStableList(args)) == 0
    again = capsys.readouterr().out
    assert "新建 0" in again and "汇总：成功 2、跳过 0、失败 0" in again
    assert _table_names(tmp_path / "bms_platform_demo.db") == demo_tables, "重复执行不新建表"


@pytest.mark.kiwi_id(2304)
def test_init_schema_single_db_form(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """单库形态：`--target platform --url` 对指定库幂等建表。"""
    _prepare(tmp_path, monkeypatch)
    url = f"sqlite+aiosqlite:///{tmp_path / 'drill_platform.db'}"
    args = ["--service", "platform", "--target", "platform", "--url", url]
    assert init_schema.main(ConcurrentStableList(args)) == 0
    assert "汇总：成功 1、跳过 0、失败 0" in capsys.readouterr().out
    assert {"sys_module", "sys_table_ownership"} <= _table_names(tmp_path / "drill_platform.db")


@pytest.mark.kiwi_id(2304)
def test_init_schema_skips_empty_table_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """空表集（归档链）→ 跳过，不计成功、不建库。"""
    _prepare(tmp_path, monkeypatch)
    assert init_schema.main(ConcurrentStableList(["--target", "archive"])) == 0
    out = capsys.readouterr().out
    assert "无表集（跳过）" in out and "汇总：成功 0、跳过 1、失败 0" in out
    assert not (tmp_path / "archive.db").exists()


@pytest.mark.kiwi_id(2304)
def test_init_schema_collects_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """缺库 / 不可达：失败不中断整批，末尾汇总并使退出码为 1。"""
    _prepare(tmp_path, monkeypatch)
    broken = "sqlite+aiosqlite:////nonexistent_dir_for_drill/bms_migrcheck.db"
    args = ["--service", "platform", "--target", "tenant", "--url", broken]
    assert init_schema.main(ConcurrentStableList(args)) == 1
    out = capsys.readouterr().out
    assert "失败" in out and "汇总：成功 0、跳过 0、失败 1" in out
