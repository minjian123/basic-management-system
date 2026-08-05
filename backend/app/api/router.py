"""全局路由注册：/api/v1 前缀下挂载各模块路由（健康检查走根路径，见 main.py）。"""

from __future__ import annotations

from fastapi import APIRouter

from .v1 import system

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
