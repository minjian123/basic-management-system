"""表归属登记种子脚本测试（Kiwi 1078）：幂等 upsert、字段更新、退役行清退与 dry-run。"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.ownership import SysTableOwnership
from bms_core.services.table_registry import TABLE_OWNERSHIP
from ops.seed_tables import seed_tables


def _url(tmp_path: Path) -> str:
    """临时平台服务库连接串。

    Args:
        tmp_path: 临时目录。

    Returns:
        str: 异步连接串。
    """
    return f"sqlite+aiosqlite:///{tmp_path / 'bms_platform.db'}"


def _sync_url(tmp_path: Path) -> str:
    """临时库同步连接串。

    Args:
        tmp_path: 临时目录。

    Returns:
        str: 同步连接串。
    """
    return f"sqlite:///{tmp_path / 'bms_platform.db'}"


def _count(tmp_path: Path) -> int:
    """统计登记行数。

    Args:
        tmp_path: 临时目录。

    Returns:
        int: 未软删行数。
    """
    engine = create_engine(_sync_url(tmp_path))
    try:
        with engine.connect() as connection:
            return int(connection.execute(text("SELECT COUNT(*) FROM sys_table_ownership")).scalar_one())
    finally:
        engine.dispose()


def _count_active(tmp_path: Path) -> int:
    """统计未软删登记行数。

    Args:
        tmp_path: 临时目录。

    Returns:
        int: 未软删行数。
    """
    engine = create_engine(_sync_url(tmp_path))
    try:
        with engine.connect() as connection:
            return int(
                connection.execute(
                    text("SELECT COUNT(*) FROM sys_table_ownership WHERE deleted_at IS NULL")
                ).scalar_one()
            )
    finally:
        engine.dispose()


def _insert_stale(tmp_path: Path, table_name: str = "sys_dict_item") -> None:
    """直插一行「不在清单」的登记行（模拟退役表残留登记）。

    Args:
        tmp_path: 临时目录。
        table_name: 退役表名。
    """
    engine = create_engine(_sync_url(tmp_path))
    try:
        with Session(engine) as session:
            session.add(SysTableOwnership(table_name=table_name, owner="platform"))
            session.commit()
    finally:
        engine.dispose()


def _stale_deleted_at(tmp_path: Path, table_name: str = "sys_dict_item") -> object:
    """读退役行的软删除时间（未清退为 None）。

    Args:
        tmp_path: 临时目录。
        table_name: 退役表名。

    Returns:
        object: `deleted_at` 值。
    """
    engine = create_engine(_sync_url(tmp_path))
    try:
        with engine.connect() as connection:
            return connection.execute(
                text("SELECT deleted_at FROM sys_table_ownership WHERE table_name = :name"),
                {"name": table_name},
            ).scalar_one()
    finally:
        engine.dispose()


def _force_sync(_url: str) -> bool:
    """判定「同步专用方言」的替身（测试用：固定为真，走同步分支）。

    Args:
        _url: 连接串（忽略）。

    Returns:
        bool: 恒为 True。
    """
    return True


@pytest.mark.kiwi_id(2178)
async def test_seed_tables_idempotent(tmp_path: Path) -> None:
    """种子：首跑全新增、重跑全跳过（0 / 0），行数与清单一致。"""
    url = _url(tmp_path)
    created, updated, retired = await seed_tables(url)
    assert created == len(TABLE_OWNERSHIP)
    assert (updated, retired) == (0, 0)
    assert _count(tmp_path) == len(TABLE_OWNERSHIP)

    assert await seed_tables(url) == (0, 0, 0)


@pytest.mark.kiwi_id(2178)
async def test_seed_tables_updates_changed_field(tmp_path: Path) -> None:
    """库中字段与清单不一致时按清单回写（幂等 upsert 的更新分支）。"""
    url = _url(tmp_path)
    await seed_tables(url)
    engine = create_engine(_sync_url(tmp_path))
    try:
        with engine.begin() as connection:
            connection.execute(text("UPDATE sys_table_ownership SET owner = 'ghost' WHERE table_name = 'sys_outbox'"))
    finally:
        engine.dispose()

    created, updated, retired = await seed_tables(url)
    assert (created, updated, retired) == (0, 1, 0)
    assert await seed_tables(url) == (0, 0, 0)


@pytest.mark.kiwi_id(2178)
async def test_seed_tables_retires_absent_rows(tmp_path: Path) -> None:
    """不在清单的登记行被清退（软删除）；重跑 0 / 0 / 0，未软删行数与清单一致。"""
    url = _url(tmp_path)
    await seed_tables(url)
    _insert_stale(tmp_path)
    assert (_count(tmp_path), _count_active(tmp_path)) == (len(TABLE_OWNERSHIP) + 1, len(TABLE_OWNERSHIP) + 1)
    assert _stale_deleted_at(tmp_path) is None

    created, updated, retired = await seed_tables(url)
    assert (created, updated, retired) == (0, 0, 1)
    assert _count_active(tmp_path) == len(TABLE_OWNERSHIP)
    assert _stale_deleted_at(tmp_path) is not None
    assert _count(tmp_path) == len(TABLE_OWNERSHIP) + 1
    assert await seed_tables(url) == (0, 0, 0)


@pytest.mark.kiwi_id(2178)
async def test_seed_tables_retires_absent_rows_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """同步方言分支（达梦）同样清退不在清单的登记行。"""
    from ops import seed_tables as module

    monkeypatch.setattr(module, "is_sync_only_url", _force_sync)
    url = _sync_url(tmp_path)
    assert await seed_tables(url) == (len(TABLE_OWNERSHIP), 0, 0)
    _insert_stale(tmp_path)

    assert await seed_tables(url) == (0, 0, 1)
    assert _count_active(tmp_path) == len(TABLE_OWNERSHIP)
    assert await seed_tables(url) == (0, 0, 0)


@pytest.mark.kiwi_id(2178)
def test_seed_tables_cli_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`--dry-run` 只打印目标库与种子清单，不建库。"""
    from ops.seed_tables import main

    url = _url(tmp_path)
    assert main(ConcurrentStableList(["--url", url, "--dry-run"])) == 0
    out = capsys.readouterr().out
    assert "dry-run" in out and "sys_table_ownership" in out
    assert not (tmp_path / "bms_platform.db").exists()
