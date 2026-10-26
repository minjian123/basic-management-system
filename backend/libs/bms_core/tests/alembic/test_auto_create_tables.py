"""启动期自动建表（Kiwi 1078 / 2177 / 2303）：单元表集并集 / 无脚本照建 / 幂等 / 开关 / 拓扑无关。

07C `03_02` 口径：库随部署单元（`[app].unit`，缺省回落服务），表集 = 所含域表集并集 + 基础设施表；
**同一套域在合并与拆分两种拓扑下建出的表集一致、表名不变**。
"""

import asyncio
import sqlite3
from pathlib import Path

import pytest

from bms_core.core.concurrent import ConcurrentStableSet
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.db import bootstrap
from bms_core.db.bootstrap import (
    apply_unit_schema,
    db_keys_for,
    default_schema_of,
    ensure_unit_schema,
    unit_metadata,
)
from bms_core.db.engine import EngineFactory
from bms_core.db.migration import (
    DATASOURCE_ARCHIVE,
    DATASOURCE_PLATFORM,
    DATASOURCE_TENANT,
    unit_domains,
)
from bms_core.services.table_registry import infrastructure_tables, unit_tables


def _tables(path: Path) -> ConcurrentStableSet[str]:
    """取 SQLite 文件表名集合。

    Args:
        path: 库文件路径。

    Returns:
        ConcurrentStableSet[str]: 表名集合。
    """
    connection = sqlite3.connect(path)
    try:
        return ConcurrentStableSet(
            str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        )
    finally:
        connection.close()


def _point_to(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, service: str = "platform") -> tuple[Path, Path]:
    """把平台库 / 租户库指向临时 SQLite 文件、置单元标识并刷新配置。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
        service: 服务标识（缺省形态下部署单元 = 服务标识）。

    Returns:
        tuple[Path, Path]: （平台服务库文件, 租户库文件）。
    """
    platform = tmp_path / "platform.db"
    tenant = tmp_path / "tenant.db"
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", f"sqlite+aiosqlite:///{platform}")
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", f"sqlite+aiosqlite:///{tenant}")
    get_settings.cache_clear()
    settings = get_settings()
    settings.app.service = service
    settings.app.unit = ""
    return platform, tenant


@pytest.mark.kiwi_id(1078)
def test_db_key_mapping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """数据源键映射（单元 × 数据源）：平台库本单元、租户库逐开发租户、归档单键。"""
    _point_to(tmp_path, monkeypatch)
    settings = get_settings()
    assert db_keys_for(DATASOURCE_PLATFORM, settings) == ["platform"]
    assert all(key.startswith("tenant_") for key in db_keys_for(DATASOURCE_TENANT, settings))
    assert db_keys_for(DATASOURCE_ARCHIVE, settings) == ["archive"]


