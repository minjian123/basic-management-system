"""字典表源扩展（Kiwi 2372）：i18n 附表覆盖与回退 / 平台库域 / `sort` 列缺省。

12 个平台内建字典共用同一表源：差异只在「库域 + 表 + i18n 附表 + 排序列」，本用例锁死这四类差异，
防止后续新增字典又回到「一 key 一个提供者类」的分散实现。

隔离口径：不搭 `EngineRegistry` 的配置链（dev 覆盖按服务模板建库，容易把用例引到真实库），
改为替换表源的 `_session` 为临时 SQLite 会话、用记录器断言库键选择——测的是表源自身逻辑。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db.registry import EngineRegistry
from bms_core.dict.table import DictI18nSpec, DictTableDataSource, DictTableScope

_DUMMY_REGISTRY = cast("EngineRegistry", object())


def _base_table(name: str = "sys_role") -> sa.Table:
    """构造标准字典表（`id` / `code` / `name` / `status` / `parent_id` / `deleted_at`，无 `sort`）。

    Args:
        name: 表名。

    Returns:
        sa.Table: 主表定义。
    """
    return sa.Table(
        name,
        sa.MetaData(),
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="enabled"),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )


def _i18n_table(name: str = "sys_role_i18n") -> sa.Table:
    """构造多语言附表（`role_id` / `locale` / `name` / `deleted_at`）。

    Args:
        name: 表名。

    Returns:
        sa.Table: 附表定义。
    """
    return sa.Table(
        name,
        sa.MetaData(),
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("locale", sa.String(16), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )


def _seed_sqlite(db_path: Path, table: sa.Table, *, i18n: sa.Table | None = None) -> None:
    """建表写入两行（第二行停用）与一行英文附表。

    Args:
        db_path: SQLite 文件路径。
        table: 主表。
        i18n: 多语言附表（可选）。
    """
    sync_engine = sa.create_engine(f"sqlite:///{db_path}")
    table.create(sync_engine)
    if i18n is not None:
        i18n.create(sync_engine)
    with sync_engine.begin() as connection:
        connection.execute(
            table.insert(),
            [
                {"id": 1, "code": "admin", "name": "管理员", "status": "enabled"},
                {"id": 2, "code": "viewer", "name": "访客", "status": "disabled"},
            ],
        )
        if i18n is not None:
            connection.execute(i18n.insert(), [{"id": 11, "role_id": 1, "locale": "en-US", "name": "Administrator"}])
    sync_engine.dispose()


@asynccontextmanager
async def _local_session(db_path: Path) -> AsyncGenerator[AsyncSession]:
    """本地 SQLite 异步会话（替代 `session_scope`，只供表源用例）。

    Args:
        db_path: SQLite 文件路径。

    Yields:
        AsyncSession: 会话。
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _source(
    table: sa.Table,
    db_path: Path,
    *,
    i18n: DictI18nSpec | None = None,
    db_scope: str = DictTableScope.TENANT.value,
) -> DictTableDataSource:
    """构造把会话替换为本地 SQLite 的表源。

    Args:
        table: 主表。
        db_path: 本地库路径。
        i18n: 多语言附表规格。
        db_scope: 库域。

    Returns:
        DictTableDataSource: 表源实例（`_session` 已替换）。
    """
    source = DictTableDataSource(
        engines=_DUMMY_REGISTRY, data_source="platform", table=table, db_scope=db_scope, i18n=i18n
    )
    source._session = lambda: _local_session(db_path)  # pyright: ignore[reportAttributeAccessIssue,reportPrivateUsage]
    return source


@pytest.fixture
def dict_db(tmp_path: Path) -> tuple[sa.Table, DictI18nSpec, Path]:
    """带 i18n 附表的临时库。

    Args:
        tmp_path: 临时目录。

    Returns:
        tuple[sa.Table, DictI18nSpec, Path]: 主表、i18n 规格、库路径。
    """
    table = _base_table()
    return table, DictI18nSpec(table=_i18n_table(), relation_column="role_id"), tmp_path / "dict.db"


@pytest.mark.kiwi_id(2372)
async def test_i18n_overrides_label_for_locale(dict_db: tuple[sa.Table, DictI18nSpec, Path]) -> None:
    """有对应 locale 的 i18n 行时，label 取附表文案。"""
    table, i18n, db_path = dict_db
    _seed_sqlite(db_path, table, i18n=i18n.table)
    items = await _source(table, db_path, i18n=i18n).load("role", "en-US")
    assert [item.label for item in items] == ["Administrator"]


@pytest.mark.kiwi_id(2372)
async def test_i18n_falls_back_to_base_name(dict_db: tuple[sa.Table, DictI18nSpec, Path]) -> None:
    """无对应 locale 的 i18n 行时回退主表 `name`（缺省回退默认文案）。"""
    table, i18n, db_path = dict_db
    _seed_sqlite(db_path, table, i18n=i18n.table)
    items = await _source(table, db_path, i18n=i18n).load("role", "zh-CN")
    assert [item.label for item in items] == ["管理员"]


