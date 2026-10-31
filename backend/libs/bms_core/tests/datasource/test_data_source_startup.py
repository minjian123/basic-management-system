"""数据源登记启动期校验（Kiwi 2372，02_01）：清单自校验 + 本地提供者覆盖（fail-closed）。

启动期校验与 `ops/check_tables.py` 离线校验共用 `DataSourceRegistry.validate()`，本文件锁的是
「启动入口的取舍」：什么时候做覆盖校验（仅统一出口且本进程确有提供者）、产品来源豁免、
违规即拒启（不 silently 跳过）。
"""

import pytest

from bms_core import application
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import PluginSelection, Settings, get_settings
from bms_core.core.exceptions import CatalogError
from bms_core.datasource.registry import DataSourceRecord


def _settings(provider: str) -> Settings:
    """构造带指定数据源出口的配置（其余取测试环境实测值）。

    Args:
        provider: `[data_source].provider` 取值。

    Returns:
        Settings: 配置副本。
    """
    settings = get_settings().model_copy(deep=True)
    settings.data_source = PluginSelection(provider=provider)
    return settings


def _patch_records(monkeypatch: pytest.MonkeyPatch, records: ConcurrentStableList[DataSourceRecord]) -> None:
    """替换登记合并视图（启动校验读取的入口）。

    Args:
        monkeypatch: 替换器。
        records: 期望的登记记录。
    """
    monkeypatch.setattr(application, "data_source_records_view", lambda: records)


def _patch_providers(monkeypatch: pytest.MonkeyPatch, outlets: ConcurrentStableList[str]) -> None:
    """替换本进程已登记的提供者出口集合。

    Args:
        monkeypatch: 替换器。
        outlets: 出口标识清单。
    """
    monkeypatch.setattr(
        "bms_core.dict.outlet.registered_data_sources",
        lambda: dict.fromkeys(outlets, object()),
    )


@pytest.mark.kiwi_id(2372)
def test_rejects_platform_record_without_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """统一出口 + 本进程有提供者时，`origin=platform` 的登记项必须有对应提供者（否则启动即拒）。"""
    record = DataSourceRecord(data_source_key="ghost", name="幽灵", data_source="ghost_outlet")
    _patch_records(monkeypatch, ConcurrentStableList((record,)))
    _patch_providers(monkeypatch, ConcurrentStableList(("platform",)))
    with pytest.raises(CatalogError, match="数据源无提供者覆盖"):
        application._validate_data_sources(_settings("routed"))  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2372)
def test_product_origin_exempt_from_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    """产品来源不经本地提供者（前端直取产品命名空间），覆盖校验豁免。"""
    record = DataSourceRecord(
        data_source_key="dept_tree",
        name="部门树",
        data_source="mdm.data_source.dept",
        origin="product",
        product_key="mdm",
        path="/data-source/dept-tree",
    )
    _patch_records(monkeypatch, ConcurrentStableList((record,)))
    _patch_providers(monkeypatch, ConcurrentStableList(("platform",)))
    application._validate_data_sources(_settings("routed"))  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2372)
def test_skips_coverage_when_no_local_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """本进程不承担字典取数（无提供者）时不做覆盖校验——非 platform 服务用 `http` 出口，不能因此起不来。"""
    record = DataSourceRecord(data_source_key="ghost", name="幽灵", data_source="ghost_outlet")
    _patch_records(monkeypatch, ConcurrentStableList((record,)))
    _patch_providers(monkeypatch, ConcurrentStableList())
    application._validate_data_sources(_settings("routed"))  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2372)
def test_rejects_invalid_catalog_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """清单自身违规（标识格式 / 名称或出口为空）直接拒启。"""
    bad = DataSourceRecord(data_source_key="Bad Key", name="", data_source="")
    _patch_records(monkeypatch, ConcurrentStableList((bad,)))
    with pytest.raises(CatalogError, match="数据源登记校验失败"):
        application._validate_data_sources(_settings(""))  # pyright: ignore[reportPrivateUsage]
