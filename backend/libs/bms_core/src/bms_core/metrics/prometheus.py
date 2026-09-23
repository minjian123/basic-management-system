"""metrics 能力域真实实现：Prometheus（`prometheus-client`）。

- `PrometheusMetrics`：`BaseMetrics` 真实实现（provider `prometheus`）——把 `counter` / `gauge` /
  `histogram` 落到进程内 `CollectorRegistry`，经 `render()` 暴露 Prometheus 文本格式供 `/metrics` 采集。
- `DEFAULT_BUCKETS`：请求延迟类直方图缺省桶（5ms~10s，覆盖 Web 请求量级）。
- `SERVICE_LABEL`：服务归因标签名——实现**统一注入** `service`（架构「指标采集」按服务归因），
  调用方无需重复传递；调用方若已传同值则等价。
- `METRIC_DOCS`：候选指标名 → 文档字符串（`HELP` 文本）；未登记名回退通用文案。

口径：
- 标签基数由调用方负责有界（如 HTTP `route` 用路由模板而非原始 path）；`version` 不进指标标签，
  由 Prometheus 抓取目标外部标签 / Grafana 变量归因（避免每次发布换时间线）。
- 指标对象按 `(kind, name, labelnames)` 缓存；同名跨类型 / 跨标签集冲突**早失败**（`ValueError`），
  防静默串指标。`workers=1`（一服务一容器）下无需多进程聚合；多 worker 随扩展评估（见任务设计开放项）。
"""

from collections.abc import Mapping
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from bms_core.metrics.base import BaseMetrics, MetricLabels

__all__ = [
    "DEFAULT_BUCKETS",
    "METRIC_DOCS",
    "SERVICE_LABEL",
    "PrometheusMetrics",
]

SERVICE_LABEL = "service"
"""服务归因标签名（实现统一注入）。"""

DEFAULT_BUCKETS: tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
"""直方图缺省桶（秒；5ms~10s，覆盖 Web 请求延迟量级）。"""

METRIC_DOCS: Mapping[str, str] = {
    "bms_request_total": "HTTP 请求总数（按服务 / 方法 / 路由 / 状态码）。",
    "bms_request_duration_seconds": "HTTP 请求耗时（秒；按服务 / 方法 / 路由）。",
    "bms_dependency_up": "依赖就绪状态（1 就绪 / 0 未就绪；按服务 / 依赖）。",
    "bms_catalog_degraded": "服务目录降级状态（1 快照不可达 / 0 可达；按服务）。",
    "bms_db_count": "库数量（按服务与库类别 platform / tenant / archive）。",
    "bms_boundary_cross_access_total": "跨服务边界访问次数（按服务 / 表前缀 / 归属 / 操作）。",
    "bms_outbox_delivery_total": "发件箱投递次数（按服务 / 结果）。",
    "bms_outbox_backlog": "发件箱积压（按服务 / 库键）。",
    "bms_release_total": "服务发布次数（按服务 / 结果；CI 推送 Pushgateway）。",
    "bms_contract_breaking_total": "契约破坏性变更数（按服务；CI 推送 Pushgateway）。",
}
"""候选指标名 → HELP 文档（未登记名回退通用文案）。"""

_DEFAULT_DOC = "BMS 指标。"


class PrometheusMetrics(BaseMetrics):
    """Prometheus 指标实现：三入口落到独立 `CollectorRegistry`，`render()` 暴露采集文本。"""

    plugin_name = "prometheus"

    def __init__(self, service: str, *, registry: CollectorRegistry | None = None) -> None:
        """初始化。

        Args:
            service: 服务身份（`settings.app.service`；作为统一注入的 `service` 标签值）。
            registry: 采集注册表；缺省新建独立注册表（隔离全局默认注册表，便于多服务同进程测试）。
        """
        self._service = service
        self._registry = registry if registry is not None else CollectorRegistry()
        self._metrics: dict[tuple[str, str, tuple[str, ...]], Any] = {}

    async def counter(self, name: str, *, value: float = 1.0, labels: MetricLabels | None = None) -> None:
        """记录计数器（单调递增）。

        Args:
            name: 指标名。
            value: 增量（默认 1.0）。
            labels: 标签集（可选；`service` 由实现统一注入）。
        """
        self._record("counter", name, labels).inc(value)

    async def gauge(self, name: str, *, value: float, labels: MetricLabels | None = None) -> None:
        """记录瞬时值（可增可减）。

        Args:
            name: 指标名。
            value: 当前值。
            labels: 标签集（可选；`service` 由实现统一注入）。
        """
        self._record("gauge", name, labels).set(value)

    async def histogram(self, name: str, *, value: float, labels: MetricLabels | None = None) -> None:
        """记录直方图观测值（如请求耗时）。

        Args:
            name: 指标名。
            value: 观测值（如秒）。
            labels: 标签集（可选；`service` 由实现统一注入）。
        """
        self._record("histogram", name, labels).observe(value)

    def render(self) -> tuple[bytes, str] | None:
        """渲染 Prometheus 文本格式。

        Returns:
            tuple[bytes, str]: `(响应体, 内容类型)`。
        """
        return generate_latest(self._registry), CONTENT_TYPE_LATEST

    def _record(self, kind: str, name: str, labels: MetricLabels | None) -> Any:
        """取带标签的指标子对象（惰性建指标并按标签集固定标签名）。

        Args:
            kind: 指标类型（counter / gauge / histogram）。
            name: 指标名。
            labels: 调用方标签集（`service` 由实现注入）。

        Returns:
            Any: 已绑定标签的指标子对象（`.inc` / `.set` / `.observe`）。
        """
        merged: dict[str, str] = {SERVICE_LABEL: self._service}
        if labels:
            merged.update(labels)
        metric = self._metric(kind, name, tuple(sorted(merged)))
        return metric.labels(**merged)

    def _metric(self, kind: str, name: str, labelnames: tuple[str, ...]) -> Any:
        """取 / 建指标对象（同名跨类型或跨标签集冲突早失败）。

        Args:
            kind: 指标类型。
            name: 指标名。
            labelnames: 已排序标签名（含注入的 `service`）。

        Returns:
            Any: `prometheus_client` 指标对象。

        Raises:
            ValueError: 同名指标已按不同类型或不同标签集登记。
        """
        key = (kind, name, labelnames)
        existing = self._metrics.get(key)
        if existing is not None:
            return existing
        for other_kind, other_name, other_labels in self._metrics:
            if other_name == name and (other_kind != kind or other_labels != labelnames):
                raise ValueError(
                    f"指标 {name} 定义冲突：已登记 {other_kind}{list(other_labels)}，"
                    f"现为 {kind}{list(labelnames)}（同名指标的类型与标签集必须一致）"
                )
        doc = METRIC_DOCS.get(name, _DEFAULT_DOC)
        metric: Any
        if kind == "counter":
            metric = Counter(name, doc, labelnames=list(labelnames), registry=self._registry)
        elif kind == "gauge":
            metric = Gauge(name, doc, labelnames=list(labelnames), registry=self._registry)
        elif kind == "histogram":
            metric = Histogram(name, doc, labelnames=list(labelnames), buckets=DEFAULT_BUCKETS, registry=self._registry)
        else:  # pragma: no cover - 类型白名单由 METRIC_KINDS 约束
            raise ValueError(f"未知指标类型：{kind}")
        self._metrics[key] = metric
        return metric
