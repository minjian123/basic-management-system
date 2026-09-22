"""健康检查能力域：依赖就绪检查项注册表契约、聚合模板与真实探针（03-3）。

- `DEPENDENCIES`：依赖标识清单**单向复用** `app/fallback/base.py`（health → fallback，不反向），
  使依赖类检查项的 `name` 与降级矩阵 / 熔断 / 指标口径一致（如 `"database"` / `"redis"` / `"minio"`）。
- `HealthCheckResult` / `HealthCheckReport`：单项结果与聚合报告数据契约（frozen dataclass），
  字段与 `/readyz` 响应形态对齐——单项 `{name, ok, error}`、报告 `{ok, checks}`，`error` 仅异常类名。
- `BaseHealthCheck`：检查项契约——`name`（抽象属性）+ 异步 `check()`。
- `BaseHealthCheckRegistry`：能力域中间层契约（`key = "health_check_registry"`）——继承
  `BaseProviderRegistry[BaseHealthCheck]`（唯一性登记 / `get` / `keys` / `values` 公共实现），
  `checks()` 返回已登记检查项（注册顺序）；`aggregate` 为**具体聚合模板**（并发执行 + 单项 / 整体两级超时
  → 保序收集 → 汇总），异常兜底（异常类名）与空集语义单点收敛，超时值经构造注入（默认取本模块常量）。
- `get_health_check_registry`：依赖注入提供者（经插件注册表解析；公共依赖经 `app/api/deps.py` 统一导出）。
- 真实注册表与检查项（`redis` / `database`）见 `app/health/registry.py` / `app/health/checks.py`（03-3 落地，
  `local` 实现名经装配工厂登记）。

口径：本域只回答「依赖是否就绪」（供 `/readyz` 聚合），不执行降级动作（归 `BaseFallbackPolicy`）；
探针结果缓存 / 探测频率限流与失败告警联动随可观测性 / 运维阶段。
"""

import asyncio
from abc import ABC, abstractmethod
from contextlib import suppress
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from bms_core.core.base import BaseObject
from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, resolve_plugin
from bms_core.core.provider import BaseProvider, BaseProviderRegistry
from bms_core.fallback.base import DEPENDENCIES

__all__ = [
    "DEFAULT_CHECK_TIMEOUT_MS",
    "DEFAULT_TOTAL_TIMEOUT_MS",
    "DEPENDENCIES",
    "BaseHealthCheck",
    "BaseHealthCheckRegistry",
    "HealthCheckReport",
    "HealthCheckResult",
    "get_health_check_registry",
]

DEFAULT_CHECK_TIMEOUT_MS = 2000
"""单项检查超时默认值（毫秒）。"""

DEFAULT_TOTAL_TIMEOUT_MS = 5000
"""聚合整体总超时默认值（毫秒）。"""


@dataclass(frozen=True)
class HealthCheckResult(BaseObject):
    """单项健康检查结果（与 `/readyz` 单项响应形态一致）。"""

    name: str
    """检查项名称（依赖类检查项建议取 `DEPENDENCIES` 之一）。"""

    ok: bool
    """是否健康（就绪）。"""

    error: str | None = None
    """未就绪原因——仅异常类名（如 `ConnectionError` / `TimeoutError`）；就绪为 `None`。"""


@dataclass(frozen=True)
class HealthCheckReport(BaseObject):
    """聚合报告：各检查项结果与总体就绪。"""

    ok: bool
    """总体是否就绪（全部检查项通过）。"""

    checks: tuple[HealthCheckResult, ...] = ()
    """各检查项结果（注册顺序，稳定）。"""


class BaseHealthCheck(BaseProvider, ABC):
    """检查项契约：键 + 异步检查（`name` 为 `key` 的兼容别名，`/readyz` 与聚合报告口径不变）。"""

    @property
    @abstractmethod
    def key(self) -> str:
        """检查项键（依赖类检查项建议取 `DEPENDENCIES` 之一）。"""

    @property
    def name(self) -> str:
        """检查项名称别名（等价 `key`）。

        Returns:
            str: 与 `key` 相同的检查项名称。
        """
        return self.key

    @abstractmethod
    async def check(self) -> HealthCheckResult:
        """执行检查。

        Returns:
            HealthCheckResult: 单项检查结果。
        """


class BaseHealthCheckRegistry(BaseProviderRegistry[BaseHealthCheck], ABC):
    """注册表契约：登记检查项 + 聚合就绪（公共登记 / 解析实现继承自注册表中间层）。"""

    key: str = "health_check_registry"
    plugin_key: str = "health_check_registry"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    def __init__(
        self,
        *,
        check_timeout_ms: int = DEFAULT_CHECK_TIMEOUT_MS,
        total_timeout_ms: int = DEFAULT_TOTAL_TIMEOUT_MS,
    ) -> None:
        """初始化。

        Args:
            check_timeout_ms: 单项检查超时（毫秒；`aggregate` 统一包裹各检查项）。
            total_timeout_ms: 聚合整体总超时（毫秒；超时后未完成项按 `TimeoutError` 兜底）。
        """
        super().__init__()
        self._check_timeout_ms = check_timeout_ms
        self._total_timeout_ms = total_timeout_ms

    def checks(self) -> tuple[BaseHealthCheck, ...]:
        """已登记检查项（注册顺序）。

        Returns:
            tuple[BaseHealthCheck, ...]: 检查项元组。
        """
        return self.values()

    async def aggregate(self) -> HealthCheckReport:
        """聚合全部检查项为就绪报告（模板方法：并发执行 + 两级超时 + 单项异常不中断聚合）。

        Returns:
            HealthCheckReport: 聚合报告；空注册表视为就绪（`ok=True`）。
        """
        checks = self.checks()
        if not checks:
            return HealthCheckReport(ok=True)

        results: dict[int, HealthCheckResult] = {}

        async def run(index: int, check: BaseHealthCheck) -> None:
            try:
                async with asyncio.timeout(self._check_timeout_ms / 1000):
                    results[index] = await check.check()
            except Exception as exc:  # 超时与检查项异常统一收敛为异常类名
                results[index] = HealthCheckResult(name=check.name, ok=False, error=type(exc).__name__)

        with suppress(TimeoutError):
            async with asyncio.timeout(self._total_timeout_ms / 1000):
                await asyncio.gather(*(run(index, check) for index, check in enumerate(checks)))

        ordered = tuple(
            results.get(index) or HealthCheckResult(name=check.name, ok=False, error="TimeoutError")
            for index, check in enumerate(checks)
        )
        return HealthCheckReport(ok=all(result.ok for result in ordered), checks=ordered)


def get_health_check_registry(request: Request) -> BaseHealthCheckRegistry:
    """取应用级健康检查注册表（依赖注入提供者；经插件注册表按配置解析）。

    Args:
        request: 请求对象。

    Returns:
        BaseHealthCheckRegistry: 应用装配的注册表实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseHealthCheckRegistry",
        resolve_plugin(
            "health_check_registry",
            settings.health_check_registry.provider,
            expected_version=BaseHealthCheckRegistry.contract_version,
        ),
    )
