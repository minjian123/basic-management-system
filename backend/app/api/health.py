"""健康检查路由：/healthz 存活探针 + /readyz 就绪探针（走健康检查项注册表聚合）。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.deps import get_health_check_registry
from app.health.base import BaseHealthCheckRegistry

router = APIRouter()

HealthCheckRegistryDep = Annotated[BaseHealthCheckRegistry, Depends(get_health_check_registry)]


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """存活检查端点。

    Returns:
        dict: 服务状态，固定返回 {"status": "ok"}。
    """
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(registry: HealthCheckRegistryDep) -> JSONResponse:
    """就绪检查端点（经注册表聚合依赖检查项）。

    Args:
        registry: 健康检查项注册表（依赖注入）。

    Returns:
        JSONResponse: 全部就绪返回 200、否则返回 503。
    """
    report = await registry.aggregate()
    payload: dict[str, object] = {
        "status": "ok" if report.healthy else "degraded",
        "checks": [{"name": item.name, "healthy": item.healthy, "detail": item.detail} for item in report.items],
    }
    return JSONResponse(status_code=200 if report.healthy else 503, content=payload)
