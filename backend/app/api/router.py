"""api 聚合路由：业务模块路由登记 → 统一挂载到 `/api/v1`；探针路由豁免前缀，单独挂根路径。"""

from fastapi import APIRouter

from app.api import demo, health, modules, notification, plugins, preference, query_scheme
from app.api.base import build_api_router, register_router

for _module in (demo, modules, plugins, preference, query_scheme, notification):
    register_router(_module.router)

api_router = build_api_router()

health_router = APIRouter()
health_router.include_router(health.router)
