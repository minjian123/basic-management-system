"""验证码占位路由：`/api/v1/captcha`（出题 / 短信发送 / 凭证校验 / 场景策略）。

- 一律经验证码基座出口（占位实现：三形态恒定通过、短信不真发、策略取平台默认）；真实出题与轨迹判定、
  短信下发、冷却与频次计数随六 认证与安全阶段（同一任务文档不重复立项）。
- 四端点**免登录**：验证码用于登录 / 找回密码等登录前场景，要求登录态与语义相背；防滥用限流随认证阶段接入（02-25）。
- 路由只做参数校验与委托，不承载失败计数与强制策略（归登录侧，见《架构设计 · 认证与会话》「密码与账号策略」节）。
"""

import base64
from typing import Annotated

from fastapi import Depends, Path

from bms_core.api.base import BaseRouter
from bms_core.api.deps import get_captcha
from bms_core.captcha.base import CAPTCHA_SCENES, BaseCaptcha, CaptchaChallenge, CaptchaCredential
from bms_core.core.exceptions import ParamError
from bms_core.schemas.captcha import (
    CaptchaChallengeRequest,
    CaptchaChallengeResponse,
    CaptchaPolicyResponse,
    CaptchaSmsRequest,
    CaptchaVerifyRequest,
    CaptchaVerifyResponse,
)
from bms_core.schemas.common import ApiResponse

router = BaseRouter(key="captcha", prefix="/captcha", tags=["captcha"])

CaptchaDep = Annotated[BaseCaptcha, Depends(get_captcha)]
ScenePath = Annotated[str, Path(description="使用场景（取值见 CAPTCHA_SCENES）")]


def _challenge_response(challenge: CaptchaChallenge) -> CaptchaChallengeResponse:
    """把能力域挑战映射为路由响应契约（字段一一对应，图片转 base64）。

    Args:
        challenge: 能力域挑战值对象。

    Returns:
        CaptchaChallengeResponse: 路由响应契约。
    """
    return CaptchaChallengeResponse(
        captcha_id=challenge.captcha_id,
        kind=challenge.kind,
        image=base64.b64encode(challenge.image).decode(),
        expires_in=challenge.expires_in,
        scene=challenge.scene,
        payload=challenge.payload,
        target=challenge.target,
        cooldown=challenge.cooldown,
    )


def _ensure_scene(scene: str) -> str:
    """校验场景取值在 `CAPTCHA_SCENES` 内（策略入口本身对未知场景回落默认）。

    Args:
        scene: 使用场景。

    Returns:
        str: 原值。

    Raises:
        ParamError: 场景未登记（10001）。
    """
    if scene not in CAPTCHA_SCENES:
        raise ParamError(f"未登记验证码场景：{scene}")
    return scene


@router.post("/challenges")
async def create_challenge(captcha: CaptchaDep, req: CaptchaChallengeRequest) -> ApiResponse:
    """生成验证码挑战（图形 / 滑块）。

    Args:
        captcha: 验证码基座。
        req: 出题请求。

    Returns:
        ApiResponse: 统一响应，data 为挑战（`CaptchaChallengeResponse`）。
    """
    challenge = await captcha.generate(_ensure_scene(req.scene), kind=req.kind)
    return ApiResponse.ok(_challenge_response(challenge))


@router.post("/sms")
async def send_sms_code(captcha: CaptchaDep, req: CaptchaSmsRequest) -> ApiResponse:
    """发送短信验证码（占位不真发；目标手机号脱敏后回显）。

    Args:
        captcha: 验证码基座。
        req: 短信发送请求。

    Returns:
        ApiResponse: 统一响应，data 为挑战（`CaptchaChallengeResponse`，`target` 为脱敏手机号）。
    """
    challenge = await captcha.send_sms(req.phone, _ensure_scene(req.scene))
    return ApiResponse.ok(_challenge_response(challenge))


@router.post("/verify")
async def verify_captcha(captcha: CaptchaDep, req: CaptchaVerifyRequest) -> ApiResponse:
    """校验验证码凭证（失败以业务错误码 20101 表达）。

    Args:
        captcha: 验证码基座。
        req: 凭证校验请求。

    Returns:
        ApiResponse: 统一响应，data 为校验结果（`CaptchaVerifyResponse`）。
    """
    credential = CaptchaCredential(
        captcha_id=req.captcha_id,
        kind=req.kind,
        code=req.code,
        trace=tuple(req.trace),
        scene=_ensure_scene(req.scene),
    )
    await captcha.require_credential(credential)
    return ApiResponse.ok(CaptchaVerifyResponse(verified=True))


@router.get("/scenes/{scene}/policy")
async def get_scene_policy(captcha: CaptchaDep, scene: ScenePath) -> ApiResponse:
    """取场景策略（是否强制 / 连续失败阈值 / 有效期 / 重发冷却）。

    Args:
        captcha: 验证码基座。
        scene: 使用场景。

    Returns:
        ApiResponse: 统一响应，data 为场景策略（`CaptchaPolicyResponse`）。
    """
    policy = await captcha.policy(_ensure_scene(scene))
    return ApiResponse.ok(
        CaptchaPolicyResponse(
            scene=policy.scene,
            required=policy.required,
            fail_threshold=policy.fail_threshold,
            ttl=policy.ttl,
            cooldown=policy.cooldown,
        )
    )
