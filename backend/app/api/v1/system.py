"""系统信息接口（调试用）：应用名、环境与版本。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ...core.config import get_settings
from ...schemas.common import ApiResponse, ok

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/info", response_model=ApiResponse[dict[str, Any]])
async def system_info() -> ApiResponse[dict[str, Any]]:
    """返回应用基本信息（版本号随发布维护）。"""
    settings = get_settings()
    return ok({"name": settings.app.name, "env": settings.app.env, "version": "0.1.0"})
