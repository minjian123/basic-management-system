"""健康检查能力域：真实内存注册表（03-3）。

- `HealthCheckRegistry`：`BaseHealthCheckRegistry` 的真实实现——登记检查项（启动期、无 IO），
  聚合模板（并发 + 单项 / 整体两级超时）由基座提供；超时值经构造注入（装配侧取 `[health]` 配置）。
"""

from app.health.base import (
    DEFAULT_CHECK_TIMEOUT_MS,
    DEFAULT_TOTAL_TIMEOUT_MS,
    BaseHealthCheck,
    BaseHealthCheckRegistry,
)

__all__ = ["HealthCheckRegistry"]


class HealthCheckRegistry(BaseHealthCheckRegistry):
    """真实内存注册表：按注册顺序持有检查项。"""

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
        self._checks: list[BaseHealthCheck] = []

    def register(self, check: BaseHealthCheck) -> None:
        """登记检查项（追加，保持注册顺序）。

        Args:
            check: 检查项。
        """
        self._checks.append(check)

    def checks(self) -> tuple[BaseHealthCheck, ...]:
        """已登记检查项（注册顺序）。

        Returns:
            tuple[BaseHealthCheck, ...]: 检查项元组。
        """
        return tuple(self._checks)
