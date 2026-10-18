"""启动期自动建表：按「服务 × 数据源」表集幂等建表（方言无关、不依赖迁移脚本）。

- **开关**：`[database].auto_create`（默认 `true`）；语义为**启动期建表总开关**——开发 / 测试默认开，
  生产建议置 `false` 并改经 ops 显式建表入口（`ops.init_schema`：部署链上先建表、后起服务）；
- **方言**：SQLite / MySQL / PostgreSQL / 达梦一律生效（去方言限定；DDL 由 SQLAlchemy 按方言生成，
  达梦走既有方言补丁），建表前把会话切到连接串 `database` 段指定的模式（达梦；其余方言无此概念）；
- **链集（06_02 分链）**：只处理**本服务**的链（`service_chains(settings.app.service)`），且**不要求
  该链有迁移脚本**（06_05：历史迁移脚本已清空，新库 / 新服务首次接入无需先造脚本）；
- **表集**：`chain_metadata(chain)` = 归属登记派生表集（`chain_tables`，仅 `status = enabled`）∩
  已有模型——与 ops 显式建表入口（`ops.init_schema`）**同一派生点**，避免两处表集漂移；
- **取键**：平台链 → 本服务平台服务库（相对键 `platform`）；归档链 → `archive`；租户链 → 本服务 ×
  `[tenant].dev_tenants` 逐租户相对键（`tenant_{code}`），空 `url_template` 时诸键解析到同一
  `[database.tenants].url`，经 URL 去重后与既有单库行为一致；
- **幂等**：`create_all(checkfirst=True)`，重复启动不报错、不重建、**只补不建改**（不做 ALTER；需干净库时
  删库重建，见《数据库开发规范》「迁移与建表口径」）。
"""

import asyncio
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
    MigrationChain,
    apply_session_schema,
    chain_metadata,
    config_section,
    service_chains,
)
from bms_core.db.sync import is_sync_only_url

logger = get_logger("bms_core.db.bootstrap")

_ASYNC_DRIVERS = frozenset({"aiosqlite", "aiomysql", "asyncmy", "asyncpg"})
"""异步驱动名集合（其余驱动一律走同步建表路径；达梦等同步方言亦经此）。"""


def db_keys_for(chain: MigrationChain, settings: Settings) -> ConcurrentStableList[str]:
    """取该链用于取引擎的数据源键集合（服务化：平台链本服务、租户链逐开发租户）。

    Args:
        chain: 链定义（自带服务与数据源段）。
        settings: 应用配置（租户链取 `[tenant].dev_tenants`）。

    Returns:
        ConcurrentStableList[str]: 数据源键列表（保序；可能为空，如无开发租户时）。
    """
    if chain.datasource == DATASOURCE_PLATFORM:
        return ConcurrentStableList([PLATFORM_DB_KEY])
    if chain.datasource == DATASOURCE_TENANT:
        return ConcurrentStableList(build_tenant_db_key(code) for code in settings.tenant.dev_tenants)
    if chain.datasource == DATASOURCE_ARCHIVE:
        return ConcurrentStableList([ARCHIVE_DB_KEY])
    return ConcurrentStableList()


@dataclass(frozen=True)
class SchemaOutcome(BaseValueObject):
    """单库建表结果（表集大小与新建 / 已存在分布）。"""

    target: str
    """目标标签（库键 / 运维通道自定名）。"""

    total: int
    """该链表集大小（归属登记 `enabled` 且已有模型）。"""

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
    """取目标库中该链表集的已存在表名（建表前统计用）。

    Args:
        connection: 同步连接（异步路径经 `run_sync` 传入）。
        metadata: 链表集元数据。

    Returns:
        ConcurrentStableSet[str]: 已存在的表名集合。
    """
    present = set(inspect(connection).get_table_names())
    return ConcurrentStableSet(name for name in metadata.tables if name in present)


