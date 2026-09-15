"""captcha 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 app.captcha.base.py 迁入）。"""

from uuid import uuid4

from app.captcha.base import CAPTCHA_TTL, BaseCaptcha, CaptchaChallenge
from app.core.capability import BaseNullObject

__all__ = [
    "NullCaptcha",
]


class NullCaptcha(BaseCaptcha, BaseNullObject):
    """占位验证码：**恒定通过**（不连 Redis、不出图，未接入真实实现时使用）。"""

    async def generate(self, scene: str = "login") -> CaptchaChallenge:
        """恒定返回挑战（占位不出图，`image` 为空字节）。

        Args:
            scene: 使用场景（占位透传不校验）。

        Returns:
            CaptchaChallenge: 挑战值对象。
        """
        return CaptchaChallenge(captcha_id=uuid4().hex, image=b"", expires_in=CAPTCHA_TTL, scene=scene)

    async def verify(self, captcha_id: str, code: str) -> bool:
        """恒定通过（占位不校验编号与验证码）。

        Args:
            captcha_id: 验证码编号（占位不校验）。
            code: 用户输入的验证码（占位不校验）。

        Returns:
            bool: True。
        """
        return True
