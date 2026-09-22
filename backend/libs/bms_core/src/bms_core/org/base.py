"""组织主数据查询能力域：组织查询与批量回显两契约（真实取数随 RBAC 阶段回补）。

- 常量：组织状态 `ORG_STATUSES`（enabled / disabled）、回显目标 `ORG_TARGETS`（user / post / dept）、
  默认每页条数 `DEFAULT_ORG_PAGE_SIZE`。
- 数据契约：`OrgUser` / `OrgPost` / `OrgDept`（嵌套部门树）/ `OrgNameRef`（批量回显项）。
- `BaseOrgDataSource`（`key = "org_data_source"`）：异步 `users` / `posts`（关键字 / 部门 / 含子级 /
  状态 / 分页）+ `dept_tree`（不分页一次性返回）。
- `BaseOrgNameResolver`（`key = "org_name_resolver"`）：异步 `resolve_names(target, ids)` 按 id 批量回显名称。
- 提供者 `get_org_data_source` / `get_org_name_resolver`（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：**租户隔离与动作级数据范围过滤由实现侧经 02-13 `DataScope` 注入、字段脱敏经 02-29 `BaseMasker`
统一接入，契约方法不显式传租户 / 数据范围参数，调用方不可绕过**；`OrgUser.masked_fields` 声明手机号 /
邮箱为敏感字段（序列化自动掩码，持 `data:plain` 权限方可看明文）。部门树一次性返回、不分页；已删除 /
停用对象不抛错，由 `OrgNameRef.exists` / `status` 标记（前端回退展示 id）。业务与前端只经本出口取数，
**不直连组织模块的表**。真实取数 / 分页 / 子树展开 / 数据范围 / 脱敏 / 权限码随 RBAC 与组织模块阶段。
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import cast

from fastapi import Request
from pydantic import Field

from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.schemas.base import BaseSchema
from bms_core.schemas.pagination import BasePageResponse

__all__ = [
    "DEFAULT_ORG_PAGE_SIZE",
    "ORG_STATUSES",
    "ORG_TARGETS",
    "BaseOrgDataSource",
    "BaseOrgNameResolver",
    "OrgDept",
    "OrgNameRef",
    "OrgPost",
    "OrgUser",
    "get_org_data_source",
    "get_org_name_resolver",
]

ORG_STATUSES: tuple[str, ...] = ("enabled", "disabled")
"""组织对象状态（用户 / 岗位 / 部门共用；`enabled` 启用 / `disabled` 停用）。"""

ORG_TARGETS: tuple[str, ...] = ("user", "post", "dept")
"""批量回显目标类型（用户 / 岗位 / 部门）。"""

DEFAULT_ORG_PAGE_SIZE = 20
"""组织列表默认每页条数（对齐前端 06_05 下拉限制条数）。"""


class OrgUser(BaseSchema):
    """组织用户（展示所需最小字段；手机号 / 邮箱默认脱敏）。"""

    masked_fields = frozenset({"phone", "email"})
    """敏感字段（经 02-29 掩码器序列化自动掩码；持 `data:plain` 权限方可看明文）。"""

    id: int = Field(description="用户 ID")
    username: str = Field(description="用户名")
    nickname: str = Field(default="", description="昵称")
    dept_id: int | None = Field(default=None, description="归属部门 ID")
    status: str = Field(default="enabled", description="状态（enabled / disabled）")
    avatar: str | None = Field(default=None, description="头像地址")
    phone: str | None = Field(default=None, description="手机号（默认脱敏）")
    email: str | None = Field(default=None, description="邮箱（默认脱敏）")


class OrgPost(BaseSchema):
    """组织岗位（展示所需最小字段）。"""

    id: int = Field(description="岗位 ID")
    code: str = Field(description="岗位编码")
    name: str = Field(description="岗位名称")
    dept_id: int | None = Field(default=None, description="归属部门 ID")
    status: str = Field(default="enabled", description="状态（enabled / disabled）")
    sort: int = Field(default=0, description="排序值")


class OrgDept(BaseSchema):
    """组织部门（嵌套树节点；部门树一次性返回、不分页）。"""

    id: int = Field(description="部门 ID")
    parent_id: int | None = Field(default=None, description="父部门 ID（None＝根）")
    name: str = Field(description="部门名称")
    sort: int = Field(default=0, description="排序值")
    status: str = Field(default="enabled", description="状态（enabled / disabled）")
    children: list[OrgDept] = Field(default_factory=list["OrgDept"], description="子部门（嵌套树）")


class OrgNameRef(BaseSchema):
    """批量回显项（按 id 回显名称；已删除 / 停用不抛错，以字段标记）。"""

    id: int = Field(description="对象 ID")
    name: str = Field(description="对象名称（不存在时为占位名）")
    target: str = Field(default="user", description="目标类型（user / post / dept）")
    exists: bool = Field(default=True, description="对象是否存在")
    status: str = Field(default="enabled", description="状态（enabled / disabled）")


class BaseOrgDataSource(BasePluggable, ABC):
    """组织主数据查询契约：用户 / 岗位查询与部门树取数。"""

    key: str = "org_data_source"
    plugin_key: str = "org_data_source"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def users(
        self,
        keyword: str | None = None,
        *,
        dept_id: int | None = None,
        include_children: bool = False,
        status: str | None = None,
        page: int = 1,
        size: int = DEFAULT_ORG_PAGE_SIZE,
    ) -> BasePageResponse[OrgUser]:
        """查询用户（关键字 / 部门 / 含子级 / 状态 / 分页）。

        Args:
            keyword: 关键字（用户名 / 昵称 / 手机号，命中列由实现定义）；None 不过滤。
            dept_id: 归属部门 ID；None 不过滤。
            include_children: 部门过滤是否含下级（实现按 `sys_dept.ancestors` 展开子树）。
            status: 状态过滤（`ORG_STATUSES` 之一）；None 不过滤。
            page: 页码（从 1 起）。
            size: 每页条数。

        Returns:
            BasePageResponse[OrgUser]: 分页用户（数据范围与脱敏由实现侧强制接入）。
        """

    @abstractmethod
    async def posts(
        self,
        keyword: str | None = None,
        *,
        dept_id: int | None = None,
        include_children: bool = False,
        status: str | None = None,
        page: int = 1,
        size: int = DEFAULT_ORG_PAGE_SIZE,
    ) -> BasePageResponse[OrgPost]:
        """查询岗位（关键字 / 部门 / 含子级 / 状态 / 分页）。

        Args:
            keyword: 关键字（岗位编码 / 名称，命中列由实现定义）；None 不过滤。
            dept_id: 归属部门 ID；None 不过滤。
            include_children: 部门过滤是否含下级。
            status: 状态过滤（`ORG_STATUSES` 之一）；None 不过滤。
            page: 页码（从 1 起）。
            size: 每页条数。

        Returns:
            BasePageResponse[OrgPost]: 分页岗位（数据范围由实现侧强制接入）。
        """

    @abstractmethod
    async def dept_tree(self, *, status: str | None = None) -> Sequence[OrgDept]:
        """取部门树（一次性返回、不分页）。

        Args:
            status: 状态过滤（`ORG_STATUSES` 之一）；None 不过滤。

        Returns:
            Sequence[OrgDept]: 部门树根节点序列（`children` 嵌套）。
        """


class BaseOrgNameResolver(BasePluggable, ABC):
    """组织主数据回显契约：按标识批量回显名称（避免 N+1）。"""

    key: str = "org_name_resolver"
    plugin_key: str = "org_name_resolver"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def resolve_names(self, target: str, ids: Sequence[int]) -> Sequence[OrgNameRef]:
        """按 id 批量回显名称。

        Args:
            target: 目标类型（`ORG_TARGETS` 之一：user / post / dept）。
            ids: 对象 ID 序列。

        Returns:
            Sequence[OrgNameRef]: 回显项（未命中 id 也在结果中占位，`exists=False`）。
        """


def get_org_data_source(request: Request) -> BaseOrgDataSource:
    """取应用级组织主数据查询契约（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseOrgDataSource: 应用装配的组织查询实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseOrgDataSource",
        resolve_plugin(
            "org_data_source",
            settings.org_data_source.provider,
            expected_version=BaseOrgDataSource.contract_version,
        ),
    )


def get_org_name_resolver(request: Request) -> BaseOrgNameResolver:
    """取应用级组织主数据回显契约（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseOrgNameResolver: 应用装配的组织回显实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseOrgNameResolver",
        resolve_plugin(
            "org_name_resolver",
            settings.org_name_resolver.provider,
            expected_version=BaseOrgNameResolver.contract_version,
        ),
    )
