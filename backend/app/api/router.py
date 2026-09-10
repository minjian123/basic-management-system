"""api 聚合路由：业务路由挂 /api/v1，探针路由挂根路径。"""

from fastapi import APIRouter

from app.api import demo, health

api_router = APIRouter()
api_router.include_router(demo.router)

health_router = APIRouter()
health_router.include_router(health.router)
