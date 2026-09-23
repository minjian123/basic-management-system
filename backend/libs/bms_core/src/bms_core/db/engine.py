"""异步引擎工厂：按数据源与读写角色创建 / 缓存引擎。

- 方言：SQLite `sqlite+aiosqlite`（开发 / 测试）、MySQL `mysql+aiomysql`、
  PostgreSQL `postgresql+psycopg`、达梦 `dm+dmPython`（**同步驱动**，见下）。
- 主 / 副本多绑定：写走主引擎；只读有副本时按进程内轮询选副本，无副本回落主引擎。
- 库键与库名经 `bms_core/db/keys.py` 单一来源派生：**相对键**（`platform` / `tenant_{code}`）按当前
  服务解析为 `bms_{service}` / `bms_{service}_{code}`；**全限定键**（`platform_{service}` /
  `tenant_{service}_{code}`）显式指向某服务。平台目标占位 `{service}` / `{database}`，租户目标占位
  `{service}` / `{tenant}` / `{database}`；空模板回落 `url` 单库（开发 SQLite 兼容）；归档库恒取 `url`。
- **越界拒绝**：取键入口先经 `validate_key` 校验服务归属，全限定键越界抛 `DataOwnershipError`（10008）；
  运维侧（`ops`）经 `allow_cross_service=True` 显式豁免（仅运维通道）。
- 建引擎**不建连**；URL 经配置基座读取；连接池参数按服务（`[app].service`）取覆盖。
- 达梦为同步驱动、无异步方言：`create` 对其抛 `ConfigError`（运行期经 `app/db/sync.py` 的
  同步门面 `SyncSession` 接入，见《后端基类清单》）；`create_sync` 提供同步引擎
  （达梦运行期与四库连通性验证），支持与异步路径同源的副本路由。
- 工厂链：`EngineFactory → BaseDbFactory → BaseFactory → BasePluggable`（02-54）；实现可替换
  （插件键 `engine_factory`，配置经 `[engine_factory].provider` 选择，缺省 `default`）。
"""

import sqlalchemy
import sqlalchemy.ext.asyncio
from sqlalchemy import Engine
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.config import DatabaseTargetSettings, DbPoolSettings, Settings, get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.factory import BaseDbFactory
from bms_core.db.keys import (
    DB_KIND_ARCHIVE,
    DB_KIND_PLATFORM,
    PLATFORM_DB_KEY,
    DbKey,
    database_name,
    resolve_db_key,
)
from bms_core.db.sync import SYNC_ONLY_DIALECTS

