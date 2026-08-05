"""健康检查：/healthz（存活探针）与 /readyz（就绪探针，依赖连通性实时探测）。

- /healthz：进程存活即 200，不检查依赖（供容器重启判断）
- /readyz：平台库 SELECT 1 + Redis PING 全部通过 200，任一失败 503（供滚动发布与流量摘除）
- 每次实时探测（Redis 操作短超时快速失败），不做缓存
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from pydantic import BaseModel

from ...db.engine import db_check
from ...db.redis import ping as redis_ping

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    """健康检查响应。"""

    status: str
    checks: dict[str, str] | None = None


@router.get("/healthz", response_model=HealthStatus)
async def healthz() -> HealthStatus:
    """存活探针：进程活着即返回 ok。"""
    return HealthStatus(status="ok")


@router.get("/readyz", response_model=HealthStatus)
async def readyz(response: Response) -> HealthStatus:
    """就绪探针：平台库与 Redis 连通性检查，任一失败返回 503。"""
    checks: dict[str, str] = {}
    db_ok = await db_check()
    checks["database"] = "ok" if db_ok else "unavailable"
    redis_ok = await redis_ping()
    checks["redis"] = "ok" if redis_ok else "unavailable"
    if db_ok and redis_ok:
        return HealthStatus(status="ok", checks=checks)
    response.status_code = 503
    return HealthStatus(status="unavailable", checks=checks)