async def _apply_async(url: str, metadata: MetaData) -> tuple[int, int]:
    """异步驱动建表（一次性引擎；返回（新建数, 已存在数））。

    Args:
        url: 目标连接串（禁止写入日志）。
        metadata: 链表集元数据。

    Returns:
        tuple[int, int]: （新建表数, 已存在表数）。
    """
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            existing = await connection.run_sync(_existing_tables, metadata)
            await connection.run_sync(metadata.create_all, checkfirst=True)
    finally:
        await engine.dispose()
    return len(metadata.tables) - len(existing), len(existing)


def _apply_sync(url: str, metadata: MetaData, schema: str) -> tuple[int, int]:
    """同步驱动建表（达梦等；建表前切换会话模式；返回（新建数, 已存在数））。

    Args:
        url: 目标连接串（禁止写入日志）。
        metadata: 链表集元数据。
        schema: 目标模式名（空串表示不切换）。

    Returns:
        tuple[int, int]: （新建表数, 已存在表数）。
    """
    engine = create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            apply_session_schema(connection, schema)
            existing = _existing_tables(connection, metadata)
            metadata.create_all(connection, checkfirst=True)
    finally:
        engine.dispose()
    return len(metadata.tables) - len(existing), len(existing)


async def apply_chain_schema(chain: MigrationChain, url: str, *, target: str = "", schema: str = "") -> SchemaOutcome:
    """对目标连接串幂等建该链的表集（方言无关；表集空即跳过、不建连）。

    启动期与 ops 显式建表入口（`ops.init_schema` / `ops.test_db` 的 `migrate` 段）共用本函数，
    表集一律经 `chain_metadata(chain)` 派生（单一来源）。

    Args:
        chain: 链定义。
        url: 目标连接串（含密码；禁止写入日志）。
        target: 目标标签（日志与统计用；缺省取链名）。
        schema: 达梦目标模式名（空串表示取连接串 `database` 段）。

    Returns:
        SchemaOutcome: 建表结果（表集空返回全 0）。
    """
    label = target or chain.name
    metadata = chain_metadata(chain)
    if not metadata.tables:
        return SchemaOutcome(target=label, total=0, created=0, existing=0)
    if _is_async_url(url):
        created, existing = await _apply_async(url, metadata)
    else:
        created, existing = await asyncio.to_thread(_apply_sync, url, metadata, schema or default_schema_of(url))
    logger.info(
        "schema_auto_create",
        target=label,
        config_section=config_section(chain),
        tables=len(metadata.tables),
        created=created,
        existing=existing,
    )
    return SchemaOutcome(target=label, total=len(metadata.tables), created=created, existing=existing)


async def ensure_service_schema(
    settings: Settings, *, factory: EngineFactory | None = None
) -> ConcurrentStableList[str]:
    """启动期按本服务三链的表集建表（开关关 / 服务未登记 / 表集空 / 同 URL 重复 跳过）。

    Args:
        settings: 应用配置。
        factory: 引擎工厂（缺省新建；用于解析各库连接串）。

    Returns:
        ConcurrentStableList[str]: 已建表的数据源键列表（未执行 / 全部跳过返回空列表）。
    """
    if not settings.database.auto_create:
        logger.info("schema_auto_create_skipped", reason="auto_create=false")
        return ConcurrentStableList()
    engine_factory = factory or EngineFactory(settings)
    try:
        chains = service_chains(settings.app.service)
    except ConfigError as exc:
        # 运行服务未在服务目录登记（脚手架生成的工程尚未登记）：无法派生链，跳过（不阻断启动）
        logger.warning("schema_auto_create_skipped", reason="service_not_registered", detail=str(exc))
        return ConcurrentStableList()
    handled: ConcurrentStableList[str] = ConcurrentStableList()
    seen_urls: ConcurrentStableSet[str] = ConcurrentStableSet()
    for chain in chains:
        for db_key in db_keys_for(chain, settings):
            url = engine_factory.resolved_url(db_key)
            if url in seen_urls:
                continue
            seen_urls.add(url)
            outcome = await apply_chain_schema(chain, url, target=db_key)
            if outcome.total:
                handled.add(db_key)
    return handled
