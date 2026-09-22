"""迁移与模型零漂移测试（Kiwi 1078）：逐链 autogenerate 对比（含反例验证比对有效）。"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Column, Integer, MetaData, Table, create_engine

from alembic import command
from bms_core.db.migration import BACKEND_ROOT, chain_metadata, config_section, has_revisions, resolve_chain


def _config(chain_name: str) -> Config:
    """取该链的 Alembic 配置。

    Args:
        chain_name: 链名。

    Returns:
        Config: Alembic 配置。
    """
    return Config(str(BACKEND_ROOT / "alembic.ini"), ini_section=config_section(resolve_chain(chain_name)))


def _upgrade(chain_name: str, url: str) -> None:
    """对目标库执行该链迁移。

    Args:
        chain_name: 链名。
        url: 连接串。
    """
    config = _config(chain_name)
    config.cmd_opts = SimpleNamespace(x=[f"url={url}"])  # pyright: ignore[reportAttributeAccessIssue]
    command.upgrade(config, "head")


def _diff(url: str, metadata: object) -> list[object]:
    """对比库结构与元数据（返回差异列表）。

    Args:
        url: 连接串（同步驱动）。
        metadata: 目标元数据。

    Returns:
        list[object]: 差异列表（空表示零漂移）。
    """
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            return compare_metadata(context, metadata)  # pyright: ignore[reportArgumentType]
    finally:
        engine.dispose()


@pytest.mark.kiwi_id(1078)
@pytest.mark.parametrize("chain_name", ["platform", "tenant"])
def test_chain_migration_matches_metadata(chain_name: str, tmp_path: Path) -> None:
    """每条链迁移后的库结构与链元数据子集零漂移（表 / 列 / 索引 / 唯一约束）。"""
    assert has_revisions(resolve_chain(chain_name)) is True
    path = tmp_path / f"{chain_name}.db"
    _upgrade(chain_name, f"sqlite+aiosqlite:///{path}")
    assert _diff(f"sqlite:///{path}", chain_metadata(resolve_chain(chain_name))) == []


@pytest.mark.kiwi_id(1078)
def test_unmigrated_tables_report_diff(tmp_path: Path) -> None:
    """反例：用含未迁移表的元数据对比租户链迁移库 → 差异非空（证明比对有效）。"""
    path = tmp_path / "tenant.db"
    _upgrade("tenant", f"sqlite+aiosqlite:///{path}")
    probe = MetaData()
    Table("drift_probe", probe, Column("id", Integer, primary_key=True))
    diff = _diff(f"sqlite:///{path}", probe)
    assert diff, "未迁移的表应产生差异"
    assert any("drift_probe" in str(item) for item in diff)
