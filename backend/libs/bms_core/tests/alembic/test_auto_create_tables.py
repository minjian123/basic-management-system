"""SQLite 开发库自动建表测试（Kiwi 1078 / 2177）：开关 / 方言 / 本服务分链表集 / 幂等。"""

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import MetaData

import bms_core.db.bootstrap as bootstrap_module
from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.config import get_settings
from bms_core.db.bootstrap import db_keys_for, ensure_development_schema
from bms_core.db.engine import EngineFactory
from bms_core.db.migration import (
    DATASOURCE_ARCHIVE,
    DATASOURCE_PLATFORM,
    DATASOURCE_TENANT,
    MigrationChain,
    resolve_chain,
)
from bms_core.db.registry import EngineRegistry


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
            row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        )
    finally:
        connection.close()


def _point_to(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, service: str = "platform") -> tuple[Path, Path]:
    """把平台库 / 租户库指向临时 SQLite 文件、置服务标识并刷新配置。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
        service: 服务标识（分链按服务解析，启动期由服务包声明回写）。

    Returns:
        tuple[Path, Path]: （平台服务库文件, 租户库文件）。
    """
    platform = tmp_path / "platform.db"
    tenant = tmp_path / "tenant.db"
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", f"sqlite+aiosqlite:///{platform}")
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", f"sqlite+aiosqlite:///{tenant}")
    get_settings.cache_clear()
    get_settings().app.service = service
    return platform, tenant


@pytest.mark.kiwi_id(1078)
def test_db_key_mapping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """数据源键映射（06_02 分链）：平台链本服务平台库；租户链逐开发租户；归档单键。"""
    _point_to(tmp_path, monkeypatch)
    settings = get_settings()
    assert db_keys_for(resolve_chain("platform:platform"), settings) == ["platform"]
    assert db_keys_for(resolve_chain("platform:tenant"), settings) == [
        f"tenant_{code}" for code in settings.tenant.dev_tenants
    ]
    assert db_keys_for(resolve_chain("platform:tenant"), settings)[0] == "tenant_demo"
    assert db_keys_for(resolve_chain("platform:archive"), settings) == ["archive"]


@pytest.mark.kiwi_id(1078)
async def test_sqlite_auto_create_tables_and_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """开关开 + SQLite：按**本服务分链表集**建表，重复执行幂等且不建骨架表。"""
    platform, tenant = _point_to(tmp_path, monkeypatch)
    settings = get_settings()
    assert settings.database.auto_create is True

    registry = EngineRegistry(EngineFactory(settings))
    try:
        handled = await ensure_development_schema(registry, settings)
        assert handled == ["platform", "tenant_demo"]
        platform_tables = _tables(platform)
        assert {"sys_module", "sys_module_i18n", "sys_table_ownership", "sys_outbox"} <= platform_tables
        assert "sys_tenant" not in platform_tables, "租户注册归 tenant 服务，不进平台服务的平台链"
        tenant_tables = _tables(tenant)
        assert {"sys_data_scope", "sys_query_scheme", "sys_outbox"} <= tenant_tables
        assert "sys_task" not in tenant_tables, "骨架表（planned）不入链、不自动建表"

        before = (_tables(platform), _tables(tenant))
        assert await ensure_development_schema(registry, settings) == handled
        assert (_tables(platform), _tables(tenant)) == before, "重复执行不新建表"
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(2177)
async def test_auto_create_service_ized_targets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """服务化模板下自动建表（分链）：平台链建本服务平台服务库；租户链按 `dev_tenants` 逐租户建库。"""
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}.db")
    monkeypatch.setenv(
        "BMS_DATABASE__TENANTS__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}_{{tenant}}.db"
    )
    monkeypatch.setenv("BMS_TENANT__DEV_TENANTS", '["demo", "acme"]')
    get_settings.cache_clear()
    settings = get_settings()
    settings.app.service = "platform"  # 启动期由服务包声明回写

    registry = EngineRegistry(EngineFactory(settings))
    try:
        handled = await ensure_development_schema(registry, settings)
        assert handled == ["platform", "tenant_demo", "tenant_acme"]
        assert "sys_module" in _tables(tmp_path / "bms_platform.db")
        assert "sys_data_scope" in _tables(tmp_path / "bms_platform_demo.db")
        assert "sys_data_scope" in _tables(tmp_path / "bms_platform_acme.db")
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1078)
async def test_auto_create_skips_chains_without_revisions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """无迁移脚本的服务链不建表（与真库迁移口径一致，避免开发库与真库漂移）。"""
    _point_to(tmp_path, monkeypatch, service="file")
    settings = get_settings()

    registry = EngineRegistry(EngineFactory(settings))
    try:
        assert await ensure_development_schema(registry, settings) == []
        assert registry.active_keys() == []
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1078)
async def test_auto_create_disabled_skips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """开关关（prod 口径）：不建表。"""
    platform, tenant = _point_to(tmp_path, monkeypatch)
    settings = get_settings()
    settings.database.auto_create = False

    registry = EngineRegistry(EngineFactory(settings))
    try:
        assert await ensure_development_schema(registry, settings) == []
        assert not platform.exists() and not tenant.exists()
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1078)
async def test_auto_create_skips_non_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """非 SQLite 方言：跳过建表（不建连，三库结构统一走 Alembic 迁移）。"""
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", "mysql+aiomysql://u:p@127.0.0.1:3306/bms_platform")
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", "mysql+aiomysql://u:p@127.0.0.1:3306/bms_platform_demo")
    monkeypatch.setenv("BMS_DATABASE__ARCHIVE__URL", "mysql+aiomysql://u:p@127.0.0.1:3306/bms_archive")
    get_settings.cache_clear()
    settings = get_settings()
    settings.app.service = "platform"

    registry = EngineRegistry(EngineFactory(settings))
    try:
        assert await ensure_development_schema(registry, settings) == []
        assert registry.active_keys() == [], "跳过后不应产生引擎"
    finally:
        await registry.aclose()


