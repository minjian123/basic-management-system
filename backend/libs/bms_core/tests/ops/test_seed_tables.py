"""表归属登记种子脚本测试（Kiwi 1078）：幂等 upsert、字段更新与 dry-run。"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

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


@pytest.mark.kiwi_id(2178)
async def test_seed_tables_idempotent(tmp_path: Path) -> None:
    """种子：首跑全新增、重跑全跳过（0 / 0），行数与清单一致。"""
    url = _url(tmp_path)
    created, updated = await seed_tables(url)
    assert created == len(TABLE_OWNERSHIP)
    assert updated == 0
    assert _count(tmp_path) == len(TABLE_OWNERSHIP)

    assert await seed_tables(url) == (0, 0)


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

    created, updated = await seed_tables(url)
    assert (created, updated) == (0, 1)
    assert await seed_tables(url) == (0, 0)


@pytest.mark.kiwi_id(2178)
def test_seed_tables_cli_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`--dry-run` 只打印目标库与种子清单，不建库。"""
    from ops.seed_tables import main

    url = _url(tmp_path)
    assert main(["--url", url, "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "dry-run" in out and "sys_table_ownership" in out
    assert not (tmp_path / "bms_platform.db").exists()
