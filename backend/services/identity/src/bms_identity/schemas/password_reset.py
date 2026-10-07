"""认证与身份服务 schemas 层：自助找回密码请求 / 响应与 platform 内部契约映射。

- 两枚公开端点（`/auth/forgot-password` / `/auth/reset-password`）免登录；成功响应恒通用（防枚举）。
- `PlatformResetTargetResult` 为 platform 内部「重置目标」契约映射（含投递目标原始值，仅内部使用不外显）。
"""

from pydantic import Field

from bms_core.schemas.base import BaseSchema
from bms_core.schemas.service import ServiceDto
from bms_identity.schemas.auth import CaptchaInput


class PasswordForgotRequest(BaseSchema):
    """发起找回请求（账号 / 手机 / 邮箱取通道；验证码按场景策略必带）。"""

    identifier: str = Field(min_length=1, max_length=255, description="账号 / 手机号 / 邮箱")
    captcha: CaptchaInput | None = Field(default=None, description="验证码凭证（场景 reset_password；策略强制时必带）")
    tenant: str | None = Field(default=None, max_length=64, description="租户编码（可选；携带则以之为准）")


class PasswordForgotResult(BaseSchema):
    """发起找回响应（恒 `sent=true`：账号不存在 / 停用 / 无通道一律同响应，防枚举）。"""

    sent: bool = Field(default=True, description="重置信息是否已受理（恒 true）")


class PasswordResetRequest(BaseSchema):
    """提交重置请求（重置令牌 + 新口令；策略判定在 platform 侧）。"""

    token: str = Field(min_length=1, max_length=512, description="重置令牌（通知下发；单次有效）")
    new_password: str = Field(min_length=1, max_length=512, description="新口令明文")
    tenant: str | None = Field(default=None, max_length=64, description="租户编码（可选；携带则以之为准）")


class PasswordResetResult(BaseSchema):
    """提交重置响应。"""

    reset: bool = Field(default=True, description="密码是否已重置（成功恒 true）")


class PlatformResetTargetResult(ServiceDto):
    """platform 内部重置目标契约 DTO（消费 `UserResetTargetResult`）。"""

    found: bool = Field(default=False, description="账号是否存在（未软删）")
    user_id: int | None = Field(default=None, description="用户主键")
    account: str = Field(default="", description="登录账号")
    deliverable: bool = Field(default=False, description="是否可送达（启用且有可用通道）")
    channel: str = Field(default="", description="投递通道（email / sms；无可为空串）")
    target: str = Field(default="", description="投递目标（原始邮箱 / 手机号；内部契约，不对外回显）")
