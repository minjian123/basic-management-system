"""启动期自动建表：按「部署单元 × 数据源」建表集幂等建表（方言无关、不依赖迁移脚本）。

- **建表集口径（07C `03_02`）**：单元在某库类别的表集 = **所含各业务域表集的并集 + 基础设施表**
  （`services/table_registry.py::unit_tables`）。域表集由归属登记按域派生，基础设施表（发件箱三表）
  不进任何域清单、每库一份。任一拓扑下「库结构 = 所含域表集并集」由本函数保证。
- **开关**：`[database].auto_create`（默认 `true`）；语义为**启动期建表总开关**——开发 / 测试默认开，
  生产建议置 `false` 并改经 ops 显式建表入口（`ops.init_schema`：部署链上先建表、后起服务）；
- **方言**：SQLite / MySQL / PostgreSQL / 达梦一律生效（DDL 由 SQLAlchemy 按方言生成，达梦走既有方言
  补丁），建表前把会话切到连接串 `database` 段指定的模式（达梦；其余方言无此概念）；
- **单元**：`[app].unit` 可选，缺省回落 `[app].service`；单元所含域由域布局声明按承载服务反推
  （`migration.py::unit_domains`），不在此另登记；
- **取键**：平台库 → 本单元平台服务库（相对键 `platform`）；归档库 → `archive`；租户库 → 本单元 ×
  `[tenant].dev_tenants` 逐租户相对键（`tenant_{code}`），空 `url_template` 时诸键解析到同一
  `[database.tenants].url`，经 URL 去重后与既有单库行为一致；
- **幂等**：`create_all(checkfirst=True)`，重复启动不报错、不重建、**只补不建改**（不做 ALTER；需干净库时
  删库重建，见《数据库开发规范》「迁移与建表口径」）。
"""

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import Connection, MetaData, create_engine, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseValueObject
from bms_core.db.engine import PLATFORM_DB_KEY, EngineFactory
from bms_core.db.keys import ARCHIVE_DB_KEY, build_tenant_db_key
from bms_core.db.migration import (
    DATASOURCE_ARCHIVE,
    DATASOURCE_PLATFORM,
    DATASOURCE_TENANT,
    apply_session_schema,
    import_models,
    unit_domains,
    unit_key,
)
from bms_core.db.sync import is_sync_only_url
from bms_core.models.base import Base
from bms_core.services.table_registry import series_tables, unit_tables

logger = get_logger("bms_core.db.bootstrap")

_ASYNC_DRIVERS = frozenset({"aiosqlite", "aiomysql", "asyncmy", "asyncpg"})
"""异步驱动名集合（其余驱动一律走同步建表路径；达梦等同步方言亦经此）。"""


def db_keys_for(datasource: str, settings: Settings) -> ConcurrentStableList[str]:
    """取该库类别用于取引擎的数据源键集合（单元化：平台库本单元、租户库逐开发租户）。

    Args:
        datasource: 数据源段（`platform` / `tenant` / `archive`）。
        settings: 应用配置（租户库取 `[tenant].dev_tenants`）。

    Returns:
        ConcurrentStableList[str]: 数据源键列表（保序；可能为空，如无开发租户时）。
    """
    if datasource == DATASOURCE_PLATFORM:
        return ConcurrentStableList([PLATFORM_DB_KEY])
    if datasource == DATASOURCE_TENANT:
        return ConcurrentStableList(build_tenant_db_key(code) for code in settings.tenant.dev_tenants)
    if datasource == DATASOURCE_ARCHIVE:
        return ConcurrentStableList([ARCHIVE_DB_KEY])
    return ConcurrentStableList()


@dataclass(frozen=True)
class SchemaOutcome(BaseValueObject):
    """单库建表结果（表集大小与新建 / 已存在分布）。"""

    target: str
    """目标标签（库键 / 运维通道自定名）。"""

    total: int
    """该库建表集大小（所含域表集并集 + 基础设施表，且已有模型）。"""

    created: int
    """本次新建表数。"""

    existing: int
    """建表前已存在表数。"""


def default_schema_of(url: str) -> str:
    """取连接串默认模式名（达梦以 `database` 段承载模式名；其余方言返回空串）。

    Args:
        url: 数据库连接串。

    Returns:
        str: 达梦目标模式名（其余方言空串）。
    """
    if not is_sync_only_url(url):
        return ""
    return make_url(url).database or ""


def _is_async_url(url: str) -> bool:
    """连接串是否异步驱动（异步路径可直接 `create_async_engine`；其余走同步路径）。

    Args:
        url: 数据库连接串。

    Returns:
        bool: 异步驱动 True。
    """
    return make_url(url).get_driver_name() in _ASYNC_DRIVERS


