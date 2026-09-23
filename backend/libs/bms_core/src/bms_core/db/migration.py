"""数据源迁移链注册：数据源 → 版本目录 / 表集 / 分支标签 / 连接串取法。

- 三条链：`platform`（平台库）/ `tenant`（租户库）/ `archive`（归档库），脚本按链分目录
  （`alembic/versions/<链名>/`），`branch_labels` 取链名；同一套脚本在四库执行（禁方言 SQL）。
- 链定义是「Alembic 元数据子集 + 版本目录 + 自动建表表集 + 连接串取法」的**唯一来源**：
  `alembic/env.py` 与开发库自动建表（`app/db/bootstrap.py`）都从此取，避免三处漂移。
- 表集只登记**已有迁移脚本**的表：骨架表（`sys_task` / `sys_notification` / `sys_icon` /
  `ai_chat_log` 等）由所属阶段自带迁移，既不进链也不自动建表。
- 表结构以《数据库设计》数据表文件为唯一事实源。
"""

import asyncio
import importlib
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, MetaData, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DatabaseError, OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from bms_core.core.base import BaseObject
from bms_core.core.config import Settings, get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.models.base import Base


def _find_backend_root() -> Path:
    """定位后端工程根（`backend/`）：自本文件向上取首个含 `alembic.ini` 的目录。

    工作区形态下迁移脚本落点由库内相对定位改为向上搜根，避免硬编码层级随布局漂移。

    Returns:
        Path: 后端工程根目录。

    Raises:
        ConfigError: 向上未找到含 `alembic.ini` 的目录（工程布局异常）。
    """
    for parent in Path(__file__).resolve().parents:
        if (parent / "alembic.ini").is_file():
            return parent
    raise ConfigError("未找到 backend/ 工程根（向上无含 alembic.ini 的目录）")


BACKEND_ROOT = _find_backend_root()
"""后端工程根（`backend/`）：含 `alembic.ini` 的最近祖先目录。"""

VERSIONS_ROOT = BACKEND_ROOT / "alembic" / "versions"
"""迁移脚本根目录（按链分子目录）。"""

PLATFORM_TABLES: frozenset[str] = frozenset(
    {
        "sys_tenant",
        "sys_module",
        "sys_module_i18n",
        "sys_outbox",
        "sys_event_consumed",
        "sys_event_dead_letter",
    }
)
"""平台链表集（《数据库设计 · 总览》「平台库表」；发件箱三表随 05_03 双链落地）。"""

TENANT_TABLES: frozenset[str] = frozenset(
    {
        "sys_dict_type",
        "sys_dict_item",
        "sys_dict_type_i18n",
        "sys_dict_item_i18n",
        "sys_dict_attr",
        "sys_dict_attr_i18n",
        "sys_query_scheme",
        "sys_outbox",
        "sys_event_consumed",
        "sys_event_dead_letter",
    }
)
"""租户链表集（字典六表 + 查询方案表 + 发件箱三表）。"""

ARCHIVE_TABLES: frozenset[str] = frozenset()
"""归档链表集（空：归档表随归档阶段落地）。"""

_DM = "dm"
"""达梦方言名（无异步驱动，走同步引擎）。"""

_MODEL_MODULES: tuple[str, ...] = (
    "bms_core.models.platform",
    "bms_core.models.ownership",
    "bms_core.models.outbox",
    "bms_core.dict.models",
    "bms_core.listing.models",
    "bms_tenant.models.tenant",
)
"""模型模块清单（导入以注册元数据）。

仅登记**进入迁移链表集**的库内模型；平台业务骨架表（`sys_task` / `sys_notification` /
`sys_icon` / `ai_chat_log`）与演示模型归平台服务，未进任何链表集，不在此登记。
"""


@dataclass(frozen=True)
class MigrationChain(BaseObject):
    """迁移链定义（数据源 → 版本目录 / 表集 / 分支标签）。"""

    name: str
    """链名（= 数据源名，取值 `platform` / `tenant` / `archive`）。"""

    tables: frozenset[str]
    """该链表集（迁移与自动建表共同口径）。"""

    scope: str
    """库语义说明（平台库 / 租户库 / 归档库）。"""

    @property
    def branch(self) -> str:
        """分支标签（与链名一致，写入迁移脚本 `branch_labels`）。

        Returns:
            str: 分支标签。
        """
        return self.name

    @property
    def version_location(self) -> Path:
        """版本目录（`alembic/versions/<链名>/`）。

        Returns:
            Path: 版本目录路径。
        """
        return VERSIONS_ROOT / self.name


MIGRATION_CHAINS: dict[str, MigrationChain] = {
    "platform": MigrationChain(name="platform", tables=PLATFORM_TABLES, scope="平台库"),
    "tenant": MigrationChain(name="tenant", tables=TENANT_TABLES, scope="租户库"),
    "archive": MigrationChain(name="archive", tables=ARCHIVE_TABLES, scope="归档库"),
}
"""迁移链注册表（键为链名，保序：平台 → 租户 → 归档）。"""

