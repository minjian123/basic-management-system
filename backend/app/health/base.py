"""健康检查能力域：依赖就绪检查项注册表契约与占位实现（真实 DB / Redis / MinIO 探针随 03_03 健康检查阶段回补）。

- `DEPENDENCIES`：依赖标识清单**单向复用** `app/fallback/base.py`（health → fallback，不反向），
  使依赖类检查项的 `name` 与降级矩阵 / 熔断 / 指标口径一致（如 `"database"` / `"redis"` / `"minio"`）。
- `HealthCheckResult` / `HealthCheckReport`：单项结果与聚合报告数据契约（frozen dataclass）。
- `BaseHealthCheck`：检查项契约——`name`（抽象属性）+ 异步 `check()`。
- `BaseHealthCheckRegistry`：能力域中间层契约（`key = "health_check_registry"`）——抽象 `register` / `checks`；
  `aggregate` 为**具体聚合模板**（遍历 → 逐项检查 → 收集 → 汇总），异常兜底与空集语义单点收敛。
- `NullHealthCheckRegistry`：占位实现——注册空操作、无检查项 → 固定通过（`healthy=True`、`items=()`），**不探依赖**。
- `get_health_check_registry`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：本域只回答「依赖是否就绪」（供 `/readyz` 聚合），不执行降级动作（归 `BaseFallbackPolicy`）；
真实探针（连接对象 / 超时 / 缓存）随回补阶段落地，契约与调用面零改动。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.fallback.base import DEPENDENCIES

__all__ = [
    "DEPENDENCIES",
    "BaseHealthCheck",
    "BaseHealthCheckRegistry",
    "HealthCheckReport",
    "HealthCheckResult",
    "NullHealthCheckRegistry",
    "get_health_check_registry",
]


@dataclass(frozen=True)
class HealthCheckResult(BaseObject):
    """单项健康检查结果。"""

    name: str
    """检查项名称（依赖类检查项建议取 `DEPENDENCIES` 之一）。"""

    healthy: bool
    """是否健康（就绪）。"""

    detail: str | None = None
    """补充说明（可选，人类可读）。"""


@dataclass(frozen=True)
class HealthCheckReport(BaseObject):
    """聚合报告：各检查项结果与总体就绪。"""

    healthy: bool
    """总体是否就绪（全部检查项通过）。"""

    items: tuple[HealthCheckResult, ...] = ()
    """各检查项结果（注册顺序，稳定）。"""


class BaseHealthCheck(BaseObject, ABC):
    """检查项契约：名称 + 异步检查。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """检查项名称（依赖类检查项建议取 `DEPENDENCIES` 之一）。"""

    @abstractmethod
    async def check(self) -> HealthCheckResult:
        """执行检查。

        Returns:
            HealthCheckResult: 单项检查结果。
        """


class BaseHealthCheckRegistry(BaseCapability, ABC):
    """注册表契约：登记检查项 + 聚合就绪。"""

    key: str = "health_check_registry"

    @abstractmethod
    def register(self, check: BaseHealthCheck) -> None:
        """登记检查项（启动期注册，无 IO）。

        Args:
            check: 检查项。
        """

    @abstractmethod
    def checks(self) -> tuple[BaseHealthCheck, ...]:
        """已登记检查项（注册顺序）。

        Returns:
            tuple[BaseHealthCheck, ...]: 检查项元组。
        """

    async def aggregate(self) -> HealthCheckReport:
        """聚合全部检查项为就绪报告（模板方法：单项异常不中断聚合）。

        Returns:
            HealthCheckReport: 聚合报告；空注册表视为就绪（`healthy=True`）。
        """
        results: list[HealthCheckResult] = []
        for check in self.checks():
            try:
                results.append(await check.check())
            except Exception:
                results.append(HealthCheckResult(name=check.name, healthy=False, detail="检查执行异常"))
        return HealthCheckReport(healthy=all(result.healthy for result in results), items=tuple(results))


class NullHealthCheckRegistry(BaseHealthCheckRegistry, BaseNullObject):
    """占位注册表：注册空操作、无检查项 → 固定通过（不探依赖，未接入真实探针时使用）。"""

    def register(self, check: BaseHealthCheck) -> None:
        """空操作（占位不登记）。

        Args:
            check: 检查项（占位忽略）。
        """

    def checks(self) -> tuple[BaseHealthCheck, ...]:
        """空检查项集。

        Returns:
            tuple[BaseHealthCheck, ...]: 空元组。
        """
        return ()


def get_health_check_registry(request: Request) -> BaseHealthCheckRegistry:
    """取应用级健康检查注册表（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseHealthCheckRegistry: 应用装配的注册表实例。
    """
    return cast("BaseHealthCheckRegistry", request.app.state.health_check_registry)
