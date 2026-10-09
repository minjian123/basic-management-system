"""平台服务 schemas 层：用户相关请求 / 响应契约。

- 内部契约（服务间调用，不经网关）：概要 / 重置目标 / 统一建号；**只读查询出口**（`/query`，
  供 mdm 组织域只读出口取用户明细——组织主数据归 mdm、用户（账号）归 platform，跨服务只经契约）；
- 管理面契约（`/api/v1/users`，登录 + `user:query`）：最小用户只读查询行。
"""

from datetime import datetime
from typing import Annotated, ClassVar, Literal

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.schemas.base import CONTRACT_COLLECTION, CONTRACT_STABLE_LIST, BaseSchema, MaskedFields

UserStatus = Literal["enabled", "disabled"]
"""账号状态取值（`enabled` / `disabled`）。"""

# 账号 / 联系方式校验（服务侧另有去空白与唯一性校验；此处只做形态约束）
_USERNAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
_PHONE_PATTERN = r"^[+]?[0-9][0-9\-\s]{5,31}$"


class UserItem(BaseSchema):
    """用户列表行（管理面；选择用户弹窗 / 已分配列表回显 / 用户列表共用；不含联系方式）。"""

    id: int = Field(description="用户主键")
    username: str = Field(description="登录账号")
    name: str = Field(description="用户昵称 / 显示名")
    status: UserStatus = Field(description="账号状态（enabled/disabled）")
    last_login_at: datetime | None = Field(default=None, description="最近登录时间（UTC；从未登录为 null）")


class InternalUserQueryRequest(BaseSchema):
    """内部用户只读查询请求（服务间调用；租户经服务 JWT `tenant` claim 解析）。"""

    keyword: str | None = Field(default=None, max_length=64, description="关键字（账号 / 姓名，大小写不敏感）")
    status: str | None = Field(default=None, max_length=16, description="账号状态（enabled / disabled）")
    ids: Annotated[ConcurrentStableList[int], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="限定集合（空 = 不限定；非空时只在该集合内筛选）"
    )
    page: int = Field(default=1, ge=1, description="页码（从 1 起）")
    size: int = Field(default=20, ge=1, le=200, description="每页条数（上限 200）")


class InternalUserItem(BaseSchema):
    """内部用户只读行（服务间出口）：联系方式**原样返回**（脱敏归消费方），不含口令与锁定字段。"""

    id: int = Field(description="用户主键")
    username: str = Field(description="登录账号")
    name: str = Field(description="昵称 / 显示名")
    status: str = Field(description="账号状态（enabled / disabled）")
    phone: str | None = Field(default=None, description="手机号（原样返回，脱敏归消费方）")
    email: str | None = Field(default=None, description="邮箱（原样返回，脱敏归消费方）")
    dept_id: int | None = Field(default=None, description="归属部门 id（字段未落地时恒为 null）")


class UserProfileRequest(BaseSchema):
    """用户概要查询请求（按主键；租户经服务 JWT `tenant` claim 解析）。"""

    user_id: int = Field(description="用户主键")


class UserProfileUser(BaseSchema):
    """用户概要（SSO 回调定位用户后取展示信息与状态）。"""

    id: int = Field(description="用户 ID")
    username: str = Field(description="登录账号")
    name: str = Field(description="昵称 / 显示名")
    status: str = Field(description="账号状态（enabled / disabled）")
    locale: str | None = Field(default=None, description="语言偏好")
    timezone: str | None = Field(default=None, description="时区偏好")
    pwd_reset_required: bool = Field(default=False, description="是否需强制改密（密码超有效期）")


class UserProfileResult(BaseSchema):
    """用户概要查询结果（不存在时 `found=false`，由调用侧判定错误语义）。"""

    found: bool = Field(description="用户是否存在")
    user: UserProfileUser | None = Field(default=None, description="用户概要（found=true 时返回）")


class UserCreateRequest(BaseSchema):
    """建号请求（账号 / 昵称 / 语言时区 / 来源；租户经服务 JWT `tenant` claim 解析）。"""

    username: str = Field(min_length=1, max_length=64, description="登录账号（调用侧已清洗）")
    name: str = Field(min_length=1, max_length=128, description="昵称 / 显示名")
    locale: str | None = Field(default=None, max_length=16, description="语言偏好（可空）")
    timezone: str | None = Field(default=None, max_length=64, description="时区偏好（可空）")
    source: str = Field(
        default="sso_jit",
        min_length=1,
        max_length=32,
        description="建号来源（缺省 sso_jit；其余建号路径显式传 admin_create / import / self_register / super_admin）",
    )


class UserCreateResult(BaseSchema):
    """JIT 建号结果（撞名 `created=false` + `reason=username_conflict`，由调用侧换后缀重试）。"""

    created: bool = Field(description="是否建号成功")
    reason: str | None = Field(default=None, description="未建号原因（username_conflict）")
    user: UserProfileUser | None = Field(default=None, description="新建用户概要（created=true 时返回）")


class UserResetTargetRequest(BaseSchema):
    """找回密码重置目标查询请求（账号 / 手机 / 邮箱；租户经服务 JWT `tenant` claim 解析）。"""

    identifier: str = Field(min_length=1, max_length=255, description="账号 / 手机号 / 邮箱")


