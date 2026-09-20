"""captcha 能力域缺省实现（Null Object）：三形态占位返回、无副作用（02-3 自 `app.captcha.base.py` 迁入）。"""

from uuid import uuid4

from app.captcha.base import (
    CAPTCHA_TTL,
    NULL_CAPTCHA_PAYLOAD,
    SMS_CAPTCHA_TTL,
    SMS_COOLDOWN,
    BaseCaptcha,
    CaptchaChallenge,
    CaptchaCredential,
    CaptchaKind,
    CaptchaScenePolicy,
    default_scene_policy,
    mask_phone,
)
from app.core.capability import BaseNullObject

__all__ = [
    "NullCaptcha",
]


class NullCaptcha(BaseCaptcha, BaseNullObject):
    """占位验证码：**恒定通过**（不连 Redis、不出图、不发短信、不读配置）。"""

    async def generate(self, scene: str = "login", *, kind: CaptchaKind = CaptchaKind.IMAGE) -> CaptchaChallenge:
        """恒定返回挑战（占位不出图，`image` 为空字节；形态决定有效期与冷却）。

        Args:
            scene: 使用场景（占位透传不校验）。
            kind: 挑战类型（占位按形态回带有效期与冷却）。

        Returns:
            CaptchaChallenge: 挑战值对象。
        """
        return self._challenge(scene, kind)

    async def send_sms(self, phone: str, scene: str = "login") -> CaptchaChallenge:
        """恒定返回短信挑战（占位不真发，`target` 为脱敏手机号）。

        Args:
            phone: 目标手机号（占位期经 `mask_phone` 就地脱敏，不落库、不发送）。
            scene: 使用场景（占位透传不校验）。

        Returns:
            CaptchaChallenge: 挑战值对象（`kind=sms` / 脱敏目标 / 短信有效期与冷却）。
        """
        return self._challenge(scene, CaptchaKind.SMS, target=mask_phone(phone))

    async def verify_credential(self, credential: CaptchaCredential) -> bool:
        """恒定通过（占位不校验编号、校验码与轨迹）。

        Args:
            credential: 验证码凭证（占位不校验）。

        Returns:
            bool: True。
        """
        return True

    async def policy(self, scene: str) -> CaptchaScenePolicy:
        """恒定返回平台默认策略（占位不读 `sys_config`、不区分租户）。

        Args:
            scene: 使用场景。

        Returns:
            CaptchaScenePolicy: 平台默认策略（未登记场景回落通用默认）。
        """
        return default_scene_policy(scene)

    @staticmethod
    def _challenge(scene: str, kind: CaptchaKind, *, target: str = "") -> CaptchaChallenge:
        """构造占位挑战（形态决定有效期与冷却，不生成真实内容）。

        Args:
            scene: 使用场景。
            kind: 挑战类型。
            target: 脱敏目标（仅短信形态使用）。

        Returns:
            CaptchaChallenge: 占位挑战值对象。
        """
        is_sms = kind is CaptchaKind.SMS
        return CaptchaChallenge(
            captcha_id=uuid4().hex,
            image=b"",
            expires_in=SMS_CAPTCHA_TTL if is_sms else CAPTCHA_TTL,
            scene=scene,
            kind=kind,
            payload=NULL_CAPTCHA_PAYLOAD,
            target=target,
            cooldown=SMS_COOLDOWN if is_sms else 0,
        )
