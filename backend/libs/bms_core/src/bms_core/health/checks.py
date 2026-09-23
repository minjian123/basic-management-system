"""健康检查能力域：真实依赖检查项（03-3）。

- `RedisHealthCheck`：`redis` 检查项——懒建 `redis.asyncio` 客户端并 `PING`；实现 `BaseAsyncResource`，
  经 `ResourceManager` 随应用生命周期统一释放（连接跨探测复用，不做每次新建）。
- `DatabaseHealthCheck`：`database` 检查项——经 `EngineRegistry` 取平台引擎（本服务平台库）执行 `SELECT 1`。
- `CatalogHealthCheck`：`catalog` 检查项——服务目录快照可达性（`platform` 本地权威 / 其余服务经契约）；
  **非必需项**（`required=False`）：失败只标记降级可见，不产生 503（06_01）。
- 检查项**不自行捕获异常**：IO 异常 / 超时统一由 `BaseHealthCheckRegistry.aggregate` 兜底为异常类名，
  避免各检查项重复 try/except 与错误泄漏口径漂移；检查项 `name` 取 `DEPENDENCIES`（与降级 / 熔断 / 指标同源）。
"""

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import text

from bms_core.core.capability import BaseAsyncResource
from bms_core.db.registry import PLATFORM_DB_KEY, EngineRegistry
from bms_core.health.base import BaseHealthCheck, HealthCheckResult

__all__ = ["CATALOG_CHECK_KEY", "CatalogHealthCheck", "DatabaseHealthCheck", "RedisHealthCheck"]

CATALOG_CHECK_KEY = "catalog"
"""服务目录检查项键（`/readyz` 消费方按此键联动 `bms_catalog_degraded` 指标；08_02）。"""


class RedisHealthCheck(BaseHealthCheck, BaseAsyncResource):
    """`redis` 检查项：客户端 `PING`，连接对象随应用生命周期释放。"""

    def __init__(self, url: str) -> None:
        """初始化。

        Args:
            url: Redis 连接串（装配侧取 `settings.redis.url`，含 `BMS_` 覆盖后的生效值）。
        """
        self._url = url
        self._client: Redis | None = None

    @property
    def key(self) -> str:
        """检查项键（取 `DEPENDENCIES` 的 `redis`）。"""
        return "redis"

    def describe(self) -> str:
        """元信息描述。

        Returns:
            str: 检查项说明。
        """
        return f"Redis 健康检查（{self.key}）"

    async def check(self) -> HealthCheckResult:
        """执行 `PING` 探测。

        Returns:
            HealthCheckResult: 就绪结果；异常由聚合层兜底为异常类名。
        """
        client = self._client
        if client is None:
            client = Redis.from_url(self._url)  # pyright: ignore[reportUnknownMemberType]
            self._client = client
        await client.ping()  # pyright: ignore[reportUnknownMemberType]
        return HealthCheckResult(name=self.key, ok=True)

    async def aclose(self) -> None:
        """关闭 Redis 客户端（幂等，随应用生命周期调用）。"""
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()


class DatabaseHealthCheck(BaseHealthCheck):
    """`database` 检查项：平台库 `SELECT 1`。"""

    def __init__(self, registry: EngineRegistry) -> None:
        """初始化。

        Args:
            registry: 多租户引擎注册表（取平台引擎）。
        """
        self._registry = registry

    @property
    def key(self) -> str:
        """检查项键（取 `DEPENDENCIES` 的 `database`）。"""
        return "database"

    def describe(self) -> str:
        """元信息描述。

        Returns:
            str: 检查项说明。
        """
        return f"数据库健康检查（{self.key}）"

    async def check(self) -> HealthCheckResult:
        """执行平台库连通性探测。

        Returns:
            HealthCheckResult: 就绪结果；异常由聚合层兜底为异常类名。
        """
        engine = await self._registry.get(PLATFORM_DB_KEY)
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return HealthCheckResult(name=self.key, ok=True)


class CatalogHealthCheck(BaseHealthCheck):
    """`catalog` 检查项：服务目录快照可达性（**非必需**：失败只标记降级可见）。

    取数路径与启动接库校验同源（`platform` 本地权威直读 / 其余服务经 `service_client` 契约），
    故该项可反映「启动降级」是否仍存在；失败不参与整体就绪判定（不产生 503）。
    """

    required = False

    def __init__(self, app: FastAPI) -> None:
        """初始化。

        Args:
            app: 应用实例（取服务身份 / 配置 / 引擎注册表 / 会话工厂）。
        """
        self._app = app

    @property
    def key(self) -> str:
        """检查项键（`catalog`）。"""
        return CATALOG_CHECK_KEY

    def describe(self) -> str:
        """元信息描述。

        Returns:
            str: 检查项说明。
        """
        return f"服务目录快照健康检查（{self.key}；非必需项）"

    async def check(self) -> HealthCheckResult:
        """探测服务目录快照可达性（懒导入避免能力域导入期耦合）。

        Returns:
            HealthCheckResult: 就绪结果；异常由聚合层兜底为异常类名。
        """
        from bms_core.catalog.loader import load_catalog_snapshot

        await load_catalog_snapshot(self._app)
        return HealthCheckResult(name=self.key, ok=True)
