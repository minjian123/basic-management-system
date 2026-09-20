"""健康检查路由：/healthz 存活探针 + /readyz 就绪探针（启动完成态判定 + 注册表聚合）。

两探针豁免《API接口规范》「统一响应」的 `{code, message, data}` 包裹，直接返回裸结构；
HTTP 状态码保留传输层语义（就绪 200 / 未就绪或启动未完成 503），不套用「业务失败统一 200」。
"""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from app.api.base import BaseRouter
from app.api.deps import get_health_check_registry
from app.health.base import BaseHealthCheckRegistry

router = BaseRouter(key="health", default_responses=False)
"""探针路由基座：豁免统一前缀与统一响应（`/healthz` `/readyz`，见《API接口规范》「探针豁免」）。"""

HealthCheckRegistryDep = Annotated[BaseHealthCheckRegistry, Depends(get_health_check_registry)]


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """存活检查端点。

    Returns:
        dict: 服务状态，固定返回 {"status": "ok"}。
    """
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request, registry: HealthCheckRegistryDep) -> JSONResponse:
    """就绪检查端点（启动完成态 + 注册表聚合）。

    Args:
        request: 当前请求（取应用启动完成态）。
        registry: 健康检查项注册表（依赖注入）。

    Returns:
        JSONResponse: 全部就绪 200；未就绪或启动未完成 503。
    """
    if not getattr(request.app.state, "startup_complete", False):
        return JSONResponse(status_code=503, content={"status": "down", "checks": {}})

    report = await registry.aggregate()
    checks = {item.name: {"ok": item.ok, "error": item.error} for item in report.checks}
    return JSONResponse(
        status_code=200 if report.ok else 503,
        content={"status": "ok" if report.ok else "down", "checks": checks},
    )
