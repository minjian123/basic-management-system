"""数据源迁移链注册：链名 `{service}:{datasource}`（服务 × 数据源）→ 版本目录 / 表集 / 连接串取法。

- **链名 = 配置段名**：缺省链 `platform:tenant` 用 `[alembic]`（向后兼容裸命令），其余链用
  `[alembic:{service}:{datasource}]`（如 `[alembic:platform:platform]`）；命令
  `alembic -n alembic:{service}:{datasource} upgrade head`。**不设数据源级别名段**。
- **版本目录**：`alembic/versions/{service}/{datasource}/`；`branch_labels` 取链名；revision 编号
  **链内唯一、链内独立递增**（跨链允许同名，各链版本目录独立）。
- **表集派生**（单一来源）：`services/table_registry.py::chain_tables(service, datasource)`（仅
  `status = enabled` 的归属表 + 基础设施表）∩ 已有模型（`Base.metadata.tables`）——
  `planned` 表与尚无模型的登记表自然不参与，随所属阶段补模型与表文件后**自动进链**。
- **模型模块按服务解析**：公共模型模块 `COMMON_MODEL_MODULES` + 服务包自声明
  `bms_{service}/models/__init__.py::MODEL_MODULES`（无模型的服务声明空元组）；服务包不存在
  （`planned` / 预留服务）跳过。**动态导入**（`importlib`）而非静态 import——迁移 / 运维期按链的
  服务取模型，`bms_core` 不静态依赖任何服务包（依赖方向不变，见《后端开发规范》）。
- **连接串取法**：显式 `db_key` 优先（运维通道）；缺省按链的数据源解析——平台链取该服务的平台
  服务库（全限定键 `platform_{service}`）、租户链回落 `[database.tenants].url`（真库批量迁移一律
  经库键）、归档链取 `[database.archive].url`（归档库不服务化）。
- 链定义是「Alembic 元数据子集 + 版本目录 + 自动建表表集 + 连接串取法」的**唯一来源**：
  `alembic/env.py` 与开发库自动建表（`db/bootstrap.py`）都从此取，避免多处漂移。
- 表结构以《数据库设计》数据表文件为唯一事实源。
"""

import asyncio
import importlib
import importlib.util
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
from bms_core.db.keys import PLATFORM_SERVICE_KEY, build_platform_db_key
from bms_core.models.base import Base
from bms_core.services.table_registry import chain_tables, known_service_keys

DATASOURCE_PLATFORM = "platform"
"""数据源段：平台服务库。"""

DATASOURCE_TENANT = "tenant"
"""数据源段：服务租户库。"""

DATASOURCE_ARCHIVE = "archive"
"""数据源段：归档库（不服务化，服务段取占位）。"""

DATASOURCES: tuple[str, ...] = (DATASOURCE_PLATFORM, DATASOURCE_TENANT, DATASOURCE_ARCHIVE)
"""数据源段集合（保序：平台 → 租户 → 归档）。"""

CHAIN_SEPARATOR = ":"
"""链名分隔符（链名形如 `platform:platform`）。"""

DEFAULT_CHAIN_NAME = f"{PLATFORM_SERVICE_KEY}{CHAIN_SEPARATOR}{DATASOURCE_TENANT}"
"""缺省链（`platform:tenant`）：配置段 `[alembic]` 指向它，保证裸命令语义不变。"""

CONFIG_SECTION = "alembic"
"""Alembic 缺省配置段名（其余段形如 `alembic:{service}:{datasource}`）。"""

ARCHIVE_CHAIN_SERVICE = PLATFORM_SERVICE_KEY
"""归档链的服务段占位（归档库不服务化，链名固定 `platform:archive`）。"""

COMMON_MODEL_MODULES: tuple[str, ...] = (
    "bms_core.models.ownership",
    "bms_core.models.outbox",
    "bms_core.dict.models",
    "bms_core.listing.models",
)
"""公共模型模块清单（跨服务共享的基座模型；各链均需注册其元数据）。"""

