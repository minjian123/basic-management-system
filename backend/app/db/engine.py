"""异步引擎工厂：按数据源与读写角色创建 / 缓存引擎。

- 方言：SQLite `sqlite+aiosqlite`（开发 / 测试）、MySQL `mysql+aiomysql`、
  PostgreSQL `postgresql+psycopg`、达梦 `dm+dmPython`（**同步驱动**，见下）。
- 主 / 副本多绑定：写走主引擎；只读有副本时按进程内轮询选副本，无副本回落主引擎。
- 租户库键（`tenant_{code}`）经目标 `url_template` 模板解析（`{service}` / `{tenant}` / `{database}`），
  空模板回落 `url` 单库（开发 SQLite 兼容）；平台 / 归档库恒取 `url`。
- 建引擎**不建连**；URL 经配置基座读取；连接池参数按服务（`[app].service`）取覆盖。
- 达梦为同步驱动、无异步方言：`create` 对其抛 `ConfigError`（运行期经 `app/db/sync.py` 的
  同步门面 `SyncSession` 接入，见《后端基类清单》）；`create_sync` 提供同步引擎
  （达梦运行期与四库连通性验证），支持与异步路径同源的副本路由。
- 工厂链：`EngineFactory → BaseDbFactory → BaseFactory → BasePluggable`（02-54）；实现可替换
  （插件键 `engine_factory`，配置经 `[engine_factory].provider` 选择，缺省 `default`）。
"""

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import DatabaseTargetSettings, DbPoolSettings, Settings, get_settings
from app.core.exceptions import ConfigError
from app.core.factory import BaseDbFactory
from app.db.sync import SYNC_ONLY_DIALECTS
from app.db.tenant import TENANT_DB_KEY_PREFIX, parse_tenant_db_key

_SQLITE = "sqlite"
PLATFORM_DB_KEY = "platform"
"""平台库数据源键（唯一来源；`app/db/registry.py` 复用）。"""
ARCHIVE_DB_KEY = "archive"
"""归档库数据源键（只读）。"""
_CONNECT_TIMEOUT_DIALECTS = frozenset({"mysql", "postgresql"})
"""支持 `connect_args={"connect_timeout": ...}` 的异步方言。"""


def _dialect_name(url: str) -> str:
    """取连接串方言名（`+` 前段，如 `mysql` / `postgresql` / `dm` / `sqlite`）。

    Args:
        url: 数据库连接串。

    Returns:
        str: 后端方言名。
    """
    return make_url(url).get_backend_name()


def _with_password(url: str, target: DatabaseTargetSettings) -> str:
    """按目标的分字段密码合成连接串（无密码则原样返回）。

    Args:
        url: 连接串（主库或副本）。
        target: 数据库目标配置。

    Returns:
        str: 可能含密码的连接串（禁止写入日志）。
    """
    if not target.password:
        return url
    return make_url(url).set(password=target.password).render_as_string(hide_password=False)