class UserResetTargetResult(BaseSchema):
    """重置目标解析结果（通道与目标供 identity 侧通知投递；不可送达以 `deliverable=false` 表达）。"""

    found: bool = Field(default=False, description="账号是否存在（未软删）")
    user_id: int | None = Field(default=None, description="用户主键（found=true 时返回）")
    account: str = Field(default="", description="登录账号（found=true 时返回）")
    deliverable: bool = Field(default=False, description="是否可送达（启用且有可用通道）")
    channel: str = Field(default="", description="投递通道（email / sms；无可用通道为空串）")
    target: str = Field(default="", description="投递目标（原始邮箱 / 手机号；内部契约，不对外回显）")


# --------------------------------------------------------------------------- 管理面（用户完整域）
# 用户 CRUD / 启停 / 重置密码 / 角色查看（需求 07-2）。组织字段（部门 / 岗位）不在本模块：
# 用户＝系统账号，组织关系归 mdm（需求 07-11）。


class UserAdminCreateRequest(BaseSchema):
    """新建用户请求（初始密码可选；缺省后端随机生成并一次性回显）。"""

    username: str = Field(
        min_length=1,
        max_length=64,
        pattern=_USERNAME_PATTERN,
        description="登录账号（租户内唯一；软删除后原账号可复用）",
    )
    name: str = Field(min_length=1, max_length=128, description="昵称 / 显示名")
    password: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="初始密码（不传则由后端随机生成并在响应中一次性返回）",
    )
    pwd_reset_required: bool = Field(default=True, description="是否强制下次登录改密")
    email: str | None = Field(default=None, max_length=255, pattern=_EMAIL_PATTERN, description="邮箱（可空）")
    phone: str | None = Field(default=None, max_length=32, pattern=_PHONE_PATTERN, description="手机号（可空）")
    status: UserStatus = Field(default="enabled", description="初始状态（enabled/disabled）")


class UserUpdateRequest(BaseSchema):
    """修改用户请求（昵称 / 邮箱 / 手机；乐观锁比对版本）。"""

    name: str | None = Field(default=None, min_length=1, max_length=128, description="昵称 / 显示名（None = 不改）")
    email: str | None = Field(default=None, max_length=255, description="邮箱（None = 不改；空串 = 清空）")
    phone: str | None = Field(default=None, max_length=32, description="手机号（None = 不改；空串 = 清空）")
    version: int = Field(ge=1, description="客户端版本（乐观锁比对）")


class UserStatusUpdateRequest(BaseSchema):
    """启用 / 停用请求（停用即失效该用户全部会话）。"""

    status: UserStatus = Field(description="目标状态（enabled / disabled）")


class UserPasswordResetRequest(BaseSchema):
    """重置密码请求（复杂度与历史策略校验 + 强制首登改密 + 失效全部会话）。"""

    new_password: str = Field(min_length=1, max_length=128, description="新密码（复杂度 30005 / 历史重复 30006）")
    force_change: bool = Field(default=True, description="是否强制下次登录改密")


class UserDetail(BaseSchema):
    """用户详情（含联系方式与乐观锁版本；联系方式按脱敏标记掩码，`data:plain` 权限见明文）。"""

    masked_fields: ClassVar[MaskedFields] = ConcurrentStableSet({"phone", "email"})

    id: int = Field(description="用户主键")
    username: str = Field(description="登录账号")
    name: str = Field(description="昵称 / 显示名")
    status: UserStatus = Field(description="账号状态（enabled/disabled）")
    email: str | None = Field(default=None, description="邮箱（按脱敏标记掩码）")
    phone: str | None = Field(default=None, description="手机号（按脱敏标记掩码）")
    last_login_at: datetime | None = Field(default=None, description="最近登录时间（UTC；从未登录为 null）")
    version: int = Field(description="乐观锁版本")
    created_at: datetime = Field(description="创建时间（UTC）")
    updated_at: datetime = Field(description="更新时间（UTC）")


class UserAdminCreateResult(BaseSchema):
    """新建用户结果（后端生成的初始密码仅本次返回）。"""

    user: UserDetail = Field(description="新建用户详情")
    initial_password: str | None = Field(
        default=None, description="后端生成的初始密码（仅本次返回；调用方自行指定密码时为 null）"
    )


class UserDeleteResult(BaseSchema):
    """软删除结果（`session_revoked` 表示会话撤销是否成功）。"""

    deleted: bool = Field(description="是否删除成功")
    session_revoked: bool = Field(description="是否已失效该用户全部会话")


class UserStatusResult(BaseSchema):
    """启用 / 停用结果（停用时 `session_revoked` 有意义）。"""

    user: UserDetail = Field(description="更新后的用户详情")
    session_revoked: bool = Field(description="是否已失效该用户全部会话")


class UserPasswordResetResult(BaseSchema):
    """重置密码结果（不回显新密码）。"""

    reset: bool = Field(description="是否重置成功")
    session_revoked: bool = Field(description="是否已失效该用户全部会话")


class UserRoleItem(BaseSchema):
    """用户直接角色行（同库 `sys_user_role` ⋈ `sys_role`；只读，维护归角色管理）。"""

    role_id: int = Field(description="角色主键")
    role_code: str = Field(description="角色码")
    role_name: str = Field(description="角色名称")
    role_type: str = Field(description="角色类型（custom/system/security/audit）")


class UserRoleList(BaseSchema):
    """用户直接角色清单。"""

    items: Annotated[ConcurrentStableList[UserRoleItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="直接角色清单"
    )