DEFAULT_MIGRATION_TARGET = "tenant"
"""缺省链（对应 `[alembic]` 配置段；向后兼容既有 `alembic upgrade head` 调用）。"""

CONFIG_SECTION = "alembic"
"""Alembic 缺省配置段名（全部配置段形如 `alembic` / `alembic:<链名>`）。"""


def config_section(chain: MigrationChain) -> str:
    """取该链的 Alembic 配置段名（缺省链用 `[alembic]`，其余用 `[alembic:<链名>]`）。

    Args:
        chain: 链定义。

    Returns:
        str: 配置段名。
    """
    if chain.name == DEFAULT_MIGRATION_TARGET:
        return CONFIG_SECTION
    return f"{CONFIG_SECTION}:{chain.name}"


def resolve_chain_from_section(section: str) -> MigrationChain:
    """按 Alembic 配置段名取链（`alembic` → 缺省链；`alembic:<链名>` → 对应链）。

    单入参口径：`alembic -n alembic:<链名> upgrade head` 与 `ops` 程序化调用同源。

    Args:
        section: 配置段名。

    Returns:
        MigrationChain: 链定义。

    Raises:
        ConfigError: 配置段未登记。
    """
    if section == CONFIG_SECTION:
        return resolve_chain(DEFAULT_MIGRATION_TARGET)
    prefix = f"{CONFIG_SECTION}:"
    if section.startswith(prefix):
        return resolve_chain(section[len(prefix) :])
    raise ConfigError(f"未知 Alembic 配置段：{section}（允许 {CONFIG_SECTION} / {CONFIG_SECTION}:<链名>）")


def import_models() -> None:
    """导入全部模型模块（注册 `Base.metadata`；幂等）。"""
    for module in _MODEL_MODULES:
        importlib.import_module(module)


def chain_names() -> list[str]:
    """全部链名（保序）。

    Returns:
        list[str]: 链名列表。
    """
    return list(MIGRATION_CHAINS)


def resolve_chain(target: str) -> MigrationChain:
    """按链名取链定义。

    Args:
        target: 链名（`platform` / `tenant` / `archive`）。

    Returns:
        MigrationChain: 链定义。

    Raises:
        ConfigError: 链名未登记。
    """
    chain = MIGRATION_CHAINS.get(target)
    if chain is None:
        allowed = " / ".join(chain_names())
        raise ConfigError(f"未知迁移链：{target}（允许 {allowed}）")
    return chain


def chain_metadata(chain: MigrationChain) -> MetaData:
    """取该链的元数据子集（只含链表；沿用 `Base.metadata` 命名约定）。

    Args:
        chain: 链定义。

    Returns:
        MetaData: 元数据子集（迁移目标 / 自动建表共用）。

    Raises:
        ConfigError: 链表集登记的表在模型中不存在（声明与实现不符）。
    """
    import_models()
    metadata = MetaData(naming_convention=Base.metadata.naming_convention)
    missing = sorted(chain.tables - set(Base.metadata.tables))
    if missing:
        raise ConfigError(f"迁移链 {chain.name} 登记的表在模型中不存在：{', '.join(missing)}")
    for name, table in Base.metadata.tables.items():
        if name in chain.tables:
            table.to_metadata(metadata)
    return metadata


def chain_url(
    chain: MigrationChain,
    settings: Settings | None = None,
    *,
    db_key: str | None = None,
    allow_cross_service: bool = False,
) -> str:
    """取该链的连接串（含分字段密码；禁止写入日志）。

    传入 `db_key` 时无论链别一律经库键与 `url_template` 解析（复用引擎工厂口径，服务化后
    平台链亦可按 `platform_{service}` 指定服务库）；未传时取链对应的配置缺省连接串。

    Args:
        chain: 链定义。
        settings: 应用配置；None 取全局配置单例。
        db_key: 库键（`platform` / `platform_{service}` / `tenant_{code}` / `tenant_{service}_{code}`）。
        allow_cross_service: 是否允许跨服务库键（**仅 `ops` / 迁移运维通道**）。

    Returns:
        str: 连接串（含密码）。
    """
    resolved = settings if settings is not None else get_settings()
    if db_key:
        from bms_core.db.engine import EngineFactory

        return EngineFactory(resolved, allow_cross_service=allow_cross_service).resolved_url(db_key)
    database = resolved.database
    if chain.name == "platform":
        return database.platform.resolved_url()
    if chain.name == "archive":
        return database.archive.resolved_url()
    return database.tenants.resolved_url()


def has_revisions(chain: MigrationChain) -> bool:
    """该链是否已有迁移脚本（空链提示用）。

    Args:
        chain: 链定义。

    Returns:
        bool: 存在迁移脚本 True。
    """
    location = chain.version_location
    if not location.is_dir():
        return False
    return any(path.suffix == ".py" for path in location.iterdir())


