"""启动期自动建表测试（Kiwi 1078 / 2177 / 2303）：开关 / 无脚本链照建 / 方言无关 / 幂等 / 跳过分支。"""

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import MetaData

import bms_core.db.bootstrap as bootstrap_module
from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.config import get_settings
from bms_core.db.bootstrap import (
    SchemaOutcome,
    apply_chain_schema,
    db_keys_for,
    default_schema_of,
    ensure_service_schema,
)
from bms_core.db.engine import EngineFactory
from bms_core.db.migration import (
    DATASOURCE_ARCHIVE,
    DATASOURCE_PLATFORM,
    DATASOURCE_TENANT,
    MigrationChain,
    resolve_chain,
)


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


@pytest.mark.kiwi_id(2303)
async def test_service_schema_auto_create_and_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """开关开 + 四库方言：按**本服务分链表集**建表（脚本清空后空链照建），重复执行幂等且不建骨架表。"""
    platform, tenant = _point_to(tmp_path, monkeypatch)
    settings = get_settings()
    assert settings.database.auto_create is True

    handled = await ensure_service_schema(settings, factory=EngineFactory(settings))
    assert handled == ["platform", "tenant_demo"]
    platform_tables = _tables(platform)
    assert {"sys_module", "sys_module_i18n", "sys_table_ownership", "sys_outbox"} <= platform_tables
    assert "sys_tenant" not in platform_tables, "租户注册归 tenant 服务，不进平台服务的平台链"
    tenant_tables = _tables(tenant)
    assert {"sys_data_scope", "sys_query_scheme", "sys_outbox"} <= tenant_tables
    assert "sys_task" not in tenant_tables, "骨架表（planned）不入链、不自动建表"

    before = (_tables(platform), _tables(tenant))
    assert await ensure_service_schema(settings, factory=EngineFactory(settings)) == handled
    assert (_tables(platform), _tables(tenant)) == before, "重复执行不新建表"


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

    handled = await ensure_service_schema(settings, factory=EngineFactory(settings))
    assert handled == ["platform", "tenant_demo", "tenant_acme"]
    assert "sys_module" in _tables(tmp_path / "bms_platform.db")
    assert "sys_data_scope" in _tables(tmp_path / "bms_platform_demo.db")
    assert "sys_data_scope" in _tables(tmp_path / "bms_platform_acme.db")


@pytest.mark.kiwi_id(2303)
async def test_auto_create_builds_chains_without_scripts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """去脚本门槛（06_05）：仓库脚本清空后无迁移脚本的服务链照建当前表集（file 服务平台链三张基础设施表）。"""
    platform, tenant = _point_to(tmp_path, monkeypatch, service="file")
    settings = get_settings()

    handled = await ensure_service_schema(settings, factory=EngineFactory(settings))
    assert handled == ["platform", "tenant_demo"]
    assert {"sys_outbox", "sys_event_consumed", "sys_event_dead_letter"} <= _tables(platform)
    assert platform.exists() and tenant.exists()


@pytest.mark.kiwi_id(2303)
async def test_auto_create_disabled_skips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """开关关（生产口径）：不建表、不建连。"""
    platform, tenant = _point_to(tmp_path, monkeypatch)
    settings = get_settings()
    settings.database.auto_create = False

    assert await ensure_service_schema(settings, factory=EngineFactory(settings)) == []
    assert not platform.exists() and not tenant.exists()


@pytest.mark.kiwi_id(2303)
async def test_auto_create_covers_non_sqlite_dialect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """方言无关（去 SQLite 限定）：非 SQLite 目标同样进入建表路径（建连经替身，避免真库依赖）。"""
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", "mysql+aiomysql://u:p@127.0.0.1:3306/bms_platform")
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", "mysql+aiomysql://u:p@127.0.0.1:3306/bms_platform_demo")
    get_settings.cache_clear()
    settings = get_settings()
    settings.app.service = "platform"
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    async def _fake_async(url: str, metadata: MetaData) -> tuple[int, int]:
        """替身：记录目标并返回（新建, 已存在）统计（不建连）。"""
        calls.add(url)
        return len(metadata.tables), 0

    monkeypatch.setattr(bootstrap_module, "_apply_async", _fake_async)
    handled = await ensure_service_schema(settings, factory=EngineFactory(settings))
    assert handled == ["platform", "tenant_demo"]
    assert len(calls) == 2, "非 SQLite 目标不再被跳过"


