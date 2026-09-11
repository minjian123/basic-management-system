"""demo 示例模块路由：展示四件套调用链与统一响应占位。"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request

from app.schemas.demo import DemoCreateRequest, DemoResponse, DemoUpdateRequest
from app.services.demo_service import DemoService

router = APIRouter(prefix="/demos", tags=["demo"])


def get_demo_service(request: Request) -> DemoService:
    """获取 demo 服务（每应用实例独立；02-5 起改为依赖注入）。"""
    return cast(DemoService, request.app.state.demo_service)


DemoDep = Annotated[DemoService, Depends(get_demo_service)]


def _ok(data: object) -> dict[str, object]:
    """统一响应占位（02-3 起换用 ApiResponse）。"""
    return {"code": 0, "message": "ok", "data": data}


@router.post("")
def create_demo(req: DemoCreateRequest, service: DemoDep) -> dict[str, object]:
    """创建 demo。

    Returns:
        dict: 统一响应，data 为 {id, name}。
    """
    demo = service.create_demo(req.name)
    return _ok(DemoResponse(id=demo.id, name=demo.name).model_dump())


@router.get("")
def list_demos(service: DemoDep) -> dict[str, object]:
    """demo 列表。

    Returns:
        dict: 统一响应，data 为记录数组。
    """
    return _ok([DemoResponse(id=item.id, name=item.name).model_dump() for item in service.list_demos()])


@router.get("/{demo_id}")
def get_demo(demo_id: int, service: DemoDep) -> dict[str, object]:
    """demo 详情。

    Args:
        demo_id: 记录 ID。

    Returns:
        dict: 统一响应，data 为 {id, name}。

    Raises:
        NotFoundError: 记录不存在（全局处理器转 404）。
    """
    demo = service.get_demo(demo_id)
    return _ok(DemoResponse(id=demo.id, name=demo.name).model_dump())


@router.put("/{demo_id}")
def update_demo(demo_id: int, req: DemoUpdateRequest, service: DemoDep) -> dict[str, object]:
    """更新 demo 名称。

    Args:
        demo_id: 记录 ID。
        req: 更新请求。

    Returns:
        dict: 统一响应，data 为 {id, name}。

    Raises:
        NotFoundError: 记录不存在（全局处理器转 404）。
    """
    demo = service.update_demo(demo_id, req.name)
    return _ok(DemoResponse(id=demo.id, name=demo.name).model_dump())


@router.delete("/{demo_id}")
def delete_demo(demo_id: int, service: DemoDep) -> dict[str, object]:
    """删除 demo。

    Args:
        demo_id: 记录 ID。

    Returns:
        dict: 统一响应，data 为 null。

    Raises:
        NotFoundError: 记录不存在（全局处理器转 404）。
    """
    service.delete_demo(demo_id)
    return _ok(None)