SERVICE_MODEL_MODULES_ENTRY = "MODEL_MODULES"
"""服务包自声明模型模块清单的常量名（`bms_{service}/models/__init__.py`）。"""

_SCOPE_SUFFIX: dict[str, str] = {
    DATASOURCE_PLATFORM: "平台服务库",
    DATASOURCE_TENANT: "服务租户库",
    DATASOURCE_ARCHIVE: "归档库",
}


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
"""迁移脚本根目录（按 `{service}/{datasource}` 两级分子目录）。"""

_DM = "dm"
"""达梦方言名（无异步驱动，走同步引擎）。"""


@dataclass(frozen=True)
class MigrationChain(BaseObject):
    """迁移链定义（服务 × 数据源 → 版本目录 / 表集 / 分支标签）。"""

    name: str
    """链名（`{service}:{datasource}`，同时是配置段名与分支标签）。"""

    service: str
    """服务标识（链归属服务；归档链取占位服务）。"""

    datasource: str
    """数据源段（`platform` / `tenant` / `archive`）。"""

    tables: frozenset[str]
    """该链目标表集（归属登记派生；实际建表以脚本为准）。"""

    scope: str
    """库语义说明（如「platform 服务的平台服务库」）。"""

    @property
    def branch(self) -> str:
        """分支标签（与链名一致，写入迁移脚本 `branch_labels`）。

        Returns:
            str: 分支标签。
        """
        return self.name

    @property
    def version_location(self) -> Path:
        """版本目录（`alembic/versions/{service}/{datasource}/`）。

        Returns:
            Path: 版本目录路径。
        """
        return VERSIONS_ROOT / self.service / self.datasource


def build_chain_name(service: str, datasource: str) -> str:
    """构造链名（`{service}:{datasource}`）。

    Args:
        service: 服务标识（须已登记）。
        datasource: 数据源段（`platform` / `tenant` / `archive`）。

    Returns:
        str: 链名。

    Raises:
        ConfigError: 服务标识未登记或数据源段非法。
    """
    if not service:
        raise ConfigError("链名需要服务标识（形如 platform:platform）")
    if service not in known_service_keys():
        raise ConfigError(f"服务标识未登记：{service}（链名形如 {{service}}:{{datasource}}）")
    if datasource not in DATASOURCES:
        raise ConfigError(f"数据源段非法：{datasource}（允许 {' / '.join(DATASOURCES)}）")
    return f"{service}{CHAIN_SEPARATOR}{datasource}"


def parse_chain_name(name: str) -> tuple[str, str]:
    """反解链名（`{service}:{datasource}`）。

    Args:
        name: 链名。

    Returns:
        tuple[str, str]: （服务标识, 数据源段）。

    Raises:
        ConfigError: 链名形态非法（分段数不为 2 或数据源段非法）。
    """
    raw = name.strip()
    parts = raw.split(CHAIN_SEPARATOR)
    if len(parts) != 2 or not all(parts):
        raise ConfigError(f"链名形态非法：{name}（应为 {{service}}:{{datasource}}，如 platform:platform）")
    service, datasource = parts
    if datasource not in DATASOURCES:
        raise ConfigError(f"链 {name} 的数据源段非法：{datasource}（允许 {' / '.join(DATASOURCES)}）")
    return service, datasource


def resolve_chain(name: str) -> MigrationChain:
    """按链名取链定义（表集由归属登记派生）。

    Args:
        name: 链名（`{service}:{datasource}`）。

    Returns:
        MigrationChain: 链定义。

    Raises:
        ConfigError: 链名形态非法 / 服务标识未登记。
    """
    service, datasource = parse_chain_name(name)
    if service not in known_service_keys():
        raise ConfigError(f"链 {name} 的服务标识未登记：{service}")
    scope = f"{service} 服务的{_SCOPE_SUFFIX[datasource]}"
    return MigrationChain(
        name=f"{service}{CHAIN_SEPARATOR}{datasource}",
        service=service,
        datasource=datasource,
        tables=chain_tables(service, datasource),
        scope=scope,
    )