def _existing_tables(connection: Connection, metadata: MetaData) -> ConcurrentStableSet[str]:
    """取目标库中该建表集的已存在表名（建表前统计用）。

    Args:
        connection: 同步连接（异步路径经 `run_sync` 传入）。
        metadata: 建表集元数据。

    Returns:
        ConcurrentStableSet[str]: 已存在的表名集合。
    """
    present = set(inspect(connection).get_table_names())
    return ConcurrentStableSet(name for name in metadata.tables if name in present)


async def _apply_async(url: str, metadata: MetaData) -> tuple[int, int]:
    """异步驱动建表（一次性引擎；返回（新建数, 已存在数））。

    Args:
        url: 目标连接串（禁止写入日志）。
        metadata: 建表集元数据。

    Returns:
        tuple[int, int]: （新建表数, 已存在表数）。
    """
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            existing = await connection.run_sync(_existing_tables, metadata)
            missing = [table for name, table in metadata.tables.items() if name not in existing]
            if missing:
                await connection.run_sync(metadata.create_all, tables=missing, checkfirst=False)
    finally:
        await engine.dispose()
    return len(metadata.tables) - len(existing), len(existing)


def _apply_sync(url: str, metadata: MetaData, schema: str) -> tuple[int, int]:
    """同步驱动建表（达梦等；建表前切换会话模式；返回（新建数, 已存在数））。

    Args:
        url: 目标连接串（禁止写入日志）。
        metadata: 建表集元数据。
        schema: 目标模式名（空串表示不切换）。

    Returns:
        tuple[int, int]: （新建表数, 已存在表数）。
    """
    engine = create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            apply_session_schema(connection, schema)
            existing = _existing_tables(connection, metadata)
            # 只建**自算的缺失表**：不依赖方言 `create_all(checkfirst=True)` 的 `has_table`——
            # 达梦方言不认会话 `SET SCHEMA` 后的当前模式（03_DM8 实测），会对已存在表重复 CREATE。
            missing = [table for name, table in metadata.tables.items() if name not in existing]
            if missing:
                metadata.create_all(connection, tables=missing, checkfirst=False)
    finally:
        engine.dispose()
    return len(metadata.tables) - len(existing), len(existing)


def domains_metadata(domains: Iterable[str], datasource: str, *, include_infrastructure: bool = True) -> MetaData:
    """取指定业务域集合在某库类别的建表集元数据（部署单元建表与域搬迁共用）。

    **两处调用口径不同，靠 `include_infrastructure` 分开**：

    - 建表（启动期 / `ops.init_schema` / 迁移工具 P2）：含基础设施表——它们每库一份，
      新库也需要有；
    - 数据搬迁（`04_02` P3）：**不含**基础设施表——发件箱等表属于「本库自己的事件」，
      不随业务域搬迁，搬过去会把源库的待发事件复制到目标库导致重复投递。

    Args:
        domains: 业务域标识集合。
        datasource: 数据源段。
        include_infrastructure: 是否并入基础设施表。

    Returns:
        MetaData: 元数据子集（与 `Base.metadata` 同命名约定）。
    """
    resolved = ConcurrentStableList(domains)
    for domain in resolved:
        import_models(domain)
    tables = _tables_of(resolved, datasource, include_infrastructure=include_infrastructure)
    metadata = MetaData(naming_convention=Base.metadata.naming_convention)
    for name in sorted(tables & set(Base.metadata.tables)):
        Base.metadata.tables[name].to_metadata(metadata)
    return metadata


def _tables_of(
    domains: ConcurrentStableList[str], datasource: str, *, include_infrastructure: bool
) -> ConcurrentStableSet[str]:
    """取域集合在某库类别的表集（含 / 不含基础设施表）。

    Args:
        domains: 业务域标识集合。
        datasource: 数据源段。
        include_infrastructure: 是否并入基础设施表。

    Returns:
        ConcurrentStableSet[str]: 表名集合（插入序）。
    """
    if include_infrastructure:
        return unit_tables(domains, datasource)
    tables: ConcurrentStableSet[str] = ConcurrentStableSet()
    for domain in domains:
        tables.update(series_tables(domain, datasource))
    return tables


def unit_metadata(unit: str, datasource: str) -> MetaData:
    """取部署单元在某库类别的建表集元数据（各域表集并集 + 基础设施表 ∩ 已有模型）。

    Args:
        unit: 部署单元标识。
        datasource: 数据源段。

    Returns:
        MetaData: 元数据子集（迁移目标 / 自动建表共用）。
    """
    return domains_metadata(unit_domains(unit), datasource)