_SQLITE = "sqlite"
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

    def __init__(self, settings: Settings | None = None, *, allow_cross_service: bool = False) -> None:
        """初始化。

        Args:
            settings: 应用配置（数据库 URL 与连接池参数）；缺省取全局配置单例。
            allow_cross_service: 是否允许跨服务数据源键（**仅 `ops` 运维通道**使用；
                `False` 时全限定键的服务段必须为当前服务，否则 `DataOwnershipError` 10008）。
        """
        self._settings = settings or get_settings()
        self._allow_cross_service = allow_cross_service
        self._engines: dict[tuple[str, str], AsyncEngine] = {}
        self._sync_engines: dict[tuple[str, str], Engine] = {}
        self._round_robin: dict[str, int] = {}

    def validate_key(self, db_key: str | None = None) -> DbKey:
        """解析并校验数据源键归属（取键入口统一前置；注册表复用同一判定）。

        Args:
            db_key: 数据源键；None / 空串取 `platform`（本服务平台库）。

        Returns:
            DbKey: 库键解析结果。

        Raises:
            ConfigError: 键形态非法或全限定键服务标识未登记。
            DataOwnershipError: 全限定键越界且未开启运维豁免（10008）。
        """
        return resolve_db_key(
            db_key or PLATFORM_DB_KEY,
            service=self._settings.app.service,
            allow_cross_service=self._allow_cross_service,
        )

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
        key, target = self._resolve(options)
        url, role = self._resolve_url_role(key, target, read_only=read_only)
        engine = self._engines.get((key.raw, role))
        if engine is not None:
            return engine
        dialect = _dialect_name(url)
        if dialect in SYNC_ONLY_DIALECTS:
            raise ConfigError(
                f"数据库方言 {dialect} 为同步驱动、无异步实现（运行期请走同步门面 SyncSession）：{key.raw}"
            )
        engine = sqlalchemy.ext.asyncio.create_async_engine(url, **self._engine_kwargs(target, dialect))
        self._engines[(key.raw, role)] = engine
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
        key, target = self._resolve(options)
        url, role = self._resolve_url_role(key, target, read_only=read_only)
        engine = self._sync_engines.get((key.raw, role))
        if engine is not None:
            return engine
        engine = sqlalchemy.create_engine(url, pool_pre_ping=True)
        self._sync_engines[(key.raw, role)] = engine
        return engine

    def replicas(self, db_key: str) -> list[str]:
        """取该库配置的只读副本连接串列表。

        Args:
            db_key: 数据源键。

        Returns:
            list[str]: 副本连接串列表（可能为空）。
        """
        return list(self._resolve(db_key)[1].replicas)

    def resolve_url(self, db_key: str = PLATFORM_DB_KEY) -> str:
        """取数据源连接串（不含分字段密码；迁移脚本与 `ops` 复用）。

        平台 / 租户键经各自 `url_template` 模板解析；空模板与归档库取目标 `url`。

        Args:
            db_key: 数据源键（缺省平台库）。

        Returns:
            str: 连接串（不含分字段密码）。
        """
        key, target = self._resolve(db_key)
        return self._target_url(key, target)

    def resolved_url(self, db_key: str = PLATFORM_DB_KEY) -> str:
        """取数据源连接串（含分字段密码；供迁移 / 建删库等运维路径使用）。

        Args:
            db_key: 数据源键（缺省平台库）。

        Returns:
            str: 连接串（**禁止写入日志**）。
        """
        key, target = self._resolve(db_key)
        return _with_password(self._target_url(key, target), target)

    def _resolve(self, db_key: str | None) -> tuple[DbKey, DatabaseTargetSettings]:
        """解析库键并取数据库目标配置（先校验归属，再按库类别取目标）。

        Args:
            db_key: 数据源键；None / 空串取 `platform`。

        Returns:
            tuple[DbKey, DatabaseTargetSettings]: （库键解析结果, 目标配置）。
        """
        key = self.validate_key(db_key)
        database = self._settings.database
        if key.kind == DB_KIND_ARCHIVE:
            return key, database.archive
        if key.kind == DB_KIND_PLATFORM:
            return key, database.platform
        return key, database.tenants

    def _target_url(self, key: DbKey, target: DatabaseTargetSettings) -> str:
        """解析库键到连接串（平台 / 租户键经 `url_template` 模板；空模板回落 `url`）。

        模板占位：`{service}`（生效服务标识：全限定键的服务段，相对键取 `[app].service`）、
        `{tenant}`（租户编码；平台键为空串）、`{database}`（库名单一来源派生：
        `bms_{service}` / `bms_{service}_{tenant}`）。

        Args:
            key: 库键解析结果。
            target: 数据库目标配置。

        Returns:
            str: 连接串（不含分字段密码）。

        Raises:
            ConfigError: 模板占位非法或需服务标识而未提供。
        """
        if key.kind == DB_KIND_ARCHIVE:
            return target.url
        template = target.url_template
        if not template:
            return target.url
        effective = key.service or self._settings.app.service
        needs_service = "{service}" in template or "{database}" in template
        if needs_service and not effective:
            raise ConfigError(
                f"数据源键 {key.raw} 的连接串模板需要服务标识（{{service}} / {{database}}）："
                "请配置 [app].service 或改用全限定键 platform_{service} / tenant_{service}_{code}"
            )
        database = database_name(key, service=effective) if needs_service else ""
        try:
            return template.format(service=effective, tenant=key.tenant_code or "", database=database)
        except (KeyError, IndexError, ValueError) as exc:
            raise ConfigError(f"数据库连接串模板占位非法：{template}（{exc}）") from exc

    def _resolve_url_role(self, key: DbKey, target: DatabaseTargetSettings, *, read_only: bool) -> tuple[str, str]:
        """解析连接串与角色键（写主库；只读有副本则轮询，无副本回落主库）。

        Args:
            key: 库键解析结果。
            target: 数据库目标配置。
            read_only: 是否只读。

        Returns:
            tuple[str, str]: （连接串, 角色键）。
        """
        if not read_only or not target.replicas:
            return _with_password(self._target_url(key, target), target), "write"
        index = self._round_robin.get(key.raw, 0)
        self._round_robin[key.raw] = (index + 1) % len(target.replicas)
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
