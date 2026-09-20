"""org 能力域缺省实现（Null Object）：固定 / 批量占位数据，不连组织库、不做过滤与展开。"""

from collections.abc import Sequence

from app.core.capability import BaseNullObject
from app.org.base import (
    DEFAULT_ORG_PAGE_SIZE,
    BaseOrgDataSource,
    BaseOrgNameResolver,
    OrgDept,
    OrgNameRef,
    OrgPost,
    OrgUser,
)
from app.schemas.pagination import BasePageResponse

__all__ = [
    "NullOrgDataSource",
    "NullOrgNameResolver",
]

_NULL_NAME_PREFIX = "占位#"
"""占位回显名前缀（`NullOrgNameResolver` 按 id 生成，便于断言）。"""


class NullOrgDataSource(BaseOrgDataSource, BaseNullObject):
    """占位组织查询：固定单条用户 / 岗位页、固定两节点部门树；不连库、不做数据范围与脱敏。"""

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
        """查询用户（占位固定单条）。

        Args:
            keyword: 关键字（占位忽略）。
            dept_id: 归属部门 ID（占位忽略）。
            include_children: 是否含下级（占位忽略）。
            status: 状态过滤（占位忽略）。
            page: 页码（占位回显）。
            size: 每页条数（占位回显）。

        Returns:
            BasePageResponse[OrgUser]: 固定单条用户占位页。
        """
        del keyword, dept_id, include_children, status
        item = OrgUser(
            id=1,
            username="null-user",
            nickname="占位用户",
            dept_id=1,
            status="enabled",
            phone="13800000000",
            email="null@example.com",
        )
        return BasePageResponse[OrgUser](list=[item], total=1, page=page, size=size)

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
        """查询岗位（占位固定单条）。

        Args:
            keyword: 关键字（占位忽略）。
            dept_id: 归属部门 ID（占位忽略）。
            include_children: 是否含下级（占位忽略）。
            status: 状态过滤（占位忽略）。
            page: 页码（占位回显）。
            size: 每页条数（占位回显）。

        Returns:
            BasePageResponse[OrgPost]: 固定单条岗位占位页。
        """
        del keyword, dept_id, include_children, status
        item = OrgPost(id=1, code="null-post", name="占位岗位", dept_id=1, status="enabled", sort=0)
        return BasePageResponse[OrgPost](list=[item], total=1, page=page, size=size)

    async def dept_tree(self, *, status: str | None = None) -> Sequence[OrgDept]:
        """取部门树（占位固定两节点：根 + 一子）。

        Args:
            status: 状态过滤（占位忽略）。

        Returns:
            Sequence[OrgDept]: 固定两节点部门树。
        """
        del status
        child = OrgDept(id=2, parent_id=1, name="占位子部门", sort=0, status="enabled")
        root = OrgDept(id=1, parent_id=None, name="占位根部门", sort=0, status="enabled", children=[child])
        return (root,)


class NullOrgNameResolver(BaseOrgNameResolver, BaseNullObject):
    """占位组织回显：对传入 id 逐个返回占位名（不查库、不做数据范围与脱敏）。"""

    async def resolve_names(self, target: str, ids: Sequence[int]) -> Sequence[OrgNameRef]:
        """按 id 批量回显名称（占位按 id 生成占位名）。

        Args:
            target: 目标类型（占位原样回带）。
            ids: 对象 ID 序列。

        Returns:
            Sequence[OrgNameRef]: 每个 id 一条回显项（`exists=True` / `status=enabled`）。
        """
        return tuple(
            OrgNameRef(id=item, name=f"{_NULL_NAME_PREFIX}{item}", target=target, exists=True, status="enabled")
            for item in ids
        )
