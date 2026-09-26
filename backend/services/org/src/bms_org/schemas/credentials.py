"""组织主数据服务 schemas 层：内部凭据接口请求 / 响应契约（服务间调用，不经网关）。"""

from datetime import datetime

from pydantic import Field

from bms_core.schemas.base import BaseSchema


class CredentialVerifyRequest(BaseSchema):
    """凭据校验请求（账号 + 密码明文；租户经服务 JWT `tenant` claim 解析）。"""

    account: str = Field(min_length=1, max_length=64, description="登录账号")
    password: str = Field(min_length=1, max_length=512, description="口令明文")


class CredentialUserSummary(BaseSchema):
    """登录成功所需的最小用户概要。"""

    id: int = Field(description="用户 ID")
    username: str = Field(description="登录账号")
    name: str = Field(description="昵称 / 显示名")
    locale: str | None = Field(default=None, description="语言偏好")
    timezone: str | None = Field(default=None, description="时区偏好")
    pwd_changed_at: datetime | None = Field(default=None, description="密码最近变更时间（UTC）")


class CredentialVerifyResult(BaseSchema):
    """凭据校验结果（登录侧统一映射为认证错误码，不直出内部差异）。"""

    found: bool = Field(description="账号是否存在")
    valid: bool = Field(description="口令是否匹配")
    locked: bool = Field(description="账号是否处于锁定期")
    status: str = Field(description="账号状态（enabled/disabled）")
    rehashed: bool = Field(default=False, description="是否本次按当前参数重算了哈希")
    user: CredentialUserSummary | None = Field(default=None, description="用户概要（命中时）")


class UpdatePasswordRequest(BaseSchema):
    """密码更新请求（改密 / 找回密码 / 重哈希回写）。"""

    account: str = Field(min_length=1, max_length=64, description="登录账号")
    new_password: str = Field(min_length=1, max_length=512, description="新口令明文")
    keep_history: int = Field(default=5, ge=0, le=50, description="保留历史密码条数")


class UpdatePasswordResult(BaseSchema):
    """密码更新结果。"""

    updated: bool = Field(description="是否更新成功（账号不存在为 False）")


class LoginStateRequest(BaseSchema):
    """登录态写回请求（成功清零 / 失败计数与锁定）。"""

    account: str = Field(min_length=1, max_length=64, description="登录账号")
    success: bool = Field(description="本次登录是否成功")
    failed_count: int | None = Field(default=None, ge=0, description="失败计数（失败时由登录侧传入）")
    lock_seconds: int | None = Field(default=None, ge=0, description="锁定时长（秒；>0 且失败时写 locked_until）")


class LoginStateResult(BaseSchema):
    """登录态写回结果。"""

    failed_count: int = Field(description="当前失败计数")
    locked_until: datetime | None = Field(default=None, description="锁定到期时间（UTC）")
    last_login_at: datetime | None = Field(default=None, description="最近登录时间（UTC）")