@pytest.mark.kiwi_id(2303)
async def test_auto_create_skips_unregistered_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """运行服务未登记（脚手架工程尚未登记）：派生链失败即跳过，不阻断启动、不建表。"""
    platform, tenant = _point_to(tmp_path, monkeypatch, service="ghost")
    settings = get_settings()

    assert await ensure_service_schema(settings, factory=EngineFactory(settings)) == []
    assert not platform.exists() and not tenant.exists()


@pytest.mark.kiwi_id(2303)
def test_default_schema_of_only_for_sync_dialect() -> None:
    """模式名取法：达梦取连接串 `database` 段；其余方言为空（不把库名 / 文件路径误当模式）。"""
    assert default_schema_of("dm+dmPython://SYSDBA:p@127.0.0.1:5236/BMS_MIGRCHECK") == "BMS_MIGRCHECK"
    assert default_schema_of("dm+dmPython://SYSDBA:p@127.0.0.1:5236") == ""
    assert default_schema_of("sqlite+aiosqlite:///./demo.db") == ""
    assert default_schema_of("mysql+aiomysql://u:p@127.0.0.1:3306/bms_platform") == ""


@pytest.mark.kiwi_id(2303)
async def test_apply_chain_schema_sync_driver_and_idempotent(tmp_path: Path) -> None:
    """同步驱动路径：同步连接串同样幂等建表（显式模式名对非达梦为空操作）。"""
    url = f"sqlite:///{tmp_path / 'sync.db'}"
    chain = resolve_chain("platform:platform")

    first = await apply_chain_schema(chain, url, target="sync", schema="IGNORED")
    assert first.created == first.total > 0
    assert first.existing == 0

    second = await apply_chain_schema(chain, url, target="sync", schema="IGNORED")
    assert second.created == 0
    assert second.existing == second.total


@pytest.mark.kiwi_id(2303)
async def test_apply_chain_schema_creates_only_missing_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """建表只建**自算的缺失表**：不依赖方言 `has_table`（达梦不认会话模式）也不重复 CREATE。"""
    from sqlalchemy.dialects.sqlite.base import SQLiteDialect

    url = f"sqlite:///{tmp_path / 'blind.db'}"
    chain = resolve_chain("platform:platform")
    first = await apply_chain_schema(chain, url, target="blind")
    assert first.created == first.total > 0

    # 模拟达梦方言 `has_table` 不认当前模式（03_DM8 实测）：恒定 False ⇒ 旧实现会对已存在表重复 CREATE
    monkeypatch.setattr(SQLiteDialect, "has_table", lambda self, connection, table_name, schema=None, **kwargs: False)
    second = await apply_chain_schema(chain, url, target="blind")

    assert second.created == 0
    assert second.existing == second.total


@pytest.mark.kiwi_id(2303)
async def test_apply_chain_schema_skips_empty_table_set(tmp_path: Path) -> None:
    """表集空即跳过、不建连（归档链空链）：目标文件不产生。"""
    target = tmp_path / "none.db"
    outcome = await apply_chain_schema(resolve_chain("platform:archive"), f"sqlite+aiosqlite:///{target}")
    assert outcome == SchemaOutcome(target="platform:archive", total=0, created=0, existing=0)
    assert not target.exists()


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


@pytest.mark.kiwi_id(2303)
async def test_auto_create_skips_chain_without_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """链表集为空：跳过建表（不建连、不产生库文件）。"""
    platform, tenant = _point_to(tmp_path, monkeypatch)
    settings = get_settings()

    monkeypatch.setattr(bootstrap_module, "service_chains", _empty_table_chains)
    monkeypatch.setattr(bootstrap_module, "chain_metadata", _empty_metadata)

    assert await ensure_service_schema(settings, factory=EngineFactory(settings)) == []
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


def _empty_metadata(chain: MigrationChain) -> MetaData:
    """链元数据替身：恒空表集。

    Args:
        chain: 链定义（忽略）。

    Returns:
        MetaData: 空元数据。
    """
    del chain
    return MetaData()