def default_chain() -> MigrationChain:
    """缺省链（`platform:tenant`，对应配置段 `[alembic]`）。

    Returns:
        MigrationChain: 缺省链定义。
    """
    return resolve_chain(DEFAULT_CHAIN_NAME)


def chain_names() -> list[str]:
    """全部候选链名（服务集 × 数据源集，保序；空链由 `has_revisions` 过滤）。

    Returns:
        list[str]: 链名列表。
    """
    return [
        f"{service}{CHAIN_SEPARATOR}{datasource}"
        for service in sorted(known_service_keys())
        for datasource in DATASOURCES
    ]


def service_chains(service: str) -> list[MigrationChain]:
    """某服务的三条链（平台 / 租户 / 归档，启动自动建表与批量迁移用）。

    Args:
        service: 服务标识。

    Returns:
        list[MigrationChain]: 链定义列表（保序）。

    Raises:
        ConfigError: 服务标识未登记。
    """
    return [resolve_chain(build_chain_name(service, datasource)) for datasource in DATASOURCES]


def archive_chain() -> MigrationChain:
    """归档链（`platform:archive`；归档库不服务化，表集为空）。

    Returns:
        MigrationChain: 归档链定义。
    """
    return resolve_chain(build_chain_name(ARCHIVE_CHAIN_SERVICE, DATASOURCE_ARCHIVE))


def config_section(chain: MigrationChain) -> str:
    """取该链的 Alembic 配置段名（缺省链用 `[alembic]`，其余用 `[alembic:{链名}]`）。

    Args:
        chain: 链定义。

    Returns:
        str: 配置段名。
    """
    if chain.name == DEFAULT_CHAIN_NAME:
        return CONFIG_SECTION
    return f"{CONFIG_SECTION}{CHAIN_SEPARATOR}{chain.name}"


def resolve_chain_from_section(section: str) -> MigrationChain:
    """按 Alembic 配置段名取链（`[alembic]` → 缺省链；`[alembic:{链名}]` → 对应链）。

    单入参口径：`alembic -n alembic:{service}:{datasource} upgrade head` 与 `ops` 程序化调用同源。

    Args:
        section: 配置段名。

    Returns:
        MigrationChain: 链定义。

    Raises:
        ConfigError: 配置段未登记 / 缺省链误用全限定段名。
    """
    if section == CONFIG_SECTION:
        return default_chain()
    prefix = f"{CONFIG_SECTION}{CHAIN_SEPARATOR}"
    if section.startswith(prefix):
        name = section[len(prefix) :]
        chain = resolve_chain(name)
        if chain.name == DEFAULT_CHAIN_NAME:
            raise ConfigError(
                f"缺省链（{DEFAULT_CHAIN_NAME}）的配置段为 [{CONFIG_SECTION}]：请用 `-n {CONFIG_SECTION}`"
            )
        return chain
    raise ConfigError(
        f"未知 Alembic 配置段：{section}（允许 {CONFIG_SECTION} / {CONFIG_SECTION}:{{service}}:{{datasource}}）"
    )


def service_model_modules(service: str) -> tuple[str, ...]:
    """取服务包自声明的模型模块清单（服务包不存在返回空元组）。

    Args:
        service: 服务标识。

    Returns:
        tuple[str, ...]: 模型模块清单。

    Raises:
        ConfigError: 服务包存在但未声明 `MODEL_MODULES`。
    """
    package = f"bms_{service}.models"
    if importlib.util.find_spec(package) is None:
        return ()
    module = importlib.import_module(package)
    declared = getattr(module, SERVICE_MODEL_MODULES_ENTRY, None)
    if declared is None:
        raise ConfigError(
            f"服务包 {package} 未声明 {SERVICE_MODEL_MODULES_ENTRY}（模型模块清单；无模型的服务请声明空元组）"
        )
    return tuple(str(name) for name in declared)


