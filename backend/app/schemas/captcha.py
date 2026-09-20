"""验证码占位路由的请求 / 响应契约（与 `app/captcha/` 能力域契约字段一一对应）。

- `CaptchaChallengeRequest`：出题请求（场景 + 挑战类型）。
- `CaptchaSmsRequest`：短信验证码发送请求（目标手机号 + 场景）。
- `CaptchaVerifyRequest`：凭证校验请求（挑战类型 / 编号 / 校验码 / 轨迹 / 场景）。
- `CaptchaChallengeResponse` / `CaptchaVerifyResponse` / `CaptchaPolicyResponse`：挑战 / 校验 / 场景策略响应。

口径：路由契约与能力域契约**字段名一致**，由路由层显式映射（不隐式透传字典），保证 OpenAPI 契约稳定；
图片字节在路由面以 **base64** 字符串承载（能力域契约只返回字节，传输形态由接口层决定）。
"""

from pydantic import Field

from app.captcha.base import CaptchaKind
from app.schemas.base import BaseSchema

__all__ = [
    "CaptchaChallengeRequest",
    "CaptchaChallengeResponse",
    "CaptchaPolicyResponse",
    "CaptchaSmsRequest",
    "CaptchaVerifyRequest",
    "CaptchaVerifyResponse",
]


class CaptchaChallengeRequest(BaseSchema):
    """验证码出题请求。"""

    scene: str = Field(default="login", description="使用场景（取值见 CAPTCHA_SCENES）")
    kind: CaptchaKind = Field(default=CaptchaKind.IMAGE, description="挑战类型（image / slider）")


class CaptchaSmsRequest(BaseSchema):
    """短信验证码发送请求。"""

    phone: str = Field(min_length=1, description="目标手机号（格式校验随真实实现）")
    scene: str = Field(default="login", description="使用场景（取值见 CAPTCHA_SCENES）")


class CaptchaVerifyRequest(BaseSchema):
    """验证码凭证校验请求。"""

    captcha_id: str = Field(min_length=1, description="挑战编号")
    kind: CaptchaKind = Field(default=CaptchaKind.IMAGE, description="挑战类型（决定取校验码还是轨迹）")
    code: str = Field(default="", description="用户输入的校验码（图形 / 短信）")
    trace: list[tuple[int, int, int]] = Field(
        default_factory=list[tuple[int, int, int]], description="滑块轨迹点序列（每点为 x / y / 相对起点毫秒）"
    )
    scene: str = Field(default="login", description="使用场景（取值见 CAPTCHA_SCENES）")


class CaptchaChallengeResponse(BaseSchema):
    """验证码挑战响应（对应能力域 `CaptchaChallenge`）。"""

    captcha_id: str = Field(description="挑战编号")
    kind: CaptchaKind = Field(description="挑战类型")
    image: str = Field(description="挑战图片（base64；占位为空串）")
    expires_in: int = Field(description="有效期（秒）")
    scene: str = Field(description="使用场景")
    payload: str = Field(description="形态相关参数（JSON 字符串）")
    target: str = Field(description="脱敏目标（仅短信渠道，其余为空串）")
    cooldown: int = Field(description="重发冷却（秒）")


class CaptchaVerifyResponse(BaseSchema):
    """验证码校验响应（校验失败以业务错误码表达，不落本契约）。"""

    verified: bool = Field(description="是否校验通过（通过恒 true）")


class CaptchaPolicyResponse(BaseSchema):
    """场景策略响应（对应能力域 `CaptchaScenePolicy`）。"""

    scene: str = Field(description="使用场景")
    required: bool = Field(description="该场景是否强制要求验证码")
    fail_threshold: int = Field(description="连续失败阈值")
    ttl: int = Field(description="挑战有效期（秒）")
    cooldown: int = Field(description="重发冷却（秒）")