def alembic_config(chain: MigrationChain) -> Config:
    """取该链的 Alembic 配置（**配置段名 = 链名**，版本目录由配置段 `version_locations` 声明）。

    Alembic 在 `env.py` 执行**之前**读取 `version_locations`，故选链只能经配置段
    （`alembic -n alembic:<链名>`）；本函数是 ops 侧程序化调用的唯一入口。

    Args:
        chain: 链定义。

    Returns:
        Config: 该链的 Alembic 配置。
    """
    return Config(str(BACKEND_ROOT / "alembic.ini"), ini_section=config_section(chain))


def head_revision(chain: MigrationChain) -> str | None:
    """取该链 head 版本号（空链返回 None；供「已是最新」幂等判定）。

    Args:
        chain: 链定义。

    Returns:
        str | None: head 版本号。
    """
    return ScriptDirectory.from_config(alembic_config(chain)).get_current_head()


def upgrade_chain(chain: MigrationChain, url: str, *, schema: str = "") -> None:
    """**阻塞**把该链迁移到 head（调用方用 `asyncio.to_thread` 包装）。

    连接串经 `-x url=` 显式传入（优先于配置与环境变量）；达梦模式经 `-x schema=` 切换
    （其他方言忽略该参数）。

    Args:
        chain: 链定义。
        url: 目标连接串（含密码；禁止写入日志）。
        schema: 达梦目标模式名（空串表示不切换）。
    """
    config = alembic_config(chain)
    x_args = [f"url={url}"] + ([f"schema={schema}"] if schema else [])
    config.cmd_opts = SimpleNamespace(x=x_args)  # pyright: ignore[reportAttributeAccessIssue]
    command.upgrade(config, "head")


def apply_session_schema(connection: Connection, schema: str) -> None:
    """切换达梦会话当前模式（非达梦方言 / 未指定模式时为空操作）。

    迁移与版本读取共用：达梦以**模式**为库级隔离单位，操作前须把会话切到目标模式；
    `SET SCHEMA` 不被支持时回落标准 SQL `ALTER SESSION SET CURRENT_SCHEMA`。

    Args:
        connection: 数据库连接（同步）。
        schema: 目标模式名（空串表示不切换）。
    """
    if not schema or connection.dialect.name != _DM:
        return
    try:
        connection.exec_driver_sql(f"SET SCHEMA {schema}")
    except Exception:  # 达梦版本差异：`SET SCHEMA` 不支持时回落标准 SQL 语法
        connection.exec_driver_sql(f"ALTER SESSION SET CURRENT_SCHEMA {schema}")
    # 结束 `SET SCHEMA` 打开的隐式事务：否则 Alembic 会把其视为「外部事务」而不再提交，
    # 导致迁移的 `alembic_version` 版本行随连接关闭回滚（实测：表已建、版本行为空）
    if connection.in_transaction():
        connection.commit()


def _read_revision(url: str, schema: str) -> str | None:
    """同步读目标库 `alembic_version` 当前版本（达梦等无异步方言驱动）。

    Args:
        url: 连接串。
        schema: 目标模式名（达梦；空串表示不切换）。

    Returns:
        str | None: 当前版本号；未迁移（表不存在）返回 None。
    """
    engine = create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            apply_session_schema(connection, schema)
            try:
                row = connection.exec_driver_sql("SELECT version_num FROM alembic_version").first()
            except ProgrammingError, OperationalError, DatabaseError:
                # 未迁移：无 `alembic_version` 表（各库异常类不同——PG / MySQL 报 ProgrammingError、
                # SQLite 报 OperationalError、达梦把「无效的表或视图名」报为 DatabaseError）
                return None
            return None if row is None else str(row[0])
    finally:
        engine.dispose()


async def current_revision(url: str, *, schema: str = "") -> str | None:
    """读目标库 `alembic_version` 当前版本（未迁移返回 None）。

    供 `ops` 批量迁移判断「已是最新（跳过）」与初始化报告；达梦走同步驱动线程。

    Args:
        url: 连接串。
        schema: 目标模式名（达梦；空串表示不切换）。

    Returns:
        str | None: 当前版本号；未迁移返回 None。
    """
    if make_url(url).get_backend_name() == _DM:
        return await asyncio.to_thread(_read_revision, url, schema)
    engine = create_async_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            try:
                result = await connection.exec_driver_sql("SELECT version_num FROM alembic_version")
            except ProgrammingError, OperationalError, DatabaseError:
                # 未迁移：无 `alembic_version` 表（各库异常类不同——PG / MySQL 报 ProgrammingError、
                # SQLite 报 OperationalError、达梦把「无效的表或视图名」报为 DatabaseError）
                return None
            value = result.scalar()
            return None if value is None else str(value)
    finally:
        await engine.dispose()