def import_models(service: str) -> None:
    """导入该链服务的全部模型模块（注册 `Base.metadata`；幂等）。

    动态导入：迁移 / 运维期按链的服务取模型，`bms_core` 不静态依赖任何服务包。

    Args:
        service: 服务标识。

    Raises:
        ConfigError: 服务包存在但未声明 `MODEL_MODULES`。
    """
    for module in (*COMMON_MODEL_MODULES, *service_model_modules(service)):
        importlib.import_module(module)


def chain_metadata(chain: MigrationChain) -> MetaData:
    """取该链的元数据子集（表集派生 ∩ 已有模型；沿用 `Base.metadata` 命名约定）。

    Args:
        chain: 链定义。

    Returns:
        MetaData: 元数据子集（迁移目标 / 自动建表共用）。
    """
    import_models(chain.service)
    metadata = MetaData(naming_convention=Base.metadata.naming_convention)
    for name in sorted(chain.tables & set(Base.metadata.tables)):
        Base.metadata.tables[name].to_metadata(metadata)
    return metadata


def chain_url(
    chain: MigrationChain,
    settings: Settings | None = None,
    *,
    db_key: str | None = None,
    allow_cross_service: bool = False,
) -> str:
    """取该链的连接串（含分字段密码；禁止写入日志）。

    显式 `db_key` 时一律经库键与 `url_template` 解析（运维通道）；未传时按链的数据源解析：
    平台链取该服务的平台服务库（全限定键 `platform_{service}`）、租户链回落
    `[database.tenants].url`（真库批量迁移一律经库键）、归档链取 `[database.archive].url`。

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
    if chain.datasource == DATASOURCE_ARCHIVE:
        return database.archive.resolved_url()
    if chain.datasource == DATASOURCE_PLATFORM:
        from bms_core.db.engine import EngineFactory

        # 链自带服务：按服务派生全限定键（运维通道，不受运行服务限制）
        key = build_platform_db_key(chain.service)
        return EngineFactory(resolved, allow_cross_service=True).resolved_url(key)
    return database.tenants.resolved_url()


def has_revisions(chain: MigrationChain) -> bool:
    """该链是否已有迁移脚本（空链提示与跳过用）。

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
    """取该链的 Alembic 配置（**配置段名由链名派生**，版本目录由配置段声明）。

    Alembic 在 `env.py` 执行**之前**读取 `version_locations`，故选链只能经配置段；本函数是
    ops 侧程序化调用的唯一入口，配置段缺失（新增服务首次迁移未补段）即快速失败。

    Args:
        chain: 链定义。

    Returns:
        Config: 该链的 Alembic 配置。

    Raises:
        ConfigError: 该链未在 `alembic.ini` 登记配置段（缺 `version_locations`）。
    """
    section = config_section(chain)
    try:
        config = Config(str(BACKEND_ROOT / "alembic.ini"), ini_section=section)
        locations = config.get_main_option("version_locations")
    except Exception as exc:  # 配置段缺失 / 读取异常一律快速失败
        raise ConfigError(f"迁移链 {chain.name} 的配置段 [{section}] 不可读：{exc}") from exc
    if not locations:
        raise ConfigError(
            f"迁移链 {chain.name} 未在 alembic.ini 登记配置段 [{section}]（缺 version_locations）；"
            "新增服务首次迁移时须补段"
        )
    return config


def head_revision(chain: MigrationChain) -> str | None:
    """取该链 head 版本号（空链返回 None；供「已是最新」幂等判定）。

    Args:
        chain: 链定义。

    Returns:
        str | None: head 版本号；无脚本返回 None。
    """
    if not has_revisions(chain):
        return None
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
