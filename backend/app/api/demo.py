"""demo 示例模块路由：展示四件套调用链与统一响应。"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request

from app.schemas.common import ApiResponse
from app.schemas.demo import DemoCreateRequest, DemoResponse, DemoUpdateRequest
from app.services.demo_service import DemoService

router = APIRouter(prefix="/demos", tags=["demo"])


def get_demo_service(request: Request) -> DemoService:
    """获取 demo 服务（每应用实例独立；02-5 起改为依赖注入）。"""
    return cast(DemoService, request.app.state.demo_service)


DemoDep = Annotated[DemoService, Depends(get_demo_service)]


@router.post("")
def create_demo(req: DemoCreateRequest, service: DemoDep) -> ApiResponse:
    """创建 demo。

    Returns:
        ApiResponse: 统一响应，data 为 {id, name}。
    """
    demo = service.create_demo(req.name)
    return ApiResponse.ok(DemoResponse(id=demo.id, name=demo.name))


@router.get("")
def list_demos(service: DemoDep) -> ApiResponse:
    """demo 列表。

    Returns:
        ApiResponse: 统一响应，data 为记录数组。
    """
    return ApiResponse.ok([DemoResponse(id=item.id, name=item.name) for item in service.list_demos()])


@router.get("/{demo_id}")
def get_demo(demo_id: int, service: DemoDep) -> ApiResponse:
    """demo 详情。

    Args:
        demo_id: 记录 ID。

    Returns:
        ApiResponse: 统一响应，data 为 {id, name}。

    Raises:
        NotFoundError: 记录不存在（全局处理器转 404）。
    """
    demo = service.get_demo(demo_id)
    return ApiResponse.ok(DemoResponse(id=demo.id, name=demo.name))


@router.put("/{demo_id}")
def update_demo(demo_id: int, req: DemoUpdateRequest, service: DemoDep) -> ApiResponse:
    """更新 demo 名称。

    Args:
        demo_id: 记录 ID。
        req: 更新请求。

    Returns:
        ApiResponse: 统一响应，data 为 {id, name}。

    Raises:
        NotFoundError: 记录不存在（全局处理器转 404）。
    """
    demo = service.update_demo(demo_id, req.name)
    return ApiResponse.ok(DemoResponse(id=demo.id, name=demo.name))


@router.delete("/{demo_id}")
def delete_demo(demo_id: int, service: DemoDep) -> ApiResponse:
    """删除 demo。

    Args:
        demo_id: 记录 ID。

    Returns:
        ApiResponse: 统一响应，data 为 null。

    Raises:
        NotFoundError: 记录不存在（全局处理器转 404）。
    """
    service.delete_demo(demo_id)
    return ApiResponse.ok()
