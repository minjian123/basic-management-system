"""认证与身份服务 schemas 层：登录 / 刷新 / 登出请求与响应契约。"""

from pydantic import Field

from bms_core.schemas.base import BaseSchema
from bms_core.schemas.service import ServiceDto

REFRESH_COOKIE_NAME = "bms_refresh_token"
"""refresh token cookie 名（httpOnly + Secure + SameSite=Lax，`Path` 见 `REFRESH_COOKIE_PATH`）。"""

REFRESH_COOKIE_PATH = "/api/v1/auth"
"""refresh token cookie 作用路径（仅认证端点可见，收敛暴露面）。"""


class CaptchaInput(BaseSchema):
    """登录验证码凭证（图形 / 滑块 / 短信；与验证码基座 `CaptchaCredential` 字段对应）。"""

    captcha_id: str = Field(default="", description="挑战编号")
    kind: str = Field(default="image", description="验证码形态（image / slider / sms）")
    code: str = Field(default="", description="校验码（图形 / 短信）")
    trace: list[tuple[int, int, int]] = Field(
        default_factory=lambda: list[tuple[int, int, int]](), description="滑块轨迹点（x / y / 相对起点毫秒）"
    )


class LoginRequest(BaseSchema):
    """本地登录请求。"""

    account: str = Field(min_length=1, max_length=64, description="登录账号")
    password: str = Field(min_length=1, max_length=512, description="口令明文")
    tenant: str | None = Field(default=None, max_length=64, description="租户编码（可选；携带则以之为准）")
    captcha: CaptchaInput | None = Field(default=None, description="验证码凭证（策略强制或已出题时携带）")


class UserSummary(BaseSchema):
    """登录成功返回的用户概要（权限 / 菜单概要归阶段七 RBAC）。"""

    id: int = Field(description="用户 ID")
    username: str = Field(description="登录账号")
    name: str = Field(description="昵称 / 显示名")
    tenant: str | None = Field(default=None, description="租户编码")
    locale: str | None = Field(default=None, description="语言偏好")
    timezone: str | None = Field(default=None, description="时区偏好")
    must_change_password: bool = Field(default=False, description="是否需强制改密（密码策略归域三）")


class LoginResult(BaseSchema):
    """登录成功响应（access 在响应体；refresh 走 httpOnly cookie）。"""

    access_token: str = Field(description="访问令牌（BMS 自签 JWT）")
    token_type: str = Field(default="Bearer", description="令牌类型")
    expires_in: int = Field(description="access 有效期（秒）")
    user: UserSummary = Field(description="用户概要")


class RefreshResult(BaseSchema):
    """刷新成功响应（新 access 在体；新 refresh 走 httpOnly cookie）。"""

    access_token: str = Field(description="新访问令牌")
    token_type: str = Field(default="Bearer", description="令牌类型")
    expires_in: int = Field(description="access 有效期（秒）")


class OrgUserSummary(ServiceDto):
    """org 内部凭据校验返回的最小用户概要。"""

    id: int = Field(description="用户 ID")
    username: str = Field(description="登录账号")
    name: str = Field(description="昵称 / 显示名")
    locale: str | None = Field(default=None, description="语言偏好")
    timezone: str | None = Field(default=None, description="时区偏好")
    pwd_changed_at: str | None = Field(default=None, description="密码最近变更时间（ISO 8601）")


class OrgVerifyResult(ServiceDto):
    """org 内部凭据校验契约 DTO（消费 `sys_user` 凭据校验结果）。"""

    found: bool = Field(default=False, description="账号是否存在")
    valid: bool = Field(default=False, description="口令是否匹配")
    locked: bool = Field(default=False, description="是否处于锁定期")
    status: str = Field(default="", description="账号状态（enabled/disabled）")
    rehashed: bool = Field(default=False, description="是否本次重哈希")
    user: OrgUserSummary | None = Field(default=None, description="用户概要")


class OrgLoginState(ServiceDto):
    """org 内部登录态写回契约 DTO。"""

    failed_count: int = Field(default=0, description="当前失败计数")
    locked_until: str | None = Field(default=None, description="锁定到期时间（ISO 8601）")
    last_login_at: str | None = Field(default=None, description="最近登录时间（ISO 8601）")
