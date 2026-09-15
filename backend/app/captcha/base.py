"""验证码能力域：图形验证码基座契约（真实 Pillow + Redis 随四 认证与安全阶段回补）。

- `BaseCaptcha`：能力域中间层契约（`key = "captcha"`）——`generate`（返回挑战值对象：编号 + 图片字节 +
  有效期 + 场景）/ `verify`（校验，真实实现单次有效）。
- `build_captcha_key`：验证码存储 key 统一拼接（`bms:global:captcha:{uuid}`，见《架构设计 · 数据架构》
  「key 空间规划」节）。
- `get_captcha`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

与安全原语（`app/core/security.py`）分工：原语是无状态工具（哈希 / 令牌 / 会话），本基座是认证公共机制
（验证码生成与校验，涉及 Redis 与时间语义）。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from app.core.base import BaseObject
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable

CAPTCHA_KEY_PREFIX = "bms"
"""验证码 key 前缀（与缓存 key 同前缀）。"""

GLOBAL_CAPTCHA_SCOPE = "global"
"""验证码作用域位（全局 key，无租户维度）。"""

CAPTCHA_TTL = 300
"""验证码有效期（秒，5 分钟；见《架构设计 · 子系统_认证与会话》「密码与账号策略」节）。"""

CAPTCHA_SCENES: tuple[str, ...] = ("login", "reset_password", "bind")
"""验证码场景取值（占位期仅登记不校验）。"""


def build_captcha_key(captcha_id: str) -> str:
    """构建验证码存储 key（规范 `bms:global:captcha:{uuid}`）。

    Args:
        captcha_id: 验证码编号。

    Returns:
        str: 验证码 key。
    """
    return f"{CAPTCHA_KEY_PREFIX}:{GLOBAL_CAPTCHA_SCOPE}:captcha:{captcha_id}"


@dataclass(frozen=True)
class CaptchaChallenge(BaseObject):
    """验证码挑战：编号 + 图片字节 + 有效期 + 场景（值对象，不携带答案明文）。"""

    captcha_id: str
    image: bytes
    expires_in: int = CAPTCHA_TTL
    scene: str = "login"


class BaseCaptcha(BasePluggable, ABC):
    """图形验证码契约：生成挑战与校验（真实实现经 Redis 存取）。"""

    key: str = "captcha"
    plugin_key: str = "captcha"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def generate(self, scene: str = "login") -> CaptchaChallenge:
        """生成验证码。

        Args:
            scene: 使用场景（取值见 `CAPTCHA_SCENES`）。

        Returns:
            CaptchaChallenge: 挑战值对象（编号 / 图片字节 / 有效期 / 场景）。
        """

    @abstractmethod
    async def verify(self, captcha_id: str, code: str) -> bool:
        """校验验证码。

        Args:
            captcha_id: 验证码编号。
            code: 用户输入的验证码。

        Returns:
            bool: 校验通过为 True；过期 / 不存在 / 不匹配为 False。
        """


def get_captcha(request: Request) -> BaseCaptcha:
    """取应用级验证码基座（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseCaptcha: 应用装配的验证码实例。
    """
    return cast("BaseCaptcha", request.app.state.captcha)
