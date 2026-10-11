"""通用数据接口三层用例（Kiwi 2288，02_10）：继承关系 / 通用条目 / 缺省实现 / 可直用实现类。"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import cast

import pytest
import sqlalchemy as sa

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.objects import BaseFrameworkObject
from bms_core.datasource.base import (
    BaseDictDataSource,
    BaseFormDataSource,
    BaseGenericDataSource,
    DataSourceItem,
)
from bms_core.datasource.registry import DataSourceKind
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.dict.outlet import EmptyDictDataSource
from bms_core.dict.table import DictColumnMapping, DictTableDataSource

_OPEN_ENGINES: ConcurrentStableList[EngineRegistry] = ConcurrentStableList()
"""用例内构造的引擎注册表（用例结束统一 `aclose`）。"""


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


def _dict_table() -> sa.Table:
    """构造临时字典表（标准字典系统字段 + id）。

    Returns:
        sa.Table: 字典表定义。
    """
    return sa.Table(
        "sys_demo_dict",
        sa.MetaData(),
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="enabled"),
        sa.Column("deleted_at", sa.String(32), nullable=True),
    )


@pytest.fixture
def dict_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[EngineRegistry, sa.Table]]:
    """临时 SQLite 库 + 已建字典表（含启用 / 停用 / 软删三类行）。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 环境变量覆盖。

    Yields:
        tuple[EngineRegistry, sa.Table]: 引擎注册表与表定义。
    """
    db_path = tmp_path / "dict_table.db"
    table = _dict_table()
    sync_engine = sa.create_engine(f"sqlite:///{db_path}")
    table.create(sync_engine)
    with sync_engine.begin() as connection:
        connection.execute(
            table.insert(),
            [
                {
                    "id": 1,
                    "code": "a",
                    "name": "甲",
                    "parent_id": None,
                    "sort": 1,
                    "status": "enabled",
                    "deleted_at": None,
                },
                {
                    "id": 2,
                    "code": "b",
                    "name": "乙",
                    "parent_id": 1,
                    "sort": 2,
                    "status": "enabled",
                    "deleted_at": None,
                },
                {
                    "id": 3,
                    "code": "c",
                    "name": "丙",
                    "parent_id": None,
                    "sort": 3,
                    "status": "disabled",
                    "deleted_at": None,
                },
                {
                    "id": 4,
                    "code": "d",
                    "name": "丁",
                    "parent_id": None,
                    "sort": 4,
                    "status": "enabled",
                    "deleted_at": "2026-10-11",
                },
            ],
        )
    sync_engine.dispose()
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", f"sqlite+aiosqlite:///{db_path}")
    get_settings.cache_clear()
    registry = EngineRegistry(EngineFactory(get_settings()))
    _OPEN_ENGINES.add(registry)
    yield registry, table
    get_settings.cache_clear()


class _FakeDictSource(BaseDictDataSource):
    """伪字典数据源（实现抽象面，校验基础层缺省实现）。"""

    @property
    def data_source(self) -> str:
        """数据出口标识。

        Returns:
            str: 数据出口标识。
        """
        return "fake"

    async def load(self, data_source_key: str, locale: str) -> tuple[DataSourceItem, ...]:
        """按标识返回单条行。

        Args:
            data_source_key: 数据源标识。
            locale: 语言。

        Returns:
            tuple[DataSourceItem, ...]: 单条行。
        """
        return (DataSourceItem(value=data_source_key, label=f"占位{data_source_key}"),)


class _RenamedColumns(DictTableDataSource):
    """继承覆写 `mapping()`：label 取 `name`（默认即标准列名，此处显式覆写以校验可继承性）。"""

    def mapping(self) -> DictColumnMapping:
        """列名映射（覆写示例）。

        Returns:
            DictColumnMapping: 列名映射。
        """
        return DictColumnMapping(value="code", label="name")


@pytest.mark.kiwi_id(2288)
def test_layer_inheritance_and_contract() -> None:
    """表单 / 字典通用数据接口均继承基础；提供者层为框架对象、不占插件端口键。"""
    assert issubclass(BaseFormDataSource, BaseGenericDataSource)
    assert issubclass(BaseDictDataSource, BaseGenericDataSource)
    assert issubclass(BaseGenericDataSource, BaseFrameworkObject)
    assert BaseDictDataSource.DICT_FIELDS == ("code", "name", "parent_id", "sort", "status")
    assert {item.value for item in DataSourceKind} == {"dict", "form"}


@pytest.mark.kiwi_id(2288)
async def test_generic_default_version_and_batch() -> None:
    """基础层缺省实现：`version` 缺省 0、`batch` 逐键 `load` 合并、`cache_domain` 缺省。"""
    source = _FakeDictSource()
    assert await source.version("any") == 0
    assert source.cache_domain == "data_source"
    merged = await source.batch(("role", "user"), "zh-CN")
    assert set(merged) == {"role", "user"}
    rows = merged["role"]
    assert rows[0].label == "占位role"


@pytest.mark.kiwi_id(2288)
async def test_empty_dict_data_source_returns_nothing() -> None:
    """缺省空实现：恒定空行。"""
    assert await EmptyDictDataSource("platform").load("role", "zh-CN") == ()


@pytest.mark.kiwi_id(2288)
async def test_dict_table_load_filters_and_maps(dict_table: tuple[EngineRegistry, sa.Table]) -> None:
    """可直用实现类：按启用 + 未软删过滤、按 sort 排序、标准列映射为通用条目。"""
    registry, table = dict_table
    source = DictTableDataSource(engines=registry, data_source="platform", table=table)
    items = await source.load("role", "zh-CN")
    assert [item.value for item in items] == ["a", "b"]
    assert [item.label for item in items] == ["甲", "乙"]
    assert items[0].parent_id is None
    assert items[1].parent_id == 1
    assert items[0].sort == 1
    assert source.data_source == "platform"


@pytest.mark.kiwi_id(2288)
def test_dict_table_row_mapping_and_mapping_overridable() -> None:
    """可直用实现类：`row_to_item` 映射（非正值 parent_id 归 None）与 `mapping()` 可继承覆写。"""
    table = _dict_table()
    source = _RenamedColumns(engines=cast("EngineRegistry", object()), data_source="platform", table=table)
    assert source.mapping() == DictColumnMapping(value="code", label="name")
    item = source.row_to_item(
        ConcurrentStableDict(
            {
                "id": 7,
                "value": "v",
                "label": "标签",
                "code": "v",
                "parent_id": 0,
                "sort": 2,
                "status": "enabled",
            }
        )
    )
    assert item.value == "v" and item.label == "标签"
    assert item.parent_id is None
    assert item.sort == 2
    assert item.status == "enabled"