class EngineFactory(BaseDbFactory[str | None, AsyncEngine]):
    """异步引擎工厂：按 `(db_key, 读写角色)` 创建并缓存引擎。"""

    key: str = "engine_factory"

    def __init__(self, settings: Settings | None = None) -> None:
        """初始化。

        Args:
            settings: 应用配置（数据库 URL 与连接池参数）；缺省取全局配置单例。
        """
        self._settings = settings or get_settings()
        self._engines: dict[tuple[str, str], AsyncEngine] = {}
        self._sync_engines: dict[tuple[str, str], Engine] = {}
        self._round_robin: dict[str, int] = {}

    def create(self, options: str | None = None, *, read_only: bool = False) -> AsyncEngine:
        """创建 / 复用异步引擎（不建连）。

        Args:
            options: 数据源键（`platform` / `archive` / 其余按租户库）；缺省 `platform`。
            read_only: 是否只读；只读时若有副本则轮询选副本，无副本回落主引擎。

        Returns:
            AsyncEngine: 异步引擎。

        Raises:
            ConfigError: 该方言为同步驱动（达梦），异步路径不可用。
        """
        db_key = options or PLATFORM_DB_KEY
        target = self._target(db_key)
        url, role = self._resolve_url_role(target, db_key, read_only=read_only)
        engine = self._engines.get((db_key, role))
        if engine is not None:
            return engine
        dialect = _dialect_name(url)
        if dialect in SYNC_ONLY_DIALECTS:
            raise ConfigError(
                f"数据库方言 {dialect} 为同步驱动、无异步实现（运行期请走同步门面 SyncSession）：{db_key}"
            )
        engine = create_async_engine(url, **self._engine_kwargs(target, dialect))
        self._engines[(db_key, role)] = engine
        return engine

    def create_sync(self, options: str | None = None, *, read_only: bool = False) -> Engine:
        """创建 / 复用同步引擎（达梦运行期与四库连通性验证用）。

        副本路由与异步路径同源：`read_only=True` 且配置了副本时轮询选副本，无副本回落主库。

        Args:
            options: 数据源键；缺省 `platform`。
            read_only: 是否只读（True 时经副本路由）。

        Returns:
            Engine: 同步引擎（不建连）。
        """
        db_key = options or PLATFORM_DB_KEY
        target = self._target(db_key)
        url, role = self._resolve_url_role(target, db_key, read_only=read_only)
        engine = self._sync_engines.get((db_key, role))
        if engine is not None:
            return engine
        engine = create_engine(url, pool_pre_ping=True)
        self._sync_engines[(db_key, role)] = engine
        return engine

    def replicas(self, db_key: str) -> list[str]:
        """取该库配置的只读副本连接串列表。

        Args:
            db_key: 数据源键。

        Returns:
            list[str]: 副本连接串列表（可能为空）。
        """
        return list(self._target(db_key).replicas)

    def resolve_url(self, db_key: str = PLATFORM_DB_KEY) -> str:
        """取数据源连接串（不含分字段密码；迁移脚本与 `ops` 复用）。

        租户库键经 `url_template` 模板解析；平台 / 归档库取目标 `url`。

        Args:
            db_key: 数据源键（缺省平台库）。

        Returns:
            str: 连接串（不含分字段密码）。
        """
        return self._target_url(self._target(db_key), db_key)

    def resolved_url(self, db_key: str = PLATFORM_DB_KEY) -> str:
        """取数据源连接串（含分字段密码；供迁移 / 建删库等运维路径使用）。

        Args:
            db_key: 数据源键（缺省平台库）。

        Returns:
            str: 连接串（**禁止写入日志**）。
        """
        target = self._target(db_key)
        return _with_password(self._target_url(target, db_key), target)

    def _target(self, db_key: str) -> DatabaseTargetSettings:
        """按数据源键取数据库目标配置。"""
        database = self._settings.database
        if db_key == PLATFORM_DB_KEY:
            return database.platform
        if db_key == ARCHIVE_DB_KEY:
            return database.archive
        return database.tenants

    def _target_url(self, target: DatabaseTargetSettings, db_key: str) -> str:
        """解析数据源键到连接串（租户键经 `url_template` 模板；空模板回落 `url`）。

        模板占位：`{service}`（`[app].service`）、`{tenant}`（库键反解编码）、
        `{database}`（`bms_{service}_{tenant}`）。

        Args:
            target: 数据库目标配置。
            db_key: 数据源键。

        Returns:
            str: 连接串（不含分字段密码）。

        Raises:
            ConfigError: 租户键非法或模板占位非法。
        """
        if not db_key.startswith(TENANT_DB_KEY_PREFIX):
            return target.url
        tenant = parse_tenant_db_key(db_key)
        if not target.url_template:
            return target.url
        service = self._settings.app.service
        try:
            return target.url_template.format(service=service, tenant=tenant, database=f"bms_{service}_{tenant}")
        except (KeyError, IndexError, ValueError) as exc:
            raise ConfigError(f"租户库连接串模板占位非法：{target.url_template}（{exc}）") from exc

    def _resolve_url_role(self, target: DatabaseTargetSettings, db_key: str, *, read_only: bool) -> tuple[str, str]:
        """解析连接串与角色键（写主库；只读有副本则轮询，无副本回落主库）。

        Args:
            target: 数据库目标配置。
            db_key: 数据源键。
            read_only: 是否只读。

        Returns:
            tuple[str, str]: （连接串, 角色键）。
        """
        if not read_only or not target.replicas:
            return _with_password(self._target_url(target, db_key), target), "write"
        index = self._round_robin.get(db_key, 0)
        self._round_robin[db_key] = (index + 1) % len(target.replicas)
        return _with_password(target.replicas[index], target), f"read:{index}"

    def _engine_kwargs(self, target: DatabaseTargetSettings, dialect: str) -> dict[str, object]:
        """构造引擎参数（SQLite 无池参数；余下附池参数与建连超时）。

        Args:
            target: 数据库目标配置。
            dialect: 方言名。

        Returns:
            dict[str, object]: `create_async_engine` 关键字参数。
        """
        if dialect == _SQLITE:
            return {"pool_pre_ping": True}
        pool: DbPoolSettings = target.effective_pool(self._settings.app.service)
        kwargs: dict[str, object] = {
            "pool_pre_ping": True,
            "pool_size": pool.pool_size,
            "max_overflow": pool.max_overflow,
            "pool_timeout": pool.pool_timeout,
            "pool_recycle": pool.pool_recycle,
        }
        if dialect in _CONNECT_TIMEOUT_DIALECTS:
            kwargs["connect_args"] = {"connect_timeout": int(pool.connect_timeout)}
        return kwargs

    async def drop(self, db_key: str) -> None:
        """释放并移除指定数据源的全部引擎（主 / 副本 / 同步）。

        Args:
            db_key: 数据源键。
        """
        roles = [role for (key, role) in self._engines if key == db_key]
        for role in roles:
            engine = self._engines.pop((db_key, role), None)
            if engine is not None:
                await engine.dispose()
        sync_roles = [role for (key, role) in self._sync_engines if key == db_key]
        for sync_role in sync_roles:
            sync_engine = self._sync_engines.pop((db_key, sync_role), None)
            if sync_engine is not None:
                sync_engine.dispose()
        self._round_robin.pop(db_key, None)

    async def aclose(self) -> None:
        """释放全部缓存引擎（幂等）。"""
        for engine in self._engines.values():
            await engine.dispose()
        self._engines.clear()
        for sync_engine in self._sync_engines.values():
            sync_engine.dispose()
        self._sync_engines.clear()
        self._round_robin.clear()
