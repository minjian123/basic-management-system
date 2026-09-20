"""验证码能力域：图形 / 滑块 / 短信三形态基座契约（真实出题 / 轨迹判定 / 短信下发随六 认证与安全阶段回补）。

- `CaptchaKind` / `CaptchaChallenge` / `CaptchaCredential` / `CaptchaScenePolicy`：挑战类型、挑战值对象、
  统一凭证与场景策略数据契约（挑战值对象只在尾部追加带默认值字段，属**向后兼容扩展**）。
- `CAPTCHA_SCENES` / `CAPTCHA_SCENE_POLICIES` / `default_scene_policy`：场景枚举与平台默认策略表
  （真实实现读 `sys_config` 按租户覆盖、缺省回落本表）。
- `mask_phone`：短信目标脱敏唯一入口（保留前 3 后 4）；真实实现改经 02-29 脱敏基座，签名与口径不变。
- `build_captcha_key`：验证码存储 key 统一拼接（`bms:global:captcha:{uuid}`，见《架构设计 · 数据架构》
  「key 空间规划」节）；三类渠道**共用同一编号空间**。
- `BaseCaptcha`：能力域中间层契约（`key = "captcha"`）——出题 `generate` / 短信发送 `send_sms` /
  凭证判定 `verify_credential` + 强制校验 `require_credential`（失败抛 `CaptchaVerifyError` 20101）/
  场景策略 `policy`；图形码兼容入口 `verify(captcha_id, code)` 为**默认实现**（委托凭证校验，语义不变）。
- `get_captcha`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

与安全原语（`app/core/security.py`）分工：原语是无状态工具（哈希 / 令牌 / 会话），本基座是认证公共机制
（验证码出题与**一次性校验**，涉及 Redis 与时间语义）。短信下发经 02-20 通知渠道、限次与防滥用经 02-25
限流基座、脱敏经 02-29——三者职责边界不重叠（见《架构设计 · 认证与会话》「密码与账号策略」节）。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import cast

from fastapi import Request

from app.core.base import BaseObject
from app.core.config import Settings
from app.core.exceptions import CaptchaVerifyError
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin

CAPTCHA_KEY_PREFIX = "bms"
"""验证码 key 前缀（与缓存 key 同前缀）。"""

GLOBAL_CAPTCHA_SCOPE = "global"
"""验证码作用域位（全局 key，无租户维度）。"""

CAPTCHA_TTL = 300
"""验证码有效期（秒，5 分钟；见《架构设计 · 子系统_认证与会话》「密码与账号策略」节）。"""

SMS_CAPTCHA_TTL = 300
"""短信验证码有效期（秒，5 分钟；与图形码同窗）。"""

SMS_COOLDOWN = 60
"""短信重发冷却（秒）；同时作为前端倒计时口径。"""

CAPTCHA_FAIL_THRESHOLD = 3
"""连续失败阈值（平台默认，供场景策略默认表基准）。"""

SLIDER_TOLERANCE = 10
"""滑块轨迹终点容差（像素下限）；真实实现只收紧不重定。"""

NULL_CAPTCHA_PAYLOAD = "{}"
"""占位形态参数（JSON 空对象串；真实实现按形态填背景与缺口参数）。"""

CAPTCHA_SCENES: tuple[str, ...] = ("login", "reset_password", "bind", "unbind", "register")
"""验证码场景取值（登录 / 找回密码 / 绑定手机 / 解绑手机 / 注册）。"""


def build_captcha_key(captcha_id: str) -> str:
    """构建验证码存储 key（规范 `bms:global:captcha:{uuid}`）。

    Args:
        captcha_id: 验证码编号。

    Returns:
        str: 验证码 key。
    """
    return f"{CAPTCHA_KEY_PREFIX}:{GLOBAL_CAPTCHA_SCOPE}:captcha:{captcha_id}"


def mask_phone(phone: str) -> str:
    """手机号脱敏（保留前 3 后 4，如 `138****5678`）。

    长度不足 8 位时保留前 3 位（不抛错），保证任何输入都不会原样回显；真实实现改经 02-29 脱敏基座，
    函数签名与调用口径不变。

    Args:
        phone: 手机号。

    Returns:
        str: 脱敏手机号。
    """
    if len(phone) >= 8:
        return f"{phone[:3]}****{phone[-4:]}"
    return f"{phone[:3]}****"


class CaptchaKind(StrEnum):
    """挑战类型（与前端验证码字段形态取值同源）。"""

    IMAGE = "image"
    """图形验证码（出图字节经 `CaptchaChallenge.image` 返回）。"""

    SLIDER = "slider"
    """滑块挑战（背景与缺口参数经 `payload` 返回，轨迹凭证经 `CaptchaCredential.trace` 校验）。"""

    SMS = "sms"
    """短信验证码（经 `send_sms` 发送，校验码经 `CaptchaCredential.code` 校验）。"""


@dataclass(frozen=True)
class CaptchaChallenge(BaseObject):
    """验证码挑战（值对象，不携带答案明文）：编号 + 图片字节 + 有效期 + 场景 + 形态相关字段。"""

    captcha_id: str
    """挑战编号（三类渠道共用同一编号空间）。"""

    image: bytes
    """挑战图片字节（图形 / 滑块为 PNG；短信为空字节）。"""

    expires_in: int = CAPTCHA_TTL
    """有效期（秒）。"""

    scene: str = "login"
    """使用场景（取值见 `CAPTCHA_SCENES`）。"""

    kind: CaptchaKind = CaptchaKind.IMAGE
    """挑战类型（图形 / 滑块 / 短信）。"""

    payload: str = ""
    """形态相关参数（JSON 字符串；滑块为背景与缺口参数，图形 / 短信为空串）。"""

    target: str = ""
    """脱敏目标（仅短信渠道使用，恒为脱敏手机号）。"""

    cooldown: int = 0
    """重发冷却秒数（短信取 `SMS_COOLDOWN`；图形 / 滑块为 0）。"""


@dataclass(frozen=True)
class CaptchaCredential(BaseObject):
    """验证码凭证（统一承载三形态的用户提交内容）：图形 / 短信用校验码，滑块用轨迹。"""

    captcha_id: str
    """挑战编号。"""

    kind: CaptchaKind = CaptchaKind.IMAGE
    """挑战类型（决定校验取 `code` 还是 `trace`）。"""

    code: str = ""
    """用户输入的校验码（图形 / 短信）。"""

    trace: tuple[tuple[int, int, int], ...] = ()
    """滑块轨迹点序列（每点 `(x, y, 相对起点毫秒)`；位置与时间维度一次预留，避免后续破坏性扩展）。"""

    scene: str = "login"
    """使用场景。"""


@dataclass(frozen=True)
class CaptchaScenePolicy(BaseObject):
    """场景策略：是否强制、连续失败阈值、有效期与重发冷却（真实实现按租户经 `sys_config` 覆盖）。"""

    scene: str
    """使用场景。"""

    required: bool = True
    """该场景是否强制要求验证码。"""

    fail_threshold: int = CAPTCHA_FAIL_THRESHOLD
    """连续失败阈值（达阈值后由上层强制要求）。"""

    ttl: int = CAPTCHA_TTL
    """挑战有效期（秒）。"""

    cooldown: int = SMS_COOLDOWN
    """重发冷却（秒）。"""


CAPTCHA_SCENE_POLICIES: tuple[CaptchaScenePolicy, ...] = (
    CaptchaScenePolicy(scene="login", required=False),
    CaptchaScenePolicy(scene="reset_password"),
    CaptchaScenePolicy(scene="bind"),
    CaptchaScenePolicy(scene="unbind"),
    CaptchaScenePolicy(scene="register"),
)
"""平台默认场景策略表（顺序与 `CAPTCHA_SCENES` 一致；登录首次不强制、连续失败达阈值后强制）。"""

DEFAULT_CAPTCHA_SCENE_POLICY = CaptchaScenePolicy(scene="")
"""通用默认策略（未登记场景回落；`scene` 为空串表示通用口径）。"""


def default_scene_policy(scene: str) -> CaptchaScenePolicy:
    """取平台默认场景策略（未登记场景回落通用默认，不抛错）。

    Args:
        scene: 使用场景。

    Returns:
        CaptchaScenePolicy: 场景策略（`scene` 回显为入参）。
    """
    for policy in CAPTCHA_SCENE_POLICIES:
        if policy.scene == scene:
            return policy
    return replace(DEFAULT_CAPTCHA_SCENE_POLICY, scene=scene)


class BaseCaptcha(BasePluggable, ABC):
    """验证码契约：三类渠道出题、短信发送、凭证校验与场景策略。"""

    key: str = "captcha"
    plugin_key: str = "captcha"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def generate(self, scene: str = "login", *, kind: CaptchaKind = CaptchaKind.IMAGE) -> CaptchaChallenge:
        """生成验证码挑战（图形 / 滑块；短信走 `send_sms`）。

        Args:
            scene: 使用场景（取值见 `CAPTCHA_SCENES`）。
            kind: 挑战类型（图形 / 滑块）；短信形态应改走 `send_sms`。

        Returns:
            CaptchaChallenge: 挑战值对象（编号 / 图片字节 / 有效期 / 场景 / 形态参数）。
        """

    @abstractmethod
    async def send_sms(self, phone: str, scene: str = "login") -> CaptchaChallenge:
        """发送短信验证码（真实实现经 02-20 通知渠道下发、02-25 限流基座限次）。

        Args:
            phone: 目标手机号（回显值一律经 `mask_phone` 脱敏）。
            scene: 使用场景（取值见 `CAPTCHA_SCENES`）。

        Returns:
            CaptchaChallenge: 挑战值对象（`kind=sms` / 脱敏目标 / 有效期 / 冷却）。

        Raises:
            CaptchaTooFrequentError: 冷却未到或频次超限（`20103` / 429；真实实现抛，占位不抛）。
        """

    @abstractmethod
    async def verify_credential(self, credential: CaptchaCredential) -> bool:
        """校验验证码凭证（判定入口，不抛错；真实实现校验成功后即失效）。

        Args:
            credential: 验证码凭证（图形 / 短信用校验码、滑块用轨迹）。

        Returns:
            bool: 校验通过为 True；过期 / 不存在 / 不匹配为 False。
        """

    async def require_credential(self, credential: CaptchaCredential) -> None:
        """强制校验验证码凭证（接口层一行接入）。

        Args:
            credential: 验证码凭证。

        Raises:
            CaptchaVerifyError: 校验不通过（`20101`；全局处理器统一转响应）。
        """
        if not await self.verify_credential(credential):
            raise CaptchaVerifyError(f"验证码校验不通过：{credential.captcha_id}")

    @abstractmethod
    async def policy(self, scene: str) -> CaptchaScenePolicy:
        """取场景策略（是否强制 / 失败阈值 / 有效期 / 冷却）。

        Args:
            scene: 使用场景。

        Returns:
            CaptchaScenePolicy: 场景策略（真实实现读 `sys_config`、缺省回落平台默认表）。
        """

    async def verify(self, captcha_id: str, code: str) -> bool:
        """校验图形验证码（图形码兼容入口，委托 `verify_credential`）。

        Args:
            captcha_id: 验证码编号。
            code: 用户输入的验证码。

        Returns:
            bool: 校验通过为 True；过期 / 不存在 / 不匹配为 False。
        """
        return await self.verify_credential(CaptchaCredential(captcha_id=captcha_id, code=code))


def get_captcha(request: Request) -> BaseCaptcha:
    """取应用级验证码基座（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseCaptcha: 应用装配的验证码实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseCaptcha",
        resolve_plugin(
            "captcha",
            settings.captcha.provider,
            expected_version=BaseCaptcha.contract_version,
        ),
    )