async def apply_domains_schema(
    domains: Iterable[str], datasource: str, url: str, *, target: str = "", schema: str = ""
) -> SchemaOutcome:
    """对目标连接串幂等建指定域集合在该库类别的建表集（方言无关；表集空即跳过、不建连）。

    与 `apply_unit_schema` 同源（后者是「域集由单元反推」的特例）：迁移工具 P2 的目标单元
    在静态域布局里可能还不是这些域的承载服务（拆分新单元），故必须能按**显式域清单**建表。

    Args:
        domains: 业务域标识集合。
        datasource: 数据源段。
        url: 目标连接串（含密码；禁止写入日志）。
        target: 目标标签（日志与统计用；缺省取域名列表）。
        schema: 达梦目标模式名（空串表示取连接串 `database` 段）。

    Returns:
        SchemaOutcome: 建表结果（表集空返回全 0）。
    """
    resolved = ConcurrentStableList(domains)
    label = target or f"{','.join(resolved)}:{datasource}"
    metadata = domains_metadata(resolved, datasource)
    if not metadata.tables:
        return SchemaOutcome(target=label, total=0, created=0, existing=0)
    if _is_async_url(url):
        created, existing = await _apply_async(url, metadata)
    else:
        created, existing = await asyncio.to_thread(_apply_sync, url, metadata, schema or default_schema_of(url))
    logger.info(
        "schema_auto_create",
        target=label,
        domains=list(resolved),
        tables=len(metadata.tables),
        created=created,
        existing=existing,
    )
    return SchemaOutcome(target=label, total=len(metadata.tables), created=created, existing=existing)


async def apply_unit_schema(
    unit: str, datasource: str, url: str, *, target: str = "", schema: str = ""
) -> SchemaOutcome:
    """对目标连接串幂等建该单元在该库类别的建表集（方言无关；表集空即跳过、不建连）。

    启动期与 ops 显式建表入口（`ops.init_schema` / `ops.test_db` 的 `migrate` 段）共用本函数，
    表集一律经 `unit_metadata` 派生（单一来源）。

    Args:
        unit: 部署单元标识。
        datasource: 数据源段。
        url: 目标连接串（含密码；禁止写入日志）。
        target: 目标标签（日志与统计用；缺省取 `{unit}:{datasource}`）。
        schema: 达梦目标模式名（空串表示取连接串 `database` 段）。

    Returns:
        SchemaOutcome: 建表结果（表集空返回全 0）。
    """
    domains = unit_domains(unit)
    return await apply_domains_schema(domains, datasource, url, target=target or f"{unit}:{datasource}", schema=schema)


async def ensure_unit_schema(settings: Settings, *, factory: EngineFactory | None = None) -> ConcurrentStableList[str]:
    """启动期按本单元三库类别建表（开关关 / 单元未登记域 / 表集空 / 同 URL 重复 跳过）。

    Args:
        settings: 应用配置。
        factory: 引擎工厂（缺省新建；用于解析各库连接串）。

    Returns:
        ConcurrentStableList[str]: 已建表的数据源键列表（未执行 / 全部跳过返回空列表）。
    """
    if not settings.database.auto_create:
        logger.info("schema_auto_create_skipped", reason="auto_create=false")
        return ConcurrentStableList()
    unit = unit_key(settings)
    if not unit:
        logger.warning("schema_auto_create_skipped", reason="unit_not_declared")
        return ConcurrentStableList()
    try:
        domains = unit_domains(unit)
    except ConfigError as exc:
        logger.warning("schema_auto_create_skipped", reason="unit_not_registered", detail=str(exc))
        return ConcurrentStableList()
    if not domains:
        # 运行服务未在域布局登记（脚手架生成 / 产品仓自建布局）：无法派生域集，跳过（不阻断启动）
        logger.warning("schema_auto_create_skipped", reason="unit_has_no_domain", unit=unit)
        return ConcurrentStableList()
    engine_factory = factory or EngineFactory(settings)
    handled: ConcurrentStableList[str] = ConcurrentStableList()
    seen_urls: ConcurrentStableSet[str] = ConcurrentStableSet()
    for datasource in (DATASOURCE_PLATFORM, DATASOURCE_TENANT, DATASOURCE_ARCHIVE):
        for db_key in db_keys_for(datasource, settings):
            url = engine_factory.resolved_url(db_key)
            if url in seen_urls:
                continue
            seen_urls.add(url)
            outcome = await apply_unit_schema(unit, datasource, url, target=db_key)
            if outcome.total:
                handled.add(db_key)
    return handled
