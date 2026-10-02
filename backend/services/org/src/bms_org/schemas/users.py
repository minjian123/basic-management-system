"""组织主数据服务 schemas 层：内部用户概要接口请求 / 响应契约（服务间调用，不经网关）。"""

from pydantic import Field

from bms_core.schemas.base import BaseSchema


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
    """JIT 建号请求（账号 / 昵称 / 语言时区；租户经服务 JWT `tenant` claim 解析）。"""

    username: str = Field(min_length=1, max_length=64, description="登录账号（调用侧已清洗）")
    name: str = Field(min_length=1, max_length=128, description="昵称 / 显示名")
    locale: str | None = Field(default=None, max_length=16, description="语言偏好（可空）")
    timezone: str | None = Field(default=None, max_length=64, description="时区偏好（可空）")


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
