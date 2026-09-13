"""模块注册只读路由：展示注册清单（无写接口）。"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, Request

from app.schemas.common import ApiResponse
from app.schemas.module import ModuleResponse
from app.services.module_registry import ModuleRegistry

router = APIRouter(prefix="/modules", tags=["module"])


def get_module_registry(request: Request) -> ModuleRegistry:
    """获取模块注册服务（每应用实例独立）。"""
    return cast(ModuleRegistry, request.app.state.module_registry)


RegistryDep = Annotated[ModuleRegistry, Depends(get_module_registry)]


@router.get("")
async def list_modules(
    registry: RegistryDep,
    status: Annotated[str | None, Query(description="状态筛选（enabled/disabled/planned）")] = None,
) -> ApiResponse:
    """模块注册清单（只读）。

    Args:
        registry: 模块注册服务。
        status: 状态筛选；缺省返回全部。

    Returns:
        ApiResponse: 统一响应，data 为模块记录数组。
    """
    items = registry.list_modules(status=status)
    return ApiResponse.ok([ModuleResponse.model_validate(item) for item in items])
