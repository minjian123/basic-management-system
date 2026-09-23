"""表归属登记校验测试（Kiwi 1078）：离线断言（清单 / 模型表 / 入链 / 脚本表集）与接库对账。"""

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from ops.check_tables import check_offline, check_table_db, main
from ops.seed_tables import seed_tables


def _url(tmp_path: Path) -> str:
    """临时平台服务库连接串。

    Args:
        tmp_path: 临时目录。

    Returns:
        str: 异步连接串。
    """
    return f"sqlite+aiosqlite:///{tmp_path / 'bms_platform.db'}"


@pytest.mark.kiwi_id(2178)
def test_check_offline_passes_on_repo() -> None:
    """离线断言在真实仓库状态通过（清单自校验 + 模型表已登记 + enabled 表入链 + 脚本表集不越界）。"""
    assert check_offline() == []


@pytest.mark.kiwi_id(2178)
def test_check_offline_rejects_script_table_outside_chain(tmp_path: Path) -> None:
    """脚本建了派生表集之外的表 → 拦截（防越界建表）。"""
    location = tmp_path / "platform" / "platform"
    location.mkdir(parents=True)
    (location / "0001_ghost.py").write_text(
        'revision = "0001_ghost"\n\n\ndef upgrade() -> None:\n    op.create_table("zzz_ghost")\n',
        encoding="utf-8",
    )
    errors = check_offline(versions_root=tmp_path)
    assert any("zzz_ghost" in error and "不在该链派生表集内" in error for error in errors)


@pytest.mark.kiwi_id(2178)
def test_check_table_db_roundtrip_and_conflicts(tmp_path: Path) -> None:
    """接库对账：库不可读 / 空库 / 种子后往返通过 / 字段不符逐项检出（同步入口，内部自建事件循环）。"""
    url = _url(tmp_path)
    assert any("不可读" in error for error in check_table_db(url)), "库不可读时应给出可诊断提示"

    asyncio.run(seed_tables(url))
    assert check_table_db(url) == []

    engine = create_engine(f"sqlite:///{tmp_path / 'bms_platform.db'}")
    try:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM sys_table_ownership"))
    finally:
        engine.dispose()
    assert any("库中无登记行" in error for error in check_table_db(url))

    asyncio.run(seed_tables(url))
    engine = create_engine(f"sqlite:///{tmp_path / 'bms_platform.db'}")
    try:
        with engine.begin() as connection:
            connection.execute(text("UPDATE sys_table_ownership SET owner = 'ghost' WHERE table_name = 'sys_outbox'"))
    finally:
        engine.dispose()
    assert any("owner 与清单不一致" in error for error in check_table_db(url))


@pytest.mark.kiwi_id(2178)
def test_check_tables_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI：离线通过（未给 `--url`）退出码 0 且输出校验范围。"""
    assert main([]) == 0
    assert "校验通过" in capsys.readouterr().out
