"""开发库自动建表：SQLite 环境按迁移链的表集建表（不依赖迁移脚本执行）。

- **开关**：`[database].auto_create`（默认 `true`；prod 置 `false`）；
- **方言**：仅当目标连接串方言为 SQLite 时生效（MySQL / PostgreSQL / 达梦一律走 Alembic 迁移）；
- **链集（06_02 分链）**：只处理**本服务**的链（`service_chains(settings.app.service)`）且**有迁移
  脚本**的链——与真库迁移口径一致（「无脚本的链」两边都跳过，不产生「开发库有、真库没有」的漂移）；
- **表集**：`chain_metadata(chain)` = 归属登记派生表集（`chain_tables`，仅 `status = enabled`）∩
  已有模型——与服务迁移**同一派生点**；
- **取键**：平台链 → 本服务平台服务库（相对键 `platform`）；归档链 → `archive`；租户链 → 本服务 ×
  `[tenant].dev_tenants` 逐租户相对键（`tenant_{code}`），空 `url_template` 时诸键解析到同一
  `[database.tenants].url`，经 URL 去重后与既有单库行为一致；
- **幂等**：`create_all(checkfirst=True)`，重复启动不报错、不重建、**只补不删**（需干净库时删库文件重建）。
"""

from sqlalchemy.engine import make_url

from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.logging import get_logger
from bms_core.db.engine import PLATFORM_DB_KEY, EngineFactory
from bms_core.db.keys import ARCHIVE_DB_KEY, build_tenant_db_key
from bms_core.db.migration import (
    DATASOURCE_ARCHIVE,
    DATASOURCE_PLATFORM,
    DATASOURCE_TENANT,
    MigrationChain,
    chain_metadata,
    config_section,
    has_revisions,
    service_chains,
)
from bms_core.db.registry import EngineRegistry

logger = get_logger("bms_core.db.bootstrap")


def db_keys_for(chain: MigrationChain, settings: Settings) -> list[str]:
    """取该链用于取引擎的数据源键集合（服务化：平台链本服务、租户链逐开发租户）。

    Args:
        chain: 链定义（自带服务与数据源段）。
        settings: 应用配置（租户链取 `[tenant].dev_tenants`）。

    Returns:
        list[str]: 数据源键列表（保序；可能为空，如无开发租户时）。
    """
    if chain.datasource == DATASOURCE_PLATFORM:
        return [PLATFORM_DB_KEY]
    if chain.datasource == DATASOURCE_TENANT:
        return [build_tenant_db_key(code) for code in settings.tenant.dev_tenants]
    if chain.datasource == DATASOURCE_ARCHIVE:
        return [ARCHIVE_DB_KEY]
    return []


def _is_sqlite(url: str) -> bool:
    """连接串是否 SQLite 方言。

    Args:
        url: 数据库连接串。

    Returns:
        bool: SQLite True。
    """
    return make_url(url).get_backend_name() == "sqlite"


async def ensure_development_schema(
    registry: EngineRegistry,
    settings: Settings,
    *,
    factory: EngineFactory | None = None,
) -> list[str]:
    """按链表集为 SQLite 目标建表（开关关 / 非 SQLite / 无脚本链 / 空表集跳过）。

    Args:
        registry: 引擎注册表。
        settings: 应用配置。
        factory: 引擎工厂（缺省新建；用于读取各链目标连接串）。

    Returns:
        list[str]: 已建表的数据源键列表（未执行返回空列表）。
    """
    if not settings.database.auto_create:
        logger.info("sqlite_auto_create_skipped", reason="auto_create=false")
        return []
    engine_factory = factory or EngineFactory(settings)
    try:
        chains = service_chains(settings.app.service)
    except ConfigError as exc:
        # 运行服务未在服务目录登记（脚手架生成的工程尚未登记）：无法派生链，跳过（不阻断启动）
        logger.warning("sqlite_auto_create_skipped", reason="service_not_registered", detail=str(exc))
        return []
    handled: list[str] = []
    seen_urls: set[str] = set()
    for chain in chains:
        if not has_revisions(chain):
            continue
        metadata = chain_metadata(chain)
        if not metadata.tables:
            continue
        for db_key in db_keys_for(chain, settings):
            url = engine_factory.resolve_url(db_key)
            if not _is_sqlite(url) or url in seen_urls:
                continue
            seen_urls.add(url)
            engine = await registry.get(db_key)
            async with engine.begin() as connection:
                await connection.run_sync(metadata.create_all, checkfirst=True)
            handled.append(db_key)
            logger.info(
                "sqlite_auto_create",
                target=db_key,
                config_section=config_section(chain),
                tables=len(metadata.tables),
            )
    return handled
