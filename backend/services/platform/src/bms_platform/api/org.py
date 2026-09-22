"""组织主数据占位路由：`/api/v1/org`（登录即可；真实取数 / 数据范围 / 脱敏随 RBAC 阶段）。

- 用户 / 岗位查询 `GET /org/users` `/org/posts`（关键字 / 部门 / 含子级 / 状态 / 分页）。
- 部门树 `GET /org/dept-tree`（一次性返回、不分页）。
- 批量回显 `GET /org/resolve-names`（`id_in` 逗号分隔，按 id 批量取名称）。
- 契约口径见 `app/org/base.py`：数据范围与脱敏实现侧强制接入，调用方不可绕过。
"""

from typing import Annotated

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, require_auth
from bms_core.api.deps import get_masker, get_org_data_source, get_org_name_resolver
from bms_core.core.exceptions import ParamError
from bms_core.org.base import (
    DEFAULT_ORG_PAGE_SIZE,
    BaseOrgDataSource,
    BaseOrgNameResolver,
    OrgDept,
    OrgNameRef,
    OrgPost,
    OrgUser,
)
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageResponse

router = BaseRouter(
    key="org",
    prefix="/org",
    tags=["org"],
    dependencies=[Depends(require_auth), Depends(get_masker)],
)

DataSourceDep = Annotated[BaseOrgDataSource, Depends(get_org_data_source)]
NameResolverDep = Annotated[BaseOrgNameResolver, Depends(get_org_name_resolver)]


def parse_id_in(raw: str) -> list[int]:
    """解析逗号分隔的 id 列表（`id_in=1,2,3`）。

    Args:
        raw: 逗号分隔字符串。

    Returns:
        list[int]: id 列表。

    Raises:
        ParamError: 含非整数项（10001）。
    """
    try:
        return [int(part) for part in raw.split(",") if part.strip()]
    except ValueError as exc:
        raise ParamError("id_in 应为逗号分隔的整数列表") from exc


@router.get("/users")
async def list_org_users(
    service: DataSourceDep,
    keyword: Annotated[str | None, Query(description="关键字（用户名 / 昵称 / 手机号）")] = None,
    dept_id: Annotated[int | None, Query(description="归属部门 ID")] = None,
    include_children: Annotated[bool, Query(description="部门过滤是否含下级")] = False,
    status: Annotated[str | None, Query(description="状态过滤（enabled / disabled）")] = None,
    page: Annotated[int, Query(ge=1, description="页码（从 1 起）")] = 1,
    size: Annotated[int, Query(ge=1, le=200, description="每页条数")] = DEFAULT_ORG_PAGE_SIZE,
) -> ApiResponse:
    """查询组织用户（关键字 / 部门 / 含子级 / 状态 / 分页）。

    Args:
        service: 组织查询契约。
        keyword: 关键字。
        dept_id: 归属部门 ID。
        include_children: 部门过滤是否含下级。
        status: 状态过滤。
        page: 页码。
        size: 每页条数。

    Returns:
        ApiResponse: 统一响应，data 为分页用户。
    """
    result: BasePageResponse[OrgUser] = await service.users(
        keyword, dept_id=dept_id, include_children=include_children, status=status, page=page, size=size
    )
    return ApiResponse.ok(result)


@router.get("/posts")
async def list_org_posts(
    service: DataSourceDep,
    keyword: Annotated[str | None, Query(description="关键字（岗位编码 / 名称）")] = None,
    dept_id: Annotated[int | None, Query(description="归属部门 ID")] = None,
    include_children: Annotated[bool, Query(description="部门过滤是否含下级")] = False,
    status: Annotated[str | None, Query(description="状态过滤（enabled / disabled）")] = None,
    page: Annotated[int, Query(ge=1, description="页码（从 1 起）")] = 1,
    size: Annotated[int, Query(ge=1, le=200, description="每页条数")] = DEFAULT_ORG_PAGE_SIZE,
) -> ApiResponse:
    """查询组织岗位（关键字 / 部门 / 含子级 / 状态 / 分页）。

    Args:
        service: 组织查询契约。
        keyword: 关键字。
        dept_id: 归属部门 ID。
        include_children: 部门过滤是否含下级。
        status: 状态过滤。
        page: 页码。
        size: 每页条数。

    Returns:
        ApiResponse: 统一响应，data 为分页岗位。
    """
    result: BasePageResponse[OrgPost] = await service.posts(
        keyword, dept_id=dept_id, include_children=include_children, status=status, page=page, size=size
    )
    return ApiResponse.ok(result)


@router.get("/dept-tree")
async def get_org_dept_tree(
    service: DataSourceDep,
    status: Annotated[str | None, Query(description="状态过滤（enabled / disabled）")] = None,
) -> ApiResponse:
    """取部门树（一次性返回、不分页）。

    Args:
        service: 组织查询契约。
        status: 状态过滤。

    Returns:
        ApiResponse: 统一响应，data 为部门树根节点序列。
    """
    tree: tuple[OrgDept, ...] = tuple(await service.dept_tree(status=status))
    return ApiResponse.ok(tree)


@router.get("/resolve-names")
async def resolve_org_names(
    service: NameResolverDep,
    id_in: Annotated[str, Query(description="对象 ID 列表（逗号分隔，如 1,2,3）")],
    target: Annotated[str, Query(description="目标类型（user / post / dept）")] = "user",
) -> ApiResponse:
    """按 id 批量回显名称（避免 N+1）。

    Args:
        service: 组织回显契约。
        id_in: 逗号分隔的 id 列表。
        target: 目标类型。

    Returns:
        ApiResponse: 统一响应，data 为回显项序列。
    """
    refs: tuple[OrgNameRef, ...] = tuple(await service.resolve_names(target, parse_id_in(id_in)))
    return ApiResponse.ok(refs)
