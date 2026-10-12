"""字典表数据源列映射补齐用例（`02_10` 补齐）：缺列退化与宽松取整。

补齐 `bms_core/dict/table.py` 既有用例未覆盖的路径：

- 缺关键列（值列缺失 → 空行；标签 / 编码列缺失 → 回落值列）；
- `_as_int` / `_as_optional_int` 宽松取整分支（布尔 / 整数 / 负数字符串 / 非法）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import cast

import pytest
import sqlalchemy as sa

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.dict.table import DictColumnMapping, DictTableDataSource, _as_int, _as_optional_int

_OPEN_ENGINES: ConcurrentStableList[EngineRegistry] = ConcurrentStableList()


@pytest.fixture(autouse=True)
async def _close_open_engines() -> AsyncIterator[None]:  # pyright: ignore[reportUnusedFunction]
    """用例结束释放本模块内构造的引擎注册表。

    Yields:
        None: 用例运行期。
    """
    yield
    for registry in list(_OPEN_ENGINES):
        await registry.aclose()
    _OPEN_ENGINES.clear()


def _narrow_table() -> sa.Table:
    """构造缺 `name` / `code` 的窄表（仅 `id` / `label_src` / `sort`）。

    Returns:
        sa.Table: 窄表定义。
    """
    return sa.Table(
        "sys_narrow_dict",
        sa.MetaData(),
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("label_src", sa.String(64), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
    )


@pytest.fixture
def narrow_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[EngineRegistry, sa.Table]]:
    """临时 SQLite 库 + 窄表（两行）。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 环境变量覆盖。

    Yields:
        tuple[EngineRegistry, sa.Table]: 引擎注册表与表定义。
    """
    db_path = tmp_path / "narrow_dict.db"
    table = _narrow_table()
    sync_engine = sa.create_engine(f"sqlite:///{db_path}")
    table.create(sync_engine)
    with sync_engine.begin() as connection:
        connection.execute(
            table.insert(),
            [
                {"id": 1, "label_src": "甲", "sort": 1},
                {"id": 2, "label_src": "乙", "sort": 2},
            ],
        )
    sync_engine.dispose()
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", f"sqlite+aiosqlite:///{db_path}")
    get_settings.cache_clear()
    registry = EngineRegistry(EngineFactory(get_settings()))
    _OPEN_ENGINES.add(registry)
    yield registry, table
    get_settings.cache_clear()


def _minimal_table() -> sa.Table:
    """构造最小表（仅 `code` 列：无 id / sort / status / parent / 软删列）。

    Returns:
        sa.Table: 最小表定义。
    """
    return sa.Table(
        "sys_minimal_dict",
        sa.MetaData(),
        sa.Column("code", sa.String(64), primary_key=True),
    )


@pytest.fixture
def minimal_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[EngineRegistry, sa.Table]]:
    """临时 SQLite 库 + 最小表（两行）。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 环境变量覆盖。

    Yields:
        tuple[EngineRegistry, sa.Table]: 引擎注册表与表定义。
    """
    db_path = tmp_path / "minimal_dict.db"
    table = _minimal_table()
    sync_engine = sa.create_engine(f"sqlite:///{db_path}")
    table.create(sync_engine)
    with sync_engine.begin() as connection:
        connection.execute(table.insert(), [{"code": "only1"}, {"code": "only2"}])
    sync_engine.dispose()
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", f"sqlite+aiosqlite:///{db_path}")
    get_settings.cache_clear()
    registry = EngineRegistry(EngineFactory(get_settings()))
    _OPEN_ENGINES.add(registry)
    yield registry, table
    get_settings.cache_clear()


async def test_minimal_table_without_optional_columns(
    minimal_table: tuple[EngineRegistry, sa.Table],
) -> None:
    """无 id / sort / status / 父级 / 软删列：可选列全部跳过、不排序，仍可取数。"""
    registry, table = minimal_table
    source = DictTableDataSource(engines=registry, data_source="platform", table=table)
    items = await source.load("role", "zh-CN")
    assert [item.value for item in items if item.value] == ["only1", "only2"]
    assert items[0].id == 0
    assert items[0].sort == 0
    assert items[0].status == "enabled"


async def test_missing_value_column_returns_empty() -> None:
    """值列缺失 → 直接返回空元组（不查库）。"""
    table = _narrow_table()
    source = DictTableDataSource(
        engines=cast("EngineRegistry", object()),
        data_source="platform",
        table=table,
        mapping=DictColumnMapping(value="nope"),
    )
    assert await source.load("role", "zh-CN") == ()


async def test_missing_label_and_code_columns_fall_back_to_value(
    narrow_table: tuple[EngineRegistry, sa.Table],
) -> None:
    """标签 / 编码列缺失 → 回落值列；`sort` 列存在时按其排序。"""
    registry, table = narrow_table
    source = DictTableDataSource(
        engines=registry,
        data_source="platform",
        table=table,
        mapping=DictColumnMapping(value="label_src", label="absent_label", code="absent_code"),
    )
    items = await source.load("role", "zh-CN")
    assert [item.value for item in items] == ["甲", "乙"]
    assert [item.label for item in items] == ["甲", "乙"]
    assert [item.code for item in items] == ["甲", "乙"]
    assert [item.sort for item in items] == [1, 2]


def test_as_int_and_as_optional_int_branches() -> None:
    """宽松取整：布尔归 0、整数原样、负数字符串可解析、非法回落。"""
    assert _as_int(True) == 0
    assert _as_int(9) == 9
    assert _as_int("-4") == -4
    assert _as_int(None) == 0

    assert _as_optional_int(None) is None
    assert _as_optional_int(0) is None
    assert _as_optional_int(3) == 3
    assert _as_optional_int("5") == 5
