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


class UserProfileResult(BaseSchema):
    """用户概要查询结果（不存在时 `found=false`，由调用侧判定错误语义）。"""

    found: bool = Field(description="用户是否存在")
    user: UserProfileUser | None = Field(default=None, description="用户概要（found=true 时返回）")
