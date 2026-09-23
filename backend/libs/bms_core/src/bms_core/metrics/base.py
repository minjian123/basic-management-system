"""指标能力域：数值采集契约（真实 Prometheus 接入随分布式与监控阶段回补）。

- `METRIC_KINDS`：指标类型清单（计数器 / 瞬时值 / 直方图，对应 Prometheus counter / gauge / histogram）。
- `METRIC_NAMES`：候选指标名清单（按《架构设计 · 可观测性》「指标采集」节六类登记，前缀 `bms_` 统一）；
  占位期**仅登记不校验**，真实实现按此登记并允许按需扩展。
- `DEPENDENCIES`：依赖标识清单**单向复用** `app/fallback/base.py`（metrics → fallback，不反向），
  使 `bms_dependency_up` 等依赖状态类指标的 `dependency` 标签口径与降级矩阵 / 熔断域一致。
- `BaseMetrics`：能力域中间层契约（`key = "metrics"`）——异步 `counter` / `gauge` / `histogram` 三入口。
- `get_metrics`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：基座只**记录**数值（不聚合、不暴露 HTTP 端点、不做业务判定）；Prometheus 采集端点（`/metrics`）、
标签维度与分位口径随回补阶段落地，调用面零改动。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import cast

from fastapi import Request

from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.fallback.base import DEPENDENCIES

__all__ = [
    "DEPENDENCIES",
    "METRIC_KINDS",
    "METRIC_NAMES",
    "BaseMetrics",
    "MetricLabels",
    "get_metrics",
]

METRIC_KINDS: tuple[str, ...] = ("counter", "gauge", "histogram")
"""指标类型清单：计数器（单调递增）/ 瞬时值 / 直方图（延迟等分布）。"""

METRIC_NAMES: tuple[str, ...] = (
    "bms_request_total",
    "bms_request_duration_seconds",
    "bms_dependency_up",
    "bms_ws_connections",
    "bms_mq_backlog",
    "bms_ai_cost",
    "bms_boundary_cross_access_total",
)
"""候选指标名清单（架构「指标采集」节六类 + 服务边界跨库访问计数）：
请求量 / 延迟 / 依赖状态 / 实时连接数 / 消息积压 / AI 成本 / 跨库访问数。"""

MetricLabels = Mapping[str, str]
"""指标标签集（维度键值，如 `{"route": "/api/v1/users", "method": "GET"}`）。"""


class BaseMetrics(BasePluggable, ABC):
    """指标契约：计数器 / 瞬时值 / 直方图三入口。"""

    key: str = "metrics"
    plugin_key: str = "metrics"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def counter(self, name: str, *, value: float = 1.0, labels: MetricLabels | None = None) -> None:
        """记录计数器（单调递增，如请求量）。

        Args:
            name: 指标名（建议取 `METRIC_NAMES` 之一）。
            value: 增量（默认 1.0）。
            labels: 标签集（可选）。
        """

    @abstractmethod
    async def gauge(self, name: str, *, value: float, labels: MetricLabels | None = None) -> None:
        """记录瞬时值（可增可减，如实时连接数、依赖状态）。

        Args:
            name: 指标名（建议取 `METRIC_NAMES` 之一）。
            value: 当前值。
            labels: 标签集（可选）。
        """

    @abstractmethod
    async def histogram(self, name: str, *, value: float, labels: MetricLabels | None = None) -> None:
        """记录直方图观测值（如请求耗时）。

        Args:
            name: 指标名（建议取 `METRIC_NAMES` 之一）。
            value: 观测值（如秒）。
            labels: 标签集（可选）。
        """


def get_metrics(request: Request) -> BaseMetrics:
    """取应用级指标器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseMetrics: 应用装配的指标器实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseMetrics",
        resolve_plugin(
            "metrics",
            settings.metrics.provider,
            expected_version=BaseMetrics.contract_version,
        ),
    )