@pytest.mark.kiwi_id(2372)
async def test_without_i18n_label_always_base(dict_db: tuple[sa.Table, DictI18nSpec, Path]) -> None:
    """未配 i18n 规格时 label 恒取主表（与 locale 无关）。"""
    table, _i18n, db_path = dict_db
    _seed_sqlite(db_path, table)
    items = await _source(table, db_path).load("role", "en-US")
    assert [item.label for item in items] == ["管理员"]


@pytest.mark.kiwi_id(2372)
async def test_missing_sort_column_orders_by_id(dict_db: tuple[sa.Table, DictI18nSpec, Path]) -> None:
    """缺 `sort` 列时按 `id` 升序（12 张表里只有 `sys_identity_provider` 有 sort 列）。"""
    table, _i18n, db_path = dict_db
    _seed_sqlite(db_path, table)
    items = await _source(table, db_path).load("role", "zh-CN")
    assert [(item.id, item.code) for item in items] == [(1, "admin")]


@pytest.mark.kiwi_id(2372)
async def test_disabled_rows_excluded(dict_db: tuple[sa.Table, DictI18nSpec, Path]) -> None:
    """停用行不进入字典结果（`status='enabled'` 过滤）。"""
    table, _i18n, db_path = dict_db
    _seed_sqlite(db_path, table)
    items = await _source(table, db_path).load("role", "zh-CN")
    assert [item.code for item in items] == ["admin"]


@pytest.mark.kiwi_id(2372)
async def test_platform_scope_uses_platform_db_key(
    monkeypatch: pytest.MonkeyPatch, dict_db: tuple[sa.Table, DictI18nSpec, Path]
) -> None:
    """`db_scope=platform` 走平台库键（`session_scope(..., db_key=build_platform_db_key())`）。"""
    table, _i18n, db_path = dict_db
    _seed_sqlite(db_path, table)
    captured: ConcurrentStableList[str | None] = ConcurrentStableList()

    @asynccontextmanager
    async def _recording_scope(
        registry: EngineRegistry, *, db_key: str | None = None, read_only: bool = False
    ) -> AsyncGenerator[AsyncSession]:
        captured.add(db_key)
        async with _local_session(db_path) as session:
            yield session

    monkeypatch.setattr("bms_core.dict.table.session_scope", _recording_scope)
    source = DictTableDataSource(
        engines=_DUMMY_REGISTRY, data_source="platform", table=table, db_scope=DictTableScope.PLATFORM.value
    )
    items = await source.load("role", "zh-CN")
    assert [item.code for item in items] == ["admin"]
    assert len(captured) == 1 and captured[0] is not None


def _seed_custom(
    db_path: Path,
    table: sa.Table,
    *,
    extra: sa.Table | None = None,
    extra_rows: ConcurrentStableList[dict[str, object]] | None = None,
) -> None:
    """建主表（写一行启用）与可选附表（写指定行），供「附表列不全」用例。

    Args:
        db_path: SQLite 文件路径。
        table: 主表。
        extra: 附表（可选）。
        extra_rows: 附表行（可选）。
    """
    engine = sa.create_engine(f"sqlite:///{db_path}")
    table.create(engine)
    with engine.begin() as connection:
        connection.execute(table.insert(), [{"id": 1, "code": "admin", "name": "管理员", "status": "enabled"}])
    if extra is not None:
        extra.create(engine)
        if extra_rows:
            with engine.begin() as connection:
                connection.execute(extra.insert(), list(extra_rows))
    engine.dispose()


@pytest.mark.kiwi_id(2372)
async def test_i18n_table_without_name_column_skips_join(tmp_path: Path) -> None:
    """附表缺 `name` 列时不做 join，label 回退主表（配置错不致 500）。"""
    table = _base_table()
    db_path = tmp_path / "dict_partial.db"
    partial = sa.Table(
        "sys_role_i18n_partial",
        sa.MetaData(),
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("locale", sa.String(16), nullable=False),
    )
    _seed_custom(db_path, table, extra=partial)
    i18n = DictI18nSpec(table=partial, relation_column="role_id")
    items = await _source(table, db_path, i18n=i18n).load("role", "en-US")
    assert [item.label for item in items] == ["管理员"]


@pytest.mark.kiwi_id(2372)
async def test_i18n_table_without_soft_delete_column(tmp_path: Path) -> None:
    """附表无 `deleted_at` 列时按「无软删」处理，仍能命中译文。"""
    table = _base_table()
    db_path = tmp_path / "dict_no_soft.db"
    no_soft = sa.Table(
        "sys_role_i18n_nosoft",
        sa.MetaData(),
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("locale", sa.String(16), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
    )
    _seed_custom(
        db_path,
        table,
        extra=no_soft,
        extra_rows=ConcurrentStableList([{"id": 11, "role_id": 1, "locale": "en-US", "name": "Administrator"}]),
    )
    i18n = DictI18nSpec(table=no_soft, relation_column="role_id")
    items = await _source(table, db_path, i18n=i18n).load("role", "en-US")
    assert [item.label for item in items] == ["Administrator"]
