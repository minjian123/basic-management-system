"""平台服务端点：`/api/v1/users`（最小用户只读查询）。

- **鉴权**：模块级 `require_auth`；读挂 `user:query`（当前 `NullPermissionChecker` 恒放行，
  `02_04` 注入真实检查器后自动收口）；
- **库**：`sys_user` 在 **platform 服务租户库**（`get_uow`）；本端点与角色分配
  （`sys_user_role`）**同库**，供「选择用户」弹窗与已分配列表回显；
- **范围**：只返回最小字段（`id` / `username` / `name` / `status`），
  用户完整域 CRUD / 启停 / 重置密码归 `02_01`（届时在同一路由扩展）；
- **契约**：计入 platform 公开契约（`deploy/contracts/platform.json`）。
"""

from typing import Annotated, cast

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import get_uow
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery, BasePageResponse
from bms_platform.models.user import SysUser
from bms_platform.repositories.user import UserRepository
from bms_platform.schemas.users import UserItem
from bms_platform.services.users import USER_STATUSES, UserQueryService

router = BaseRouter(
    key="platform_users",
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_auth)],
)

UowDep = Annotated[UnitOfWork, Depends(get_uow)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
KeywordQuery = Annotated[str | None, Query(description="关键字（账号 / 姓名）")]
StatusQuery = Annotated[str | None, Query(description="账号状态（enabled/disabled）")]

_REQUIRE_QUERY = Depends(require_permission("user:query"))


def _require_status(status: str | None) -> None:
    """校验状态筛选值。

    Args:
        status: 状态（可空）。

    Raises:
        ParamError: 取值非法（10001）。
    """
    if status is not None and status not in USER_STATUSES:
        raise ParamError(f"账号状态非法：{status}")


def _user_item(row: SysUser) -> UserItem:
    """用户记录 → 最小查询行。

    Args:
        row: 用户记录。

    Returns:
        UserItem: 最小用户查询行。
    """
    return UserItem(id=row.id, username=row.username, name=row.name, status=row.status)


@router.get("", dependencies=[_REQUIRE_QUERY])
async def list_users(
    query: PageDep,
    uow: UowDep,
    kw: KeywordQuery = None,
    status: StatusQuery = None,
) -> ApiResponse[BasePageResponse[UserItem]]:
    """用户最小字段列表（账号 / 姓名关键字与状态筛选 + 分页）。

    Args:
        query: 分页与排序参数。
        uow: 请求级工作单元。
        kw: 关键字（账号 / 姓名）。
        status: 账号状态（enabled/disabled）。

    Returns:
        ApiResponse: 统一响应，data 为分页用户列表（最小字段）。
    """
    _require_status(status)
    service = UserQueryService(UserRepository(cast("DbSession", uow.session)))
    rows, total = await service.list_users(query, keyword=kw, status=status)
    items = ConcurrentStableList(_user_item(row) for row in rows)
    return ApiResponse.ok(BasePageResponse[UserItem](list=items, total=total, page=query.page, size=query.size))
