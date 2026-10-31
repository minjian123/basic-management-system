"""数据源登记启动期校验（Kiwi 2372，02_01）：清单自校验 + 本地提供者覆盖（fail-closed）。

启动期校验与 `ops/check_tables.py` 离线校验共用 `DataSourceRegistry.validate()`，本文件锁的是
「启动入口的取舍」：校验范围是**本仓内建清单**（产品清单注入项由装载入口与跨仓对账保证）、
什么时候做覆盖校验（仅统一出口且本进程确有提供者）、违规即拒启（不 silently 跳过）。
"""

import pytest

from bms_core import application
from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.config import PluginSelection, Settings, get_settings
from bms_core.core.exceptions import CatalogError
from bms_core.datasource.registry import (
    DATA_SOURCE_CATALOG,
    DataSourceRecord,
    register_data_source_records,
    reset_data_source_records,
)


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


def _patch_catalog(monkeypatch: pytest.MonkeyPatch, records: ConcurrentStableList[DataSourceRecord]) -> None:
    """替换本仓内建数据源清单（启动校验读取的入口）。

    Args:
        monkeypatch: 替换器。
        records: 期望的内建清单。
    """
    monkeypatch.setattr(application, "DATA_SOURCE_CATALOG", records)


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
    _patch_catalog(monkeypatch, ConcurrentStableList((record,)))
    _patch_providers(monkeypatch, ConcurrentStableList(("platform",)))
    with pytest.raises(CatalogError, match="数据源无提供者覆盖"):
        application._validate_data_sources(_settings("routed"))  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2372)
def test_ignores_injected_product_records(monkeypatch: pytest.MonkeyPatch) -> None:
    """产品清单注入项不参与启动校验（其出口指向产品命名空间；校验它会让所有服务因产品笔误拒启）。"""
    monkeypatch.setattr(application, "DATA_SOURCE_CATALOG", DATA_SOURCE_CATALOG)
    _patch_providers(monkeypatch, ConcurrentStableList(("platform",)))
    try:
        register_data_source_records(
            ConcurrentStableList(
                (
                    DataSourceRecord(
                        data_source_key="demo_dept",
                        name="部门",
                        data_source="demo.demo.dept",
                        strategies=ConcurrentStableFrozenList(("tenant",)),
                    ),
                )
            )
        )
        application._validate_data_sources(_settings("routed"))  # pyright: ignore[reportPrivateUsage]
    finally:
        reset_data_source_records()


@pytest.mark.kiwi_id(2372)
def test_skips_coverage_when_no_local_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """本进程不承担字典取数（无提供者）时不做覆盖校验——非 platform 服务用 `http` 出口，不能因此起不来。"""
    record = DataSourceRecord(data_source_key="ghost", name="幽灵", data_source="ghost_outlet")
    _patch_catalog(monkeypatch, ConcurrentStableList((record,)))
    _patch_providers(monkeypatch, ConcurrentStableList())
    application._validate_data_sources(_settings("routed"))  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2372)
def test_rejects_invalid_catalog_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """内建清单自身违规（标识格式 / 名称或出口为空）直接拒启。"""
    bad = DataSourceRecord(data_source_key="Bad Key", name="", data_source="")
    _patch_catalog(monkeypatch, ConcurrentStableList((bad,)))
    with pytest.raises(CatalogError, match="数据源登记校验失败"):
        application._validate_data_sources(_settings(""))  # pyright: ignore[reportPrivateUsage]
