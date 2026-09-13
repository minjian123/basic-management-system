"""异步引擎工厂：按数据源创建 / 缓存 `AsyncEngine`（SQLite aiosqlite 可跑）。

- 方言：SQLite `sqlite+aiosqlite`（开发 / 测试）、MySQL `mysql+aiomysql`、
  PostgreSQL `postgresql+psycopg`、达梦 `dm+dmPython`（同步驱动封装随回补）。
- 建引擎**不建连**；URL 经配置基座读取。
"""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.base import BaseObject
from app.core.config import DatabaseTargetSettings, Settings


class EngineFactory(BaseObject):
    """异步引擎工厂：按 `db_key` 创建并缓存引擎。"""

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置（数据库 URL 与连接池参数）。
        """
        self._settings = settings
        self._engines: dict[str, AsyncEngine] = {}

    def _target(self, db_key: str) -> DatabaseTargetSettings:
        database = self._settings.database
        if db_key == "platform":
            return database.platform
        if db_key == "archive":
            return database.archive
        return database.tenants

    def create(self, db_key: str = "platform") -> AsyncEngine:
        """创建 / 复用异步引擎（不建连）。

        Args:
            db_key: 数据源键（`platform` / `archive` / 其余按租户库）。

        Returns:
            AsyncEngine: 异步引擎。
        """
        engine = self._engines.get(db_key)
        if engine is not None:
            return engine
        target = self._target(db_key)
        if target.url.startswith("sqlite"):
            engine = create_async_engine(target.url, pool_pre_ping=True)
        else:
            pool = target.pool
            engine = create_async_engine(
                target.url,
                pool_pre_ping=True,
                pool_size=pool.pool_size,
                max_overflow=pool.max_overflow,
                pool_timeout=pool.pool_timeout,
                pool_recycle=pool.pool_recycle,
            )
        self._engines[db_key] = engine
        return engine

    async def dispose(self) -> None:
        """释放全部缓存引擎。"""
        for engine in self._engines.values():
            await engine.dispose()
        self._engines.clear()
