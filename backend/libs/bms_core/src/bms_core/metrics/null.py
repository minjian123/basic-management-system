"""metrics 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 bms_core.metrics.base.py 迁入）。"""

from bms_core.core.capability import BaseNullObject
from bms_core.metrics.base import BaseMetrics, MetricLabels

__all__ = [
    "NullMetrics",
]


class NullMetrics(BaseMetrics, BaseNullObject):
    """占位指标：**空操作**（不连 Prometheus、不采集，未接入真实指标时使用）。"""

    async def counter(self, name: str, *, value: float = 1.0, labels: MetricLabels | None = None) -> None:
        """空操作（占位不采集）。

        Args:
            name: 指标名（占位忽略）。
            value: 增量（占位忽略）。
            labels: 标签集（占位忽略）。
        """

    async def gauge(self, name: str, *, value: float, labels: MetricLabels | None = None) -> None:
        """空操作（占位不采集）。

        Args:
            name: 指标名（占位忽略）。
            value: 当前值（占位忽略）。
            labels: 标签集（占位忽略）。
        """

    async def histogram(self, name: str, *, value: float, labels: MetricLabels | None = None) -> None:
        """空操作（占位不采集）。

        Args:
            name: 指标名（占位忽略）。
            value: 观测值（占位忽略）。
            labels: 标签集（占位忽略）。
        """
