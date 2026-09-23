"""指标采集端点：`/metrics`（Prometheus 文本格式）。

- 挂载于服务根路径（与 `/healthz` `/readyz` 同级），**豁免**统一响应包裹 / 租户解析 / 鉴权 / 访问日志，
  供 Prometheus 直接抓取；仅内网可达（不入网关，生产按网络策略收紧）。
- 取应用装配的指标器（`app.state.metrics`）；`render()` 为 `None`（null 占位实现）时返回 404，
  不影响探针与业务。
"""

from fastapi import Request
from fastapi.responses import Response

from bms_core.api.base import BaseRouter
from bms_core.metrics.base import BaseMetrics

__all__ = ["router"]

router = BaseRouter(key="metrics", default_responses=False)
"""指标路由基座：豁免统一前缀与统一响应（`/metrics`，与探针同款）。"""


@router.get("/metrics", include_in_schema=False)
def metrics(request: Request) -> Response:
    """指标采集端点。

    Args:
        request: 当前请求（取应用装配的指标器）。

    Returns:
        Response: Prometheus 文本格式（200）；占位实现无暴露能力时 404。
    """
    metrics_impl = getattr(request.app.state, "metrics", None)
    rendered = metrics_impl.render() if isinstance(metrics_impl, BaseMetrics) else None
    if rendered is None:
        return Response(status_code=404)
    body, content_type = rendered
    return Response(content=body, media_type=content_type)
