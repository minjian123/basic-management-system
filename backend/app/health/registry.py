"""健康检查能力域：真实内存注册表（03-3）。

- `HealthCheckRegistry`：`BaseHealthCheckRegistry` 的真实实现（实现名 `local`）——登记 / 解析公共实现
  继承自注册表中间层（注册顺序、重复键拒重）；聚合模板（并发 + 单项 / 整体两级超时）由基座提供；
  超时值经构造注入（装配工厂取 `[health]` 配置，并注入 `redis` / `database` 检查项）。
"""

from app.health.base import (
    DEFAULT_CHECK_TIMEOUT_MS,
    DEFAULT_TOTAL_TIMEOUT_MS,
    BaseHealthCheck,
    BaseHealthCheckRegistry,
)

__all__ = ["HealthCheckRegistry"]


class HealthCheckRegistry(BaseHealthCheckRegistry):
    """真实内存注册表：登记检查项（注册顺序、唯一性），聚合由基座模板执行。"""

    def __init__(
        self,
        *,
        check_timeout_ms: int = DEFAULT_CHECK_TIMEOUT_MS,
        total_timeout_ms: int = DEFAULT_TOTAL_TIMEOUT_MS,
    ) -> None:
        """初始化。

        Args:
            check_timeout_ms: 单项检查超时（毫秒）。
            total_timeout_ms: 聚合整体总超时（毫秒）。
        """
        super().__init__(check_timeout_ms=check_timeout_ms, total_timeout_ms=total_timeout_ms)

    @classmethod
    def _provider_key(cls, provider: BaseHealthCheck) -> str:
        """注册项键：检查项 `key`。

        Args:
            provider: 检查项。

        Returns:
            str: 检查项键。
        """
        return provider.key
