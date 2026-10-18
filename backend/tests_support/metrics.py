"""测试用指标出口（记录调用；单测零依赖，05_07 恢复器 / 协调器指标用例共用）。"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.metrics.base import BaseMetrics, MetricLabels

__all__ = ["RecordingMetrics"]


class RecordingMetrics(BaseMetrics):
    """指标出口替身：按记录顺序保留每次 `counter` / `gauge` 调用（含标签）。"""

    plugin_name = "recording"

    def __init__(self) -> None:
        """初始化。"""
        self.counters: ConcurrentStableList[tuple[str, float, MetricLabels | None]] = ConcurrentStableList()
        self.gauges: ConcurrentStableList[tuple[str, float]] = ConcurrentStableList()

    async def counter(self, name: str, *, value: float = 1.0, labels: MetricLabels | None = None) -> None:
        """记录计数器。

        Args:
            name: 指标名。
            value: 增量。
            labels: 标签集。
        """
        self.counters.add((name, value, labels))

    async def gauge(self, name: str, *, value: float, labels: MetricLabels | None = None) -> None:
        """记录瞬时值。

        Args:
            name: 指标名。
            value: 当前值。
            labels: 标签集（本替身不记录）。
        """
        del labels
        self.gauges.add((name, value))

    async def histogram(self, name: str, *, value: float, labels: MetricLabels | None = None) -> None:
        """记录直方图（本域未使用）。

        Args:
            name: 指标名。
            value: 观测值。
            labels: 标签集。
        """
        del name, value, labels

    def counter_values(self, name: str) -> ConcurrentStableList[float]:
        """取某指标名的计数增量序列（按记录顺序）。

        Args:
            name: 指标名。

        Returns:
            ConcurrentStableList[float]: 增量序列。
        """
        return ConcurrentStableList(value for recorded, value, _labels in self.counters if recorded == name)

    def labels_of(self, name: str) -> ConcurrentStableList[MetricLabels | None]:
        """取某指标名的标签序列（按记录顺序）。

        Args:
            name: 指标名。

        Returns:
            ConcurrentStableList[MetricLabels | None]: 标签序列。
        """
        return ConcurrentStableList(labels for recorded, _value, labels in self.counters if recorded == name)
