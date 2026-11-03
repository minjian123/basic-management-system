"""字典表源 i18n 三级回退（Kiwi 2405）：请求语言 → 系统默认语言 → 主表列。

字典六表与 3 张 `_i18n` 已在 02_09 拆除，字典 label 的多语言由通用表源 `DictI18nSpec` 承载；
本段给它补上「回退系统默认语言」一级，与主表 i18n 附表同口径（否则同一平台两套回退规则）。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.db.registry import EngineRegistry
from bms_core.dict.table import DictI18nSpec, DictTableDataSource
from bms_core.i18n.base import current_default_locale

pytestmark = [
    pytest.mark.kiwi_id(2405),
    pytest.mark.own_db("被测对象是字典表源的建表与 i18n 回退口径：需自造列结构的表，无法落在共享库"),
]

_DUMMY_REGISTRY = cast("EngineRegistry", object())


def _base_table() -> sa.Table:
    """构造标准字典主表。

    Returns:
        sa.Table: 主表定义。
    """
    return sa.Table(
        "sys_probe",
        sa.MetaData(),
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="enabled"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )


def _i18n_table() -> sa.Table:
    """构造多语言附表。

    Returns:
        sa.Table: 附表定义。
    """
    return sa.Table(
        "sys_probe_i18n",
        sa.MetaData(),
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("probe_id", sa.BigInteger(), nullable=False),
        sa.Column("locale", sa.String(16), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )


def _seed(db_path: Path, table: sa.Table, i18n: sa.Table, rows: list[sa.Table]) -> None:
    """建表并写入主表行与附表行。

    Args:
        db_path: SQLite 文件路径。
        table: 主表。
        i18n: 附表。
        rows: 附表行（`i18n.insert()` 参数）。
    """
    engine = sa.create_engine(f"sqlite:///{db_path}")
    table.create(engine)
    i18n.create(engine)
    with engine.begin() as connection:
        connection.execute(table.insert(), [{"id": 1, "code": "probe", "name": "主表名", "status": "enabled"}])
        if rows:
            connection.execute(i18n.insert(), rows)
    engine.dispose()


@asynccontextmanager
async def _local_session(db_path: Path) -> AsyncGenerator[AsyncSession]:
    """本地 SQLite 异步会话。

    Args:
        db_path: 库路径。

    Yields:
        AsyncSession: 会话。
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _source(table: sa.Table, i18n: sa.Table, db_path: Path) -> DictTableDataSource:
    """构造把会话替换为本地库的表源。

    Args:
        table: 主表。
        i18n: 附表。
        db_path: 库路径。

    Returns:
        DictTableDataSource: 表源实例。
    """
    source = DictTableDataSource(
        engines=_DUMMY_REGISTRY,
        data_source="platform",
        table=table,
        i18n=DictI18nSpec(table=i18n, relation_column="probe_id"),
    )
    source._session = lambda: _local_session(db_path)  # pyright: ignore[reportAttributeAccessIssue,reportPrivateUsage]
    return source


async def test_label_falls_back_to_default_locale(tmp_path: Path) -> None:
    """请求语言无译文时回退系统默认语言（默认 zh-CN），而非直接回主表列。"""
    table, i18n = _base_table(), _i18n_table()
    db_path = tmp_path / "dict_default.db"
    _seed(db_path, table, i18n, [{"id": 11, "probe_id": 1, "locale": "zh-CN", "name": "默认语言名"}])
    items = await _source(table, i18n, db_path).load("probe", "en-US")
    assert [item.label for item in items] == ["默认语言名"]


async def test_label_prefers_request_locale(tmp_path: Path) -> None:
    """请求语言有译文时取请求语言（第一级优先）。"""
    table, i18n = _base_table(), _i18n_table()
    db_path = tmp_path / "dict_primary.db"
    _seed(
        db_path,
        table,
        i18n,
        [
            {"id": 11, "probe_id": 1, "locale": "zh-CN", "name": "默认语言名"},
            {"id": 12, "probe_id": 1, "locale": "en-US", "name": "English Name"},
        ],
    )
    items = await _source(table, i18n, db_path).load("probe", "en-US")
    assert [item.label for item in items] == ["English Name"]


async def test_label_locale_case_insensitive(tmp_path: Path) -> None:
    """存量大小写混杂的 locale 行可被标准形态请求命中。"""
    table, i18n = _base_table(), _i18n_table()
    db_path = tmp_path / "dict_case.db"
    _seed(db_path, table, i18n, [{"id": 11, "probe_id": 1, "locale": "ZH-cn", "name": "大小写存量"}])
    items = await _source(table, i18n, db_path).load("probe", "zh-CN")
    assert [item.label for item in items] == ["大小写存量"]


async def test_label_follows_runtime_default_locale(tmp_path: Path) -> None:
    """默认语言取运行期清单上下文（租户切默认语言后回退目标随之变化）。"""
    table, i18n = _base_table(), _i18n_table()
    db_path = tmp_path / "dict_ctx.db"
    _seed(db_path, table, i18n, [{"id": 11, "probe_id": 1, "locale": "en-US", "name": "English Name"}])
    token = current_default_locale.set("en-US")
    try:
        items = await _source(table, i18n, db_path).load("probe", "ja-JP")
    finally:
        current_default_locale.reset(token)
    assert [item.label for item in items] == ["English Name"]


async def test_label_falls_back_to_owner_column(tmp_path: Path) -> None:
    """两级语言都无译文时回退主表默认列。"""
    table, i18n = _base_table(), _i18n_table()
    db_path = tmp_path / "dict_base.db"
    _seed(db_path, table, i18n, [])
    items = await _source(table, i18n, db_path).load("probe", "en-US")
    assert [item.label for item in items] == ["主表名"]
