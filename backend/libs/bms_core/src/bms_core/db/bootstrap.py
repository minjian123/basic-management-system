"""开发库自动建表：SQLite 环境按迁移链表集建表（不依赖迁移脚本）。

- **开关**：`[database].auto_create`（默认 `true`；prod 置 `false`）；
- **方言**：仅当目标连接串方言为 SQLite 时生效（MySQL / PostgreSQL / 达梦一律走 Alembic 迁移）；
- **表集**：按链元数据子集（`app/db/migration.py` 链注册）建表——与迁移脚本同口径，
  骨架表（`sys_task` 等）不建，避免开发库与真库结构漂移；
- **幂等**：`create_all(checkfirst=True)`，重复启动不报错、不重建。
"""

from sqlalchemy.engine import make_url

from bms_core.core.config import Settings
from bms_core.core.logging import get_logger
from bms_core.db.engine import PLATFORM_DB_KEY, EngineFactory
from bms_core.db.migration import MIGRATION_CHAINS, MigrationChain, chain_metadata, config_section
from bms_core.db.registry import EngineRegistry

DEFAULT_TENANT_DB_KEY = "tenants"
"""缺省租户库数据源键（不触发 `url_template` 解析，取 `database.tenants.url` 单库）。"""

logger = get_logger("bms_core.db.bootstrap")


def db_key_for(chain: MigrationChain) -> str:
    """取该链用于取引擎的数据源键。

    Args:
        chain: 链定义。

    Returns:
        str: 数据源键（平台链 `platform`；租户链缺省租户库键；归档链 `archive`）。
    """
    if chain.name == "platform":
        return PLATFORM_DB_KEY
    if chain.name == "tenant":
        return DEFAULT_TENANT_DB_KEY
    return chain.name


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
    """按链表集为 SQLite 目标建表（开关关 / 非 SQLite / 无表链跳过）。

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
    handled: list[str] = []
    seen_urls: set[str] = set()
    for chain in MIGRATION_CHAINS.values():
        if not chain.tables:
            continue
        db_key = db_key_for(chain)
        url = engine_factory.resolve_url(db_key)
        if not _is_sqlite(url) or url in seen_urls:
            continue
        seen_urls.add(url)
        metadata = chain_metadata(chain)
        engine = await registry.get(db_key)
        async with engine.begin() as connection:
            await connection.run_sync(metadata.create_all, checkfirst=True)
        handled.append(db_key)
        logger.info(
            "sqlite_auto_create",
            target=db_key_for(chain),
            config_section=config_section(chain),
            tables=len(metadata.tables),
        )
    return handled
