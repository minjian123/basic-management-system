"""健康检查能力域：真实依赖检查项（03-3）。

- `RedisHealthCheck`：`redis` 检查项——懒建 `redis.asyncio` 客户端并 `PING`；实现 `BaseAsyncResource`，
  经 `ResourceManager` 随应用生命周期统一释放（连接跨探测复用，不做每次新建）。
- `DatabaseHealthCheck`：`database` 检查项——经 `EngineRegistry` 取平台引擎（`PLATFORM_DB_KEY`）执行 `SELECT 1`。
- 检查项**不自行捕获异常**：IO 异常 / 超时统一由 `BaseHealthCheckRegistry.aggregate` 兜底为异常类名，
  避免各检查项重复 try/except 与错误泄漏口径漂移；检查项 `name` 取 `DEPENDENCIES`（与降级 / 熔断 / 指标同源）。
"""

from redis.asyncio import Redis
from sqlalchemy import text

from app.core.capability import BaseAsyncResource
from app.db.registry import PLATFORM_DB_KEY, EngineRegistry
from app.health.base import BaseHealthCheck, HealthCheckResult

__all__ = ["DatabaseHealthCheck", "RedisHealthCheck"]


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
    def name(self) -> str:
        """检查项名称（取 `DEPENDENCIES` 的 `redis`）。"""
        return "redis"

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
        return HealthCheckResult(name=self.name, ok=True)

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
    def name(self) -> str:
        """检查项名称（取 `DEPENDENCIES` 的 `database`）。"""
        return "database"

    async def check(self) -> HealthCheckResult:
        """执行平台库连通性探测。

        Returns:
            HealthCheckResult: 就绪结果；异常由聚合层兜底为异常类名。
        """
        engine = await self._registry.get(PLATFORM_DB_KEY)
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return HealthCheckResult(name=self.name, ok=True)
