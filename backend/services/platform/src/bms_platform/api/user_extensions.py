"""平台服务用户扩展信息端点：`/api/v1/user-extensions`（按用户列列表 + 新增 / 更新一条）。

- **鉴权**：模块级 `require_auth`；读挂 `require_permission("sys:user-extension:query")`、
  写挂 `require_permission("sys:user-extension:update")`（permission 基座当前为 Null = RBAC 前
  平台超管口径，RBAC 就绪后自动收口）。
- **租户**：由登录态解析租户，`get_uow` 取 platform 服务租户库会话（与字典 / 系统参数同口径）。
- **契约**：具名插槽样例插件的后端契约面（插件前端经宿主注入 `api` 按服务键 `platform` 调用）；
  计入 platform 公开契约（`deploy/contracts/platform.json`）；新增端点属非破坏性变更。
"""

from typing import Annotated, cast

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, require_auth
from bms_core.api.deps import get_uow
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_platform.models.system import SysUserExtension
from bms_platform.repositories.user_extension import UserExtensionRepository
from bms_platform.schemas.user_extension import (
    UserExtensionCreateRequest,
    UserExtensionItem,
    UserExtensionList,
    UserExtensionUpdateRequest,
)
from bms_platform.services.user_extension import UserExtensionService

router = BaseRouter(
    key="sys_user_extensions",
    prefix="/user-extensions",
    tags=["user-extensions"],
    dependencies=[Depends(require_auth)],
)

UowDep = Annotated[UnitOfWork, Depends(get_uow)]
UserIdQuery = Annotated[int, Query(gt=0, description="用户主键（必填）")]

_REQUIRE_QUERY = Depends(require_permission("sys:user-extension:query"))
_REQUIRE_UPDATE = Depends(require_permission("sys:user-extension:update"))


def _service(uow: UowDep) -> UserExtensionService:
    """构造用户扩展信息服务（请求级会话）。

    Args:
        uow: 请求级工作单元。

    Returns:
        UserExtensionService: 用户扩展信息服务实例。
    """
    session = cast("DbSession", uow.session)
    return UserExtensionService(UserExtensionRepository(session), uow)


def _to_item(row: SysUserExtension) -> UserExtensionItem:
    """扩展信息记录 → 契约。

    Args:
        row: 扩展信息记录。

    Returns:
        UserExtensionItem: 扩展信息行契约。
    """
    return UserExtensionItem(
        id=row.id,
        user_id=row.user_id,
        label=row.label,
        remark=row.remark,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", dependencies=[_REQUIRE_QUERY])
async def list_user_extensions(user_id: UserIdQuery, uow: UowDep) -> ApiResponse[UserExtensionList]:
    """按用户列示扩展信息。

    Args:
        user_id: 用户主键。
        uow: 请求级工作单元。

    Returns:
        ApiResponse: 统一响应，data 为扩展信息列表（保序）。
    """
    rows = await _service(uow).list_by_user(user_id)
    return ApiResponse.ok(UserExtensionList(items=ConcurrentStableList(_to_item(row) for row in rows)))


@router.post("", dependencies=[_REQUIRE_UPDATE])
async def create_user_extension(req: UserExtensionCreateRequest, uow: UowDep) -> ApiResponse[UserExtensionItem]:
    """新增一条扩展信息（同用户同标签冲突即拒绝）。

    Args:
        req: 新增请求（用户主键 + 标签 + 备注）。
        uow: 请求级工作单元。

    Returns:
        ApiResponse: 统一响应，data 为扩展信息行。

    Raises:
        ConflictError: 同用户同标签已存在（10003）。
    """
    row = await _service(uow).create_extension(user_id=req.user_id, label=req.label, remark=req.remark)
    return ApiResponse.ok(_to_item(row))


@router.put("/{extension_id}", dependencies=[_REQUIRE_UPDATE])
async def update_user_extension(
    extension_id: int, req: UserExtensionUpdateRequest, uow: UowDep
) -> ApiResponse[UserExtensionItem]:
    """更新一条扩展信息（整体替换标签与备注）。

    Args:
        extension_id: 扩展信息主键。
        req: 更新请求（标签 + 备注）。
        uow: 请求级工作单元。

    Returns:
        ApiResponse: 统一响应，data 为更新后的扩展信息行。

    Raises:
        NotFoundError: 记录不存在（10002）。
        ConflictError: 改后与既有行同标签（10003）。
    """
    row = await _service(uow).update_extension(extension_id, label=req.label, remark=req.remark)
    return ApiResponse.ok(_to_item(row))