def _chain(datasource: str, *, tables: ConcurrentStableSet[str]) -> MigrationChain:
    """构造指定数据源段的迁移链替身（表集可控）。

    Args:
        datasource: 数据源段（`platform` / `tenant` / `archive` / 其它）。
        tables: 该链表集。

    Returns:
        MigrationChain: 链定义。
    """
    return MigrationChain(
        name=f"probe:{datasource}", service="platform", datasource=datasource, tables=tables, scope="探针"
    )


@pytest.mark.kiwi_id(1078)
def test_db_keys_for_unknown_datasource_returns_empty() -> None:
    """未知数据源段：取键为空列表（防御分支，不抛错）。"""
    settings = get_settings()
    assert db_keys_for(_chain("mystery", tables=ConcurrentStableSet()), settings) == []


@pytest.mark.kiwi_id(1078)
def test_db_keys_for_archive_and_tenant_branches() -> None:
    """归档链取单键；租户链逐 `dev_tenants` 派生（三分支对照）。"""
    settings = get_settings()
    assert db_keys_for(_chain(DATASOURCE_ARCHIVE, tables=ConcurrentStableSet()), settings) == ["archive"]
    settings.tenant.dev_tenants = ConcurrentStableList(["demo", "acme"])
    assert db_keys_for(_chain(DATASOURCE_TENANT, tables=ConcurrentStableSet()), settings) == [
        "tenant_demo",
        "tenant_acme",
    ]
    assert db_keys_for(_chain(DATASOURCE_PLATFORM, tables=ConcurrentStableSet()), settings) == ["platform"]


@pytest.mark.kiwi_id(1078)
async def test_auto_create_skips_chain_without_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """链有迁移脚本但表集为空：跳过建表（不产生引擎）。"""
    platform, tenant = _point_to(tmp_path, monkeypatch)
    settings = get_settings()

    monkeypatch.setattr(bootstrap_module, "service_chains", _empty_table_chains)
    monkeypatch.setattr(bootstrap_module, "has_revisions", _always_has_revisions)
    monkeypatch.setattr(bootstrap_module, "chain_metadata", _empty_metadata)

    registry = EngineRegistry(EngineFactory(settings))
    try:
        assert await ensure_development_schema(registry, settings) == []
        assert registry.active_keys() == []
    finally:
        await registry.aclose()
    assert not platform.exists() and not tenant.exists()


def _empty_table_chains(service: str) -> ConcurrentStableList[MigrationChain]:
    """服务链替身：单条表集为空的平台链。

    Args:
        service: 服务标识（忽略）。

    Returns:
        ConcurrentStableList[MigrationChain]: 单条空表链。
    """
    del service
    return ConcurrentStableList([_chain(DATASOURCE_PLATFORM, tables=ConcurrentStableSet())])


def _always_has_revisions(chain: MigrationChain) -> bool:
    """迁移脚本判定替身：恒有脚本。

    Args:
        chain: 链定义（忽略）。

    Returns:
        bool: 恒 True。
    """
    del chain
    return True


def _empty_metadata(chain: MigrationChain) -> MetaData:
    """链元数据替身：恒空表集。

    Args:
        chain: 链定义（忽略）。

    Returns:
        MetaData: 空元数据。
    """
    del chain
    return MetaData()
