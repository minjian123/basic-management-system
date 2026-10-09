"""平台服务 schemas 层：角色与授权请求 / 响应模型（继承 `BaseSchema`）。

覆盖：角色 CRUD（`/api/v1/roles`）、用户分配（`/roles/{id}/users`）、菜单 / 表单 / 操作授权
（`/roles/{id}/permissions`）、字段权限（`/roles/{id}/fields`）、数据权限（`/roles/{id}/data-permissions`），
以及最小用户只读查询（`/api/v1/users`）。

集合字段一律以内联 `Annotated[集合类, CONTRACT_COLLECTION]` 声明（防契约 `$defs` 漂移）。
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, CONTRACT_STABLE_LIST, BaseSchema

RoleStatus = Literal["enabled", "disabled"]
"""角色状态取值。"""

PermType = Literal["menu", "form", "action"]
"""授权类型取值。"""

PolicyType = Literal["select", "region", "match", "extension"]
"""数据权限策略取值。"""

RoleType = Literal["custom", "system", "security", "audit"]
"""角色类型取值（`custom` 自定义；`system` / `security` / `audit` 内置三类管理员）。"""


# --------------------------------------------------------------------------- 角色


class RoleCreateRequest(BaseSchema):
    """新增角色请求（角色码租户内唯一；新角色类型恒为 `custom`，契约不透出）。"""

    code: str = Field(min_length=1, max_length=64, description="角色码（租户内唯一，格式受 role.code_pattern 约束）")
    name: str = Field(min_length=1, max_length=128, description="角色名称")
    status: RoleStatus = Field(default="enabled", description="状态（enabled/disabled）")


class RoleUpdateRequest(BaseSchema):
    """修改角色请求（角色码 / 名称 / 状态；乐观锁）；角色类型不可改。"""

    code: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="角色码（None 表示不改；格式受 role.code_pattern 约束，租户内唯一）",
    )
    name: str = Field(min_length=1, max_length=128, description="角色名称")
    status: RoleStatus = Field(default="enabled", description="状态（enabled/disabled）")
    version: int = Field(ge=1, description="客户端版本（乐观锁比对）")


class RoleItem(BaseSchema):
    """角色列表行。"""

    id: int = Field(description="角色主键")
    code: str = Field(description="角色码")
    name: str = Field(description="角色名称")
    status: str = Field(description="状态（enabled/disabled）")
    role_type: RoleType = Field(description="角色类型（custom/system/security/audit）")
    builtin: bool = Field(description="是否内置角色（按 role_type 判定，非 custom 即内置）")
    subject_count: int = Field(description="已分配用户数")


class RoleDetail(BaseSchema):
    """角色详情（含乐观锁版本与审计字段，供记录页「系统信息」）。"""

    id: int = Field(description="角色主键")
    code: str = Field(description="角色码")
    name: str = Field(description="角色名称")
    status: str = Field(description="状态（enabled/disabled）")
    role_type: RoleType = Field(description="角色类型（custom/system/security/audit）")
    builtin: bool = Field(description="是否内置角色（按 role_type 判定）")
    subject_count: int = Field(description="已分配用户数")
    version: int = Field(description="乐观锁版本")
    created_at: datetime = Field(description="创建时间（UTC）")
    created_by: int | None = Field(description="创建人")
    updated_at: datetime = Field(description="更新时间（UTC）")
    updated_by: int | None = Field(description="更新人")


# --------------------------------------------------------------------------- 用户分配


class AssignedUserItem(BaseSchema):
    """角色已分配用户行（最小字段，同库取 `sys_user`）。"""

    user_id: int = Field(description="用户主键")
    username: str = Field(description="登录账号")
    name: str = Field(description="用户昵称 / 显示名")
    status: str = Field(description="账号状态（enabled/disabled）")


class RoleAssignRequest(BaseSchema):
    """批量分配用户请求（幂等 upsert）。"""

    user_ids: Annotated[ConcurrentStableList[int], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="用户主键清单"
    )


class RoleAssignedUsers(BaseSchema):
    """批量分配结果（分配后的用户清单）。"""

    items: Annotated[ConcurrentStableList[AssignedUserItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="分配后的用户清单"
    )


# --------------------------------------------------------------------------- 授权（菜单 / 表单 / 操作）


class RolePermissionEntryRequest(BaseSchema):
    """一条授权条目（菜单 / 表单 / 操作）。"""

    perm_type: PermType = Field(description="授权类型（menu/form/action）")
    target_id: int = Field(gt=0, description="授权目标 ID")
    source_menu_id: int = Field(default=0, ge=0, description="来源菜单入口 ID（0 = 表单级直接授予）")


class RolePermissionRequest(BaseSchema):
    """授权全量覆盖请求（单事务先删后插）。"""

    entries: Annotated[ConcurrentStableList[RolePermissionEntryRequest], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="授权条目清单（全量）"
    )


class RolePermissionEntryItem(BaseSchema):
    """授权条目行（响应）。"""

    id: int = Field(description="授权行主键")
    perm_type: str = Field(description="授权类型（menu/form/action）")
    target_id: int = Field(description="授权目标 ID")
    source_menu_id: int = Field(description="来源菜单入口 ID（0 = 表单级直接授予）")


class RolePermissions(BaseSchema):
    """角色授权条目清单（含来源）。"""

    items: Annotated[ConcurrentStableList[RolePermissionEntryItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="授权条目清单"
    )


# --------------------------------------------------------------------------- 字段权限


class RoleFieldEntryRequest(BaseSchema):
    """一条字段权限条目（只落收窄项）。"""

    form_id: int = Field(gt=0, description="表单 ID")
    field_id: int = Field(gt=0, description="字段 ID")
    visible: bool = Field(default=True, description="是否可见")
    editable: bool = Field(default=True, description="是否可编辑（不可见即不可编辑）")
    source_menu_id: int = Field(default=0, ge=0, description="来源菜单入口 ID（0 = 表单级直接授予）")


class RoleFieldRequest(BaseSchema):
    """字段权限全量覆盖请求。"""

    entries: Annotated[ConcurrentStableList[RoleFieldEntryRequest], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="字段权限条目清单（全量）"
    )


class RoleFieldEntryItem(BaseSchema):
    """字段权限条目行（响应）。"""

    id: int = Field(description="字段权限行主键")
    form_id: int = Field(description="表单 ID")
    field_id: int = Field(description="字段 ID")
    visible: bool = Field(description="是否可见")
    editable: bool = Field(description="是否可编辑")
    source_menu_id: int = Field(description="来源菜单入口 ID（0 = 表单级直接授予）")


class RoleFields(BaseSchema):
    """角色字段权限条目清单（仅收窄项）。"""

    items: Annotated[ConcurrentStableList[RoleFieldEntryItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="字段权限条目清单"
    )


# --------------------------------------------------------------------------- 数据权限


class RoleDataScopeEntryRequest(BaseSchema):
    """一条数据权限条目（角色 × 字典 × 策略 → 结构化配置，只选不编）。"""

    dict_type_id: int = Field(gt=0, description="字典类型 ID")
    policy_type: PolicyType = Field(description="策略类型（select/region/match/extension）")
    config: Annotated[ConcurrentStableList[ConcurrentStableDict[str, object]], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="结构化策略配置（按策略分结构）"
    )


class RoleDataScopeRequest(BaseSchema):
    """数据权限全量覆盖请求。"""

    entries: Annotated[ConcurrentStableList[RoleDataScopeEntryRequest], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="数据权限条目清单（全量）"
    )


class RoleDataScopeEntryItem(BaseSchema):
    """数据权限条目行（响应）。"""

    id: int = Field(description="数据权限行主键")
    dict_type_id: int = Field(description="字典类型 ID")
    policy_type: str = Field(description="策略类型（select/region/match/extension）")
    config: Annotated[ConcurrentStableList[ConcurrentStableDict[str, object]], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="结构化策略配置"
    )


class RoleDataScopes(BaseSchema):
    """角色数据权限条目清单（按字典 × 策略）。"""

    items: Annotated[ConcurrentStableList[RoleDataScopeEntryItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="数据权限条目清单"
    )


# --------------------------------------------------------------------------- 分配编排（角色保存编排端点）
# 一次请求分段**全量覆盖**角色本体 / 用户分配（角色 × 用户）/ 组织分配（岗位、部门）；跨服务写入由
# TM 全局事务保证原子（`provider=xa`；`provider=null` 走顺序提交，仅 dev / test）。需求 07-11 §5。
# 与用户侧 `UserAssignments*`（schemas/users.py）对称；角色侧无「主要项」语义。


class RoleAssignmentProfile(BaseSchema):
    """分配编排请求的角色本体分段（字段语义同 `RoleUpdateRequest`；`None` 表示不改）。"""

    code: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="角色码（None = 不改；格式受 role.code_pattern 约束，租户内唯一）",
    )
    name: str | None = Field(default=None, min_length=1, max_length=128, description="角色名称（None = 不改）")
    status: RoleStatus | None = Field(default=None, description="状态（None = 不改；内置角色改状态被拒）")
    version: int = Field(ge=1, description="客户端版本（乐观锁比对）")


class RoleAssignmentPosts(BaseSchema):
    """分配编排请求的角色-岗位分段（全量覆盖；角色侧无主要项）。"""

    post_ids: Annotated[ConcurrentStableList[int], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="岗位主键集合（全量覆盖；空集 = 清空）"
    )


class RoleAssignmentDepts(BaseSchema):
    """分配编排请求的角色-部门分段（全量覆盖；角色侧无主要项）。"""

    dept_ids: Annotated[ConcurrentStableList[int], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="部门主键集合（全量覆盖；空集 = 清空）"
    )


class RoleAssignmentsRequest(BaseSchema):
    """角色保存编排请求（分段全量覆盖；未出现的分段不参与，不写）。

    分段语义：`role` / `user_ids` / `role_posts` / `role_depts` 为 `None` 表示**不改该段**；
    `user_ids` 为空集表示清空该角色全部用户分配。权限码**分段校验**（`role` → `role:update`，
    其余段 → `role:grant`）。
    """

    role: RoleAssignmentProfile | None = Field(default=None, description="角色本体分段（None = 不改）")
    user_ids: Annotated[ConcurrentStableList[int], CONTRACT_COLLECTION] | None = Field(
        default=None, description="角色直接用户全量集合（None = 不改；空集 = 清空）"
    )
    role_posts: RoleAssignmentPosts | None = Field(default=None, description="角色-岗位分段（None = 不改）")
    role_depts: RoleAssignmentDepts | None = Field(default=None, description="角色-部门分段（None = 不改）")


class RoleAssignmentsResult(BaseSchema):
    """角色保存编排结果（回带 platform 侧生效后集合）。

    组织分配段（岗位 / 部门）的生效后集合由调用方（前端）在保存成功后经 mdm 读契约取回——
    XA 分支执行端点契约只回分支状态、不回业务集合。
    """

    role: RoleDetail = Field(description="生效后角色详情")
    users: RoleAssignedUsers = Field(description="生效后已分配用户清单")
    applied: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST,
        description="本次参与的分段名（role / user_ids / role_posts / role_depts）",
    )