@pytest.mark.kiwi_id(2177)
def test_unit_metadata_is_domain_union(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """单元建表集 = 所含域表集并集 + 基础设施表（与域派生同源）。"""
    _point_to(tmp_path, monkeypatch)
    domains = unit_domains("platform")
    assert len(domains) > 1
    metadata = unit_metadata("platform", DATASOURCE_TENANT)
    assert ConcurrentStableSet(metadata.tables) <= ConcurrentStableSet(unit_tables(domains, DATASOURCE_TENANT))
    assert ConcurrentStableSet(metadata.tables) & infrastructure_tables(), "基础设施表应随单元建表集落地"
    assert {"sys_user", "sys_role", "sys_outbox"} <= ConcurrentStableSet(metadata.tables)


@pytest.mark.kiwi_id(2355)
def test_unit_metadata_equals_registry_derivation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """逐单元建表集与归属登记派生**严格相等**（模型按域收紧后建表集不变；07C `03_03`）。"""
    _point_to(tmp_path, monkeypatch)
    for unit in ("platform", "identity", "tenant"):
        domains = unit_domains(unit)
        for datasource in (DATASOURCE_PLATFORM, DATASOURCE_TENANT):
            expected = ConcurrentStableSet(unit_tables(domains, datasource))
            metadata = unit_metadata(unit, datasource)
            assert ConcurrentStableSet(metadata.tables) == expected, (unit, datasource)


@pytest.mark.kiwi_id(2303)
def test_apply_unit_schema_creates_and_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """建表幂等：首跑新建、重跑「新建 0 / 已存在 N」，表集不变。"""
    platform, _ = _point_to(tmp_path, monkeypatch)
    url = f"sqlite+aiosqlite:///{platform}"
    first = asyncio.run(apply_unit_schema("platform", DATASOURCE_PLATFORM, url, target="platform"))
    assert first.created > 0
    assert "sys_menu" in _tables(platform)
    second = asyncio.run(apply_unit_schema("platform", DATASOURCE_PLATFORM, url, target="platform"))
    assert second.created == 0
    assert second.existing == first.total


@pytest.mark.kiwi_id(2303)
def test_topology_invariance_table_sets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """合并 / 拆分两拓扑建出的表集一致（拆合不切清单、表名不变）。"""
    platform, _ = _point_to(tmp_path, monkeypatch)
    merged_url = f"sqlite+aiosqlite:///{platform}"
    merged = asyncio.run(apply_unit_schema("platform", DATASOURCE_PLATFORM, merged_url))
    split_db = tmp_path / "split.db"
    split_url = f"sqlite+aiosqlite:///{split_db}"
    for domain in unit_domains("platform"):
        asyncio.run(apply_unit_schema(domain, DATASOURCE_PLATFORM, split_url))
    assert _tables(platform) == _tables(split_db)
    assert merged.total == len(_tables(platform))


@pytest.mark.kiwi_id(2303)
async def test_ensure_unit_schema_switch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """启动期开关：关则跳过；开则按单元建表并回报已处理的库键。"""
    platform, _ = _point_to(tmp_path, monkeypatch)
    settings = get_settings()
    factory = EngineFactory(settings)
    settings.database.auto_create = False
    assert await ensure_unit_schema(settings, factory=factory) == []
    settings.database.auto_create = True
    handled = await ensure_unit_schema(settings, factory=factory)
    assert "platform" in handled
    assert "sys_menu" in _tables(platform)
    assert "sys_outbox" in _tables(platform)


@pytest.mark.kiwi_id(2359)
def test_db_keys_for_unknown_datasource(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """未知数据源段不产库键（早退空清单，不抛错）。"""
    _point_to(tmp_path, monkeypatch)
    assert db_keys_for("legacy", get_settings()) == []


@pytest.mark.kiwi_id(2359)
def test_default_schema_of_dm_only() -> None:
    """模式名取自达梦连接串的 `database` 段；异步方言返回空串（不切模式）。"""
    assert default_schema_of("dm+dmPython://SYSDBA:pwd@127.0.0.1:5236/BMS_TEST_DM") == "BMS_TEST_DM"
    assert default_schema_of("sqlite+aiosqlite:///./bms.db") == ""


@pytest.mark.kiwi_id(2359)
def test_apply_unit_schema_sync_driver_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """同步驱动建表（与达梦同路径）：首跑新建、重跑「新建 0 / 已存在 N」，不重复建表。"""
    _point_to(tmp_path, monkeypatch)
    database = tmp_path / "sync.db"
    url = f"sqlite:///{database}"
    first = asyncio.run(apply_unit_schema("platform", DATASOURCE_PLATFORM, url, target="platform-sync"))
    assert first.created == first.total
    assert "sys_menu" in _tables(database)
    second = asyncio.run(apply_unit_schema("platform", DATASOURCE_PLATFORM, url, target="platform-sync"))
    assert second.created == 0
    assert second.existing == first.total


@pytest.mark.kiwi_id(2359)
async def test_ensure_unit_schema_swallows_config_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """域派生失败（单元未登记 / 布局异常）不阻断启动：返回空清单。"""
    _point_to(tmp_path, monkeypatch)
    settings = get_settings()

    def _boom(unit: str) -> ConcurrentStableSet[str]:
        """替身：域派生即抛配置异常。"""
        raise ConfigError(f"单元未登记：{unit}")

    monkeypatch.setattr(bootstrap, "unit_domains", _boom)
    assert await ensure_unit_schema(settings) == []


@pytest.mark.kiwi_id(2359)
async def test_ensure_unit_schema_skips_when_unit_not_declared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """单元标识未声明（`[app].unit` 与 `[app].service` 均为空）：跳过建表、返回空清单。"""
    _point_to(tmp_path, monkeypatch)
    settings = get_settings()
    settings.app.unit = ""
    settings.app.service = ""

    assert await ensure_unit_schema(settings) == []
