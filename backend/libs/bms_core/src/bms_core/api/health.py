"""健康检查路由：/healthz 存活探针 + /readyz 就绪探针（启动完成态 + 停机摘流 + 注册表聚合）。

两探针豁免《API接口规范》「统一响应」的 `{code, message, data}` 包裹，直接返回裸结构；
HTTP 状态码保留传输层语义（就绪 200 / 未就绪或启动未完成或停机中 503），不套用「业务失败统一 200」。
两探针响应追加服务身份 `service` / `version`（由 `core/service.py` 的运行时落 `app.state.service_identity`；
未接入运行时的最小应用不附加该字段）。
"""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from bms_core.api.base import BaseRouter
from bms_core.api.deps import get_health_check_registry
from bms_core.core.service import ServiceIdentity
from bms_core.health.base import BaseHealthCheckRegistry, HealthCheckReport
from bms_core.metrics.base import BaseMetrics

router = BaseRouter(key="health", default_responses=False)
"""探针路由基座：豁免统一前缀与统一响应（`/healthz` `/readyz`，见《API接口规范》「探针豁免」）。"""

HealthCheckRegistryDep = Annotated[BaseHealthCheckRegistry, Depends(get_health_check_registry)]


def _service_fields(request: Request) -> dict[str, str]:
    """取探针响应的服务身份字段（未接入运行时的应用返回空字典）。

    Args:
        request: 当前请求。

    Returns:
        dict[str, str]: `{"service": 名, "version": 版}`；无身份时为空。
    """
    identity = getattr(request.app.state, "service_identity", None)
    if isinstance(identity, ServiceIdentity):
        return {"service": identity.name, "version": identity.version}
    return {}


@router.get("/healthz")
def healthz(request: Request) -> dict[str, object]:
    """存活检查端点。

    Args:
        request: 当前请求（取服务身份）。

    Returns:
        dict: 服务状态与身份，固定返回 {"status": "ok", "service": 名, "version": 版}。
    """
    return {"status": "ok", **_service_fields(request)}


@router.get("/readyz")
async def readyz(request: Request, registry: HealthCheckRegistryDep) -> JSONResponse:
    """就绪检查端点（启动完成态 + 停机摘流 + 注册表聚合）。

    Args:
        request: 当前请求（取应用启动完成态 / 停机摘流标记 / 服务身份）。
        registry: 健康检查项注册表（依赖注入）。

    Returns:
        JSONResponse: 全部就绪 200；未就绪、启动未完成或停机中 503。
    """
    fields = _service_fields(request)
    if getattr(request.app.state, "draining", False) or not getattr(request.app.state, "startup_complete", False):
        return JSONResponse(status_code=503, content={"status": "down", "checks": {}, **fields})

    report = await registry.aggregate()
    await _record_dependency_metrics(request, report)
    checks = {item.name: {"ok": item.ok, "error": item.error} for item in report.checks}
    return JSONResponse(
        status_code=200 if report.ok else 503,
        content={"status": "ok" if report.ok else "down", "checks": checks, **fields},
    )


async def _record_dependency_metrics(request: Request, report: HealthCheckReport) -> None:
    """记录依赖就绪指标 `bms_dependency_up`（1 就绪 / 0 未就绪；按服务 / 依赖）。

    指标写入失败不影响就绪判定（静默忽略）。

    Args:
        request: 当前请求（取应用装配的指标器）。
        report: 健康检查聚合报告。
    """
    metrics = getattr(request.app.state, "metrics", None)
    if not isinstance(metrics, BaseMetrics):
        return
    for item in report.checks:
        try:
            await metrics.gauge("bms_dependency_up", value=1.0 if item.ok else 0.0, labels={"dependency": item.name})
        except Exception:  # 指标写入绝不干扰探针
            continue
