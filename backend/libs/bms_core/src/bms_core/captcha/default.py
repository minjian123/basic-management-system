"""验证码能力域：图形码 / 滑块 / 短信三形态真实实现（Pillow 出图 + Redis 一次性校验）。

- `CaptchaImageOptions`：图形码出图参数（从 `[captcha].options` 解析、带范围校验，非敏感）。
- `CaptchaSliderOptions`：滑块出图 / 判定参数（同从 `[captcha].options` 解析，`slider_` 前缀键）。
- `CaptchaSmsOptions`：短信选项（同从 `[captcha].options` 解析，`sms_` 前缀键：位数 / 账号与 IP 限次 / 窗口）。
- `DefaultCaptcha`（插件名 `default`）：按形态分派出题——
  - 图形码：Pillow 出图（干扰线 / 噪点 / 字符变形，经线程池不阻塞事件循环）与校验码一次性校验。
  - 滑块：**服务端合成出图**（带缺口背景 + 滑块块图，坐标不下发、只存 Redis）+ **轨迹判定**（落点容差 +
    轨迹合理性双因子）。
  - 短信：生成 6 位纯数字码存 Redis（TTL 300s），经 `BaseNotifier` 下发（本期占位不真发）、目标手机号
    脱敏回显、重发冷却 + 账号 / IP 双维限次（经 `BaseRateLimiter`）；发送失败即删除挑战。
  挑战统一存 `bms:global:captcha:{uuid}`（JSON，TTL 300 秒），校验用 `GETDEL` 原子取出（成功即失效、
  单次有效），失败回写并累计 `fails`（失败可重试）。
- 降级口径（fail-closed）：Redis 不可用时出题 / 短信抛 `ServiceUnavailableError`（10007 / 503，明确报错）；
  校验判定入口 `verify_credential` 返回 False（不放行、不抛错，保持契约），强制入口 `require_credential`
  转 `CaptchaVerifyError`（20101）；挑战不存在 / 过期走 `CaptchaExpiredError`（20102）。
- 短信渠道不可用（通知器 `delivered=False` / 抛异常）抛 `ServiceUnavailableError` 且删除已写入挑战（不静默
  放行）；冷却 / 超频抛 `CaptchaTooFrequentError`（20103 / 429，不重置倒计时）。短信模板与真实渠道归阶段八。
"""

from __future__ import annotations

import asyncio
import base64
import hmac
import io
import json
import random
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont
from redis.asyncio import Redis as AsyncRedis

from bms_core.captcha.base import (
    CAPTCHA_TTL,
    NULL_CAPTCHA_PAYLOAD,
    SLIDER_TOLERANCE,
    SMS_CAPTCHA_LENGTH,
    BaseCaptcha,
    CaptchaChallenge,
    CaptchaCredential,
    CaptchaKind,
    CaptchaScenePolicy,
    build_captcha_key,
    default_scene_policy,
    mask_phone,
)
from bms_core.core.base import BaseObject
from bms_core.core.context import get_current_client_ip
from bms_core.core.exceptions import (
    CaptchaExpiredError,
    CaptchaTooFrequentError,
    CaptchaVerifyError,
    ParamError,
    PluginError,
    ServiceUnavailableError,
)
from bms_core.core.logging import get_logger
from bms_core.notify.base import BaseNotifier, NotificationMessage, NotifyChannel
from bms_core.notify.null import NullNotifier
from bms_core.ratelimit.base import BaseRateLimiter, RateLimitRule, build_rate_limit_key
from bms_core.ratelimit.null import NullRateLimiter

__all__ = [
    "CAPTCHA_CHARS",
    "SMS_CAPTCHA_DIGITS",
    "SMS_CAPTCHA_TEMPLATE",
    "CaptchaImageOptions",
    "CaptchaSliderOptions",
    "CaptchaSmsOptions",
    "DefaultCaptcha",
]

_LOGGER = get_logger("bms")

CAPTCHA_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
"""图形码字符集（去 `I` / `O` / `0` / `1` 等易混字符）。"""

SMS_CAPTCHA_DIGITS = "0123456789"
"""短信验证码字符集（纯数字）。"""

SMS_CAPTCHA_TEMPLATE = "您的验证码是 {code}，{minutes} 分钟内有效，请勿泄露。"
"""短信内容模板（占位渲染；真实模板与 i18n 归阶段八）。"""

_SMS_COOLDOWN_DIMENSION = "sms-cooldown"
"""短信重发冷却限流维度（目标为 `{手机号}:{场景}`）。"""

_SMS_ACCOUNT_DIMENSION = "sms-account"
"""短信账号维度（目标为手机号）。"""

_SMS_IP_DIMENSION = "ip"
"""短信来源 IP 限流维度（与登录 `_IP_DIMENSION` 同口径）。"""


def _dump(record: Mapping[str, object]) -> str:
    """序列化挑战记录（JSON；不可序列化项经 `default=str` 兜底）。

    Args:
        record: 挑战记录。

    Returns:
        str: JSON 字符串。
    """
    return json.dumps(dict(record), ensure_ascii=False, default=str)


def _png(image: Image.Image) -> bytes:
    """序列化图片为 PNG 字节。

    Args:
        image: Pillow 图片对象。

    Returns:
        bytes: PNG 字节。
    """
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _load(raw: object) -> dict[str, object] | None:
    """反序列化挑战记录（失败按未命中）。

    Args:
        raw: Redis 原始值。

    Returns:
        dict[str, object] | None: 挑战记录；未命中 / 脏值返回 None。
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return cast("dict[str, object]", parsed)


def _int_option(options: Mapping[str, object], key: str, default: int, minimum: int, maximum: int) -> int:
    """从选项映射取整数项并做范围校验（缺失取缺省，非法拒启）。

    Args:
        options: `[captcha].options` 映射。
        key: 选项键。
        default: 缺省值。
        minimum: 允许下限。
        maximum: 允许上限。

    Returns:
        int: 校验通过的整数选项。

    Raises:
        PluginError: 类型非法（布尔 / 非数值 / 不可转换）或超出范围。
    """
    raw = options.get(key, default)
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise PluginError(f"验证码出图选项非法：{key}={raw!r}（应为整数）")
    try:
        value = int(raw)
    except ValueError as exc:
        raise PluginError(f"验证码出图选项非法：{key}={raw!r}（应为整数）") from exc
    if not minimum <= value <= maximum:
        raise PluginError(f"验证码出图选项越界：{key}={value}（允许 {minimum} ~ {maximum}）")
    return value


@dataclass(frozen=True)
class CaptchaImageOptions(BaseObject):
    """图形码出图参数（非敏感；`from_options` 从 `[captcha].options` 解析并校验）。"""

    width: int = 160
    """画布宽（像素）。"""

    height: int = 60
    """画布高（像素）。"""

    length: int = 4
    """字符数。"""

    font_size: int = 36
    """字号。"""

    noise_lines: int = 4
    """干扰线条数。"""

    noise_dots: int = 60
    """噪点数。"""

    rotate_degrees: int = 25
    """单字符最大旋转角度。"""

    @classmethod
    def from_options(cls, options: Mapping[str, object] | None = None) -> CaptchaImageOptions:
        """从 `[captcha].options` 解析出图参数（缺失取缺省，非法拒启）。

        Args:
            options: 选项映射（缺省空映射）。

        Returns:
            CaptchaImageOptions: 出图参数。

        Raises:
            PluginError: 任一选项类型非法 / 越界。
        """
        values = options or {}
        height = _int_option(values, "height", 60, 30, 200)
        return cls(
            width=_int_option(values, "width", 160, 80, 400),
            height=height,
            length=_int_option(values, "length", 4, 1, 8),
            font_size=_int_option(values, "font_size", 36, 12, height),
            noise_lines=_int_option(values, "noise_lines", 4, 0, 10),
            noise_dots=_int_option(values, "noise_dots", 60, 0, 500),
            rotate_degrees=_int_option(values, "rotate_degrees", 25, 0, 45),
        )


@dataclass(frozen=True)
class CaptchaSliderOptions(BaseObject):
    """滑块出图 / 判定参数（非敏感；`from_options` 从 `[captcha].options` 的 `slider_` 前缀键解析并校验）。"""

    width: int = 300
    """背景画布宽（像素）。"""

    height: int = 150
    """背景画布高（像素）。"""

    piece_size: int = 48
    """块图边长（像素）。"""

    tolerance: int = SLIDER_TOLERANCE
    """落点容差（像素；末点 `x` 与缺口 `gap_x` 的最大允许偏差）。"""

    min_duration_ms: int = 300
    """轨迹总时长下限（毫秒；0 表示不校验）。"""

    min_points: int = 2
    """轨迹最少点数。"""

    @classmethod
    def from_options(cls, options: Mapping[str, object] | None = None) -> CaptchaSliderOptions:
        """从 `[captcha].options` 解析滑块参数（缺失取缺省，非法拒启）。

        Args:
            options: 选项映射（缺省空映射）。

        Returns:
            CaptchaSliderOptions: 滑块参数。

        Raises:
            PluginError: 任一选项类型非法 / 越界。
        """
        values = options or {}
        width = _int_option(values, "slider_width", 300, 160, 600)
        height = _int_option(values, "slider_height", 150, 80, 300)
        max_piece = (min(width, height) - 1) // 2
        return cls(
            width=width,
            height=height,
            piece_size=_int_option(values, "slider_piece_size", min(48, max_piece), 16, max_piece),
            tolerance=_int_option(values, "slider_tolerance", SLIDER_TOLERANCE, 0, 50),
            min_duration_ms=_int_option(values, "slider_min_duration_ms", 300, 0, 10000),
            min_points=_int_option(values, "slider_min_points", 2, 1, 100),
        )


@dataclass(frozen=True)
class CaptchaSmsOptions(BaseObject):
    """短信选项（非敏感；`from_options` 从 `[captcha].options` 的 `sms_` 前缀键解析并校验）。"""

    code_length: int = SMS_CAPTCHA_LENGTH
    """验证码位数（纯数字；缺省 6）。"""

    account_limit: int = 5
    """账号（手机号）窗口内发送上限。"""

    ip_limit: int = 20
    """来源 IP 窗口内发送上限。"""

    window: int = 3600
    """频次窗口（秒）。"""

    @classmethod
    def from_options(cls, options: Mapping[str, object] | None = None) -> CaptchaSmsOptions:
        """从 `[captcha].options` 解析短信选项（缺失取缺省，非法拒启）。

        Args:
            options: 选项映射（缺省空映射）。

        Returns:
            CaptchaSmsOptions: 短信选项。

        Raises:
            PluginError: 任一选项类型非法 / 越界。
        """
        values = options or {}
        return cls(
            code_length=_int_option(values, "sms_code_length", SMS_CAPTCHA_LENGTH, 4, 8),
            account_limit=_int_option(values, "sms_account_limit", 5, 1, 100),
            ip_limit=_int_option(values, "sms_ip_limit", 20, 1, 1000),
            window=_int_option(values, "sms_window", 3600, 60, 86400),
        )


class DefaultCaptcha(BaseCaptcha):
    """图形码 / 滑块 / 短信三形态真实实现（Pillow 出图 + Redis 一次性校验）。"""

    plugin_name: str = "default"
    """实现名（配置 `[captcha].provider = "default"` 命中）。"""

    def __init__(
        self,
        *,
        url: str | None,
        client: AsyncRedis | None = None,
        image: CaptchaImageOptions | None = None,
        slider: CaptchaSliderOptions | None = None,
        sms: CaptchaSmsOptions | None = None,
        notifier: BaseNotifier | None = None,
        rate_limiter: BaseRateLimiter | None = None,
    ) -> None:
        """初始化（懒建连；`url` 无缺省值以防被插件注册表自动收集）。

        Args:
            url: Redis 连接串（缺省由装配工厂取 `settings.redis.url` 注入）。
            client: 异步客户端（测试注入 `fakeredis.aioredis.FakeRedis`；缺省按 `url` 懒建）。
            image: 图形码出图参数（缺省平台默认）。
            slider: 滑块出图 / 判定参数（缺省平台默认）。
            sms: 短信选项（缺省平台默认）。
            notifier: 通知器（缺省 `NullNotifier`；由装配工厂注入真实 / 占位实现）。
            rate_limiter: 限流器（缺省 `NullRateLimiter` 恒定放行；由装配工厂注入）。
        """
        self._url = url
        self._client = client
        self._image = image or CaptchaImageOptions()
        self._slider = slider or CaptchaSliderOptions()
        self._sms = sms or CaptchaSmsOptions()
        self._notifier = notifier or NullNotifier()
        self._rate_limiter = rate_limiter or NullRateLimiter()

    @property
    def client(self) -> AsyncRedis:
        """取异步客户端（懒建，不建连）。

        Returns:
            AsyncRedis: 异步客户端实例。
        """
        if self._client is None:
            self._client = AsyncRedis.from_url(self._url or "", decode_responses=True)  # pyright: ignore[reportUnknownMemberType]
        return self._client

    async def generate(self, scene: str = "login", *, kind: CaptchaKind = CaptchaKind.IMAGE) -> CaptchaChallenge:
        """生成验证码挑战（图形码 Pillow 出图 / 滑块的合成出图经线程池；写入 Redis 记录）。

        Args:
            scene: 使用场景。
            kind: 挑战类型（图形 / 滑块；短信改走 `send_sms` 端点）。

        Returns:
            CaptchaChallenge: 挑战值对象（编号 / 图片字节 / 有效期 / 场景 / 形态参数）。

        Raises:
            ParamError: 短信形态（10001，请经 `/captcha/sms` 端点发送）或未支持形态。
            ServiceUnavailableError: Redis 不可用（10007 / 503）。
        """
        if kind is CaptchaKind.SLIDER:
            return await self._generate_slider(scene)
        if kind is CaptchaKind.SMS:
            raise ParamError("短信验证码请经 /captcha/sms 端点发送")
        if kind is not CaptchaKind.IMAGE:
            raise ParamError(f"未支持的验证码形态：{kind}")
        code = self._random_code()
        image = await asyncio.to_thread(self._render, code)
        captcha_id = uuid4().hex
        record: dict[str, object] = {"code": code, "scene": scene, "kind": kind.value, "fails": 0}
        try:
            await self.client.set(build_captcha_key(captcha_id), _dump(record), ex=CAPTCHA_TTL)  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            _LOGGER.warning("验证码写入降级", captcha_id=captcha_id[:8], error=str(exc))
            raise ServiceUnavailableError("验证码服务暂不可用，请稍后重试") from exc
        return CaptchaChallenge(
            captcha_id=captcha_id,
            image=image,
            expires_in=CAPTCHA_TTL,
            scene=scene,
            kind=CaptchaKind.IMAGE,
            payload=NULL_CAPTCHA_PAYLOAD,
        )

    async def _generate_slider(self, scene: str) -> CaptchaChallenge:
        """生成滑块挑战（合成带缺口背景 + 滑块块图；缺口坐标只存 Redis 不下发）。

        Args:
            scene: 使用场景。

        Returns:
            CaptchaChallenge: 挑战值对象（`image` 为空字节，出图数据经 `payload` 承载）。

        Raises:
            ServiceUnavailableError: Redis 不可用（10007 / 503）。
        """
        background, slider, gap_x, gap_y = await asyncio.to_thread(self._render_slider)
        captcha_id = uuid4().hex
        record: dict[str, object] = {
            "kind": CaptchaKind.SLIDER.value,
            "scene": scene,
            "gap_x": gap_x,
            "gap_y": gap_y,
            "fails": 0,
        }
        payload = _dump(
            {
                "background": base64.b64encode(background).decode(),
                "slider": base64.b64encode(slider).decode(),
                "width": self._slider.width,
                "height": self._slider.height,
            }
        )
        try:
            await self.client.set(build_captcha_key(captcha_id), _dump(record), ex=CAPTCHA_TTL)  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            _LOGGER.warning("验证码写入降级", captcha_id=captcha_id[:8], error=str(exc))
            raise ServiceUnavailableError("验证码服务暂不可用，请稍后重试") from exc
        return CaptchaChallenge(
            captcha_id=captcha_id,
            image=b"",
            expires_in=CAPTCHA_TTL,
            scene=scene,
            kind=CaptchaKind.SLIDER,
            payload=payload,
        )

    async def send_sms(self, phone: str, scene: str = "login") -> CaptchaChallenge:
        """发送短信验证码（冷却 / 账号 / IP 限次 → 生成码写 Redis → 经通知基座下发 → 脱敏回显）。

        Args:
            phone: 目标手机号（回显值经 `mask_phone` 脱敏；真实渠道收件目标为原值）。
            scene: 使用场景。

        Returns:
            CaptchaChallenge: 挑战值对象（`kind=sms` / 脱敏目标 / 有效期 / 冷却）；不含验证码明文。

        Raises:
            CaptchaTooFrequentError: 冷却未到或账号 / IP 频次超限（20103 / 429；不重置倒计时）。
            ServiceUnavailableError: Redis 不可用或通知渠道不可用（10007 / 503，明确失败不放行）。
        """
        policy = await self.policy(scene)
        await self._enforce_sms_limits(phone, scene, policy)
        code = self._random_sms_code()
        captcha_id = uuid4().hex
        record: dict[str, object] = {"kind": CaptchaKind.SMS.value, "scene": scene, "code": code, "fails": 0}
        try:
            await self.client.set(build_captcha_key(captcha_id), _dump(record), ex=policy.ttl)  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            _LOGGER.warning("验证码写入降级", captcha_id=captcha_id[:8], error=str(exc))
            raise ServiceUnavailableError("验证码服务暂不可用，请稍后重试") from exc
        try:
            result = await self._notifier.send(self._sms_message(phone, code, captcha_id, policy))
        except Exception as exc:
            await self._discard(captcha_id)
            _LOGGER.warning("短信渠道发送异常", captcha_id=captcha_id[:8], error=str(exc))
            raise ServiceUnavailableError("短信发送暂不可用，请稍后重试") from exc
        if not result.delivered:
            await self._discard(captcha_id)
            _LOGGER.warning("短信发送未送达", captcha_id=captcha_id[:8], detail=result.detail)
            raise ServiceUnavailableError("短信发送暂不可用，请稍后重试")
        return CaptchaChallenge(
            captcha_id=captcha_id,
            image=b"",
            expires_in=policy.ttl,
            scene=scene,
            kind=CaptchaKind.SMS,
            payload="",
            target=mask_phone(phone),
            cooldown=policy.cooldown,
        )

    async def verify_credential(self, credential: CaptchaCredential) -> bool:
        """校验验证码凭证（判定入口，不抛错；成功后挑战即失效）。

        Args:
            credential: 验证码凭证（图形 / 短信用 `code`；滑块用 `trace`）。

        Returns:
            bool: 校验通过为 True；不存在 / 过期 / 不匹配 / Redis 不可用均为 False（fail-closed）。
        """
        try:
            record, ttl_ms = await self._take(credential.captcha_id)
        except ServiceUnavailableError as exc:
            _LOGGER.warning("验证码校验降级", captcha_id=credential.captcha_id[:8], error=str(exc))
            return False
        if record is None:
            return False
        if self._matches(record, credential):
            return True
        await self._register_failure(credential.captcha_id, record, ttl_ms)
        return False

    async def require_credential(self, credential: CaptchaCredential) -> None:
        """强制校验验证码凭证（接口层一行接入；区分不存在 / 过期与码不符）。

        Args:
            credential: 验证码凭证。

        Raises:
            CaptchaExpiredError: 挑战不存在 / 已过期（20102 / 404）。
            CaptchaVerifyError: 校验码不匹配或 Redis 不可用（20101 / 200）。
        """
        try:
            record, ttl_ms = await self._take(credential.captcha_id)
        except ServiceUnavailableError as exc:
            _LOGGER.warning("验证码校验降级", captcha_id=credential.captcha_id[:8], error=str(exc))
            raise CaptchaVerifyError("验证码服务暂不可用") from exc
        if record is None:
            raise CaptchaExpiredError("验证码不存在或已过期")
        if not self._matches(record, credential):
            await self._register_failure(credential.captcha_id, record, ttl_ms)
            raise CaptchaVerifyError("验证码校验不通过")

    async def policy(self, scene: str) -> CaptchaScenePolicy:
        """取场景策略（本阶段返回平台默认；按租户读取归 03_04）。

        Args:
            scene: 使用场景。

        Returns:
            CaptchaScenePolicy: 平台默认场景策略（未登记场景回落通用默认）。
        """
        return default_scene_policy(scene)

    async def aclose(self) -> None:
        """释放 Redis 客户端（幂等）。"""
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.aclose()  # pyright: ignore[reportUnknownMemberType]
            except Exception as exc:  # pragma: no cover - 关闭失败仅日志
                _LOGGER.warning("验证码存储关闭失败", error=str(exc))

    def _random_code(self) -> str:
        """生成随机校验码（字符集去易混字符）。

        Returns:
            str: 指定长度的校验码。
        """
        return "".join(random.choice(CAPTCHA_CHARS) for _ in range(self._image.length))

    def _random_sms_code(self) -> str:
        """生成随机短信验证码（纯数字，长度取短信选项）。

        Returns:
            str: 指定长度的数字验证码。
        """
        return "".join(random.choice(SMS_CAPTCHA_DIGITS) for _ in range(self._sms.code_length))

    async def _enforce_sms_limits(self, phone: str, scene: str, policy: CaptchaScenePolicy) -> None:
        """按冷却 / 账号 / IP 三维校验短信发送配额（经限流基座；任一不过即拒）。

        Args:
            phone: 目标手机号。
            scene: 使用场景。
            policy: 场景策略（提供重发冷却窗口）。

        Raises:
            CaptchaTooFrequentError: 冷却未到或账号 / IP 频次超限（20103 / 429）。
        """
        await self._enforce_limit(
            build_rate_limit_key(dimension=_SMS_COOLDOWN_DIMENSION, target=f"{phone}:{scene}"),
            RateLimitRule(limit=1, window=max(1, policy.cooldown)),
            "验证码发送过于频繁，请稍后重试",
        )
        await self._enforce_limit(
            build_rate_limit_key(dimension=_SMS_ACCOUNT_DIMENSION, target=phone),
            RateLimitRule(limit=self._sms.account_limit, window=self._sms.window),
            "该手机号发送次数过多，请稍后重试",
        )
        ip = get_current_client_ip()
        if ip:
            await self._enforce_limit(
                build_rate_limit_key(dimension=_SMS_IP_DIMENSION, target=ip),
                RateLimitRule(limit=self._sms.ip_limit, window=self._sms.window),
                "当前来源发送次数过多，请稍后重试",
            )

    async def _enforce_limit(self, key: str, rule: RateLimitRule, message: str) -> None:
        """校验单项限流配额（超限抛验证码频次错误并回带剩余秒数）。

        Args:
            key: 限流 key。
            rule: 限流规则（次数 / 窗口）。
            message: 超限提示。

        Raises:
            CaptchaTooFrequentError: 超出配额（20103 / 429；`data.reset_after` 为剩余秒数）。
        """
        decision = await self._rate_limiter.check(key, rule)
        if not decision.allowed:
            raise CaptchaTooFrequentError(message, data={"reset_after": decision.reset_after})

    def _sms_message(self, phone: str, code: str, captcha_id: str, policy: CaptchaScenePolicy) -> NotificationMessage:
        """构造短信通知消息（收件目标为原值手机号；内容经基座模板占位渲染）。

        Args:
            phone: 目标手机号。
            code: 验证码。
            captcha_id: 挑战编号。
            policy: 场景策略（提供有效期口径）。

        Returns:
            NotificationMessage: 短信渠道通知消息。
        """
        return NotificationMessage(
            channel=NotifyChannel.SMS,
            recipient=phone,
            content=SMS_CAPTCHA_TEMPLATE.format(code=code, minutes=max(1, policy.ttl // 60)),
            biz_type="captcha",
            biz_id=captcha_id,
        )

    async def _discard(self, captcha_id: str) -> None:
        """删除已写入的挑战（发送失败时清理，避免悬挂可校验记录；失败仅日志）。

        Args:
            captcha_id: 挑战编号。
        """
        try:
            await self.client.delete(build_captcha_key(captcha_id))  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            _LOGGER.warning("验证码清理降级", captcha_id=captcha_id[:8], error=str(exc))

    def _render(self, code: str) -> bytes:
        """Pillow 出图（同步阻塞，调用方经 `asyncio.to_thread` 执行）。

        Args:
            code: 校验码。

        Returns:
            bytes: PNG 图片字节。
        """
        opts = self._image
        background = (random.randint(230, 255), random.randint(230, 255), random.randint(230, 255))
        image = Image.new("RGB", (opts.width, opts.height), background)
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=opts.font_size)
        step = max(1, (opts.width - 16) // max(1, opts.length))
        x = 8
        for char in code:
            layer = Image.new("RGBA", (opts.font_size * 2, opts.font_size * 2), (0, 0, 0, 0))
            ImageDraw.Draw(layer).text(
                (opts.font_size // 2, opts.font_size // 2),
                char,
                font=font,
                fill=(random.randint(0, 90), random.randint(0, 90), random.randint(0, 90), 255),
            )
            rotated = layer.rotate(
                random.uniform(-opts.rotate_degrees, opts.rotate_degrees),
                resample=Image.Resampling.BICUBIC,
            )
            image.paste(rotated, (x, random.randint(0, max(0, opts.height - opts.font_size))), rotated)
            x += step
        for _ in range(opts.noise_lines):
            draw.line(
                [
                    (random.randint(0, opts.width), random.randint(0, opts.height)),
                    (random.randint(0, opts.width), random.randint(0, opts.height)),
                ],
                fill=(random.randint(60, 180), random.randint(60, 180), random.randint(60, 180)),
                width=1,
            )
        for _ in range(opts.noise_dots):
            point = (random.randint(0, opts.width), random.randint(0, opts.height))
            draw.point(point, fill=(random.randint(60, 180), random.randint(60, 180), random.randint(60, 180)))
        return _png(image)

    def _render_slider(self) -> tuple[bytes, bytes, int, int]:
        """Pillow 合成滑块出图（同步阻塞，调用方经 `asyncio.to_thread` 执行）。

        生成带缺口的背景图与缺口区域的独立块图；缺口位置在随机坐标处，**只随返回值入 Redis，不下发**。

        Returns:
            tuple[bytes, bytes, int, int]: 背景 PNG 字节、块图 PNG 字节、缺口横向坐标、缺口纵向坐标。
        """
        opts = self._slider
        piece = opts.piece_size
        background = self._slider_background(opts.width, opts.height)
        gap_x = random.randint(piece, opts.width - piece - 1)
        gap_y = random.randint(piece, opts.height - piece - 1)
        region = (gap_x, gap_y, gap_x + piece, gap_y + piece)
        slider = background.crop(region)
        image_draw = ImageDraw.Draw(background)
        image_draw.rectangle(region, fill=(0, 0, 0), outline=(255, 255, 255), width=2)
        return _png(background), _png(slider), gap_x, gap_y

    @staticmethod
    def _slider_background(width: int, height: int) -> Image.Image:
        """生成滑块背景图（对角渐变底 + 随机噪点，抗简单识别）。

        Args:
            width: 画布宽（像素）。
            height: 画布高（像素）。

        Returns:
            Image.Image: RGB 背景图。
        """
        top = (random.randint(40, 200), random.randint(40, 200), random.randint(40, 200))
        bottom = (random.randint(40, 200), random.randint(40, 200), random.randint(40, 200))
        gradient = Image.new("RGB", (width, height))
        gradient_draw = ImageDraw.Draw(gradient)
        for y in range(height):
            ratio = y / max(1, height - 1)
            color = tuple(int(top[index] + (bottom[index] - top[index]) * ratio) for index in range(3))
            gradient_draw.line([(0, y), (width, y)], fill=color)
        noise = Image.effect_noise((width, height), 32).convert("RGB")
        return Image.blend(gradient, noise, 0.15)

    async def _take(self, captcha_id: str) -> tuple[dict[str, object] | None, int]:
        """一次性原子取出挑战记录（先取剩余 TTL 再 `GETDEL`；成功后记录即删除）。

        Args:
            captcha_id: 挑战编号。

        Returns:
            tuple[dict[str, object] | None, int]: 挑战记录与剩余有效期（毫秒；不存在 / 无过期
            为 Redis `PTTL` 语义值 -2 / -1）。

        Raises:
            ServiceUnavailableError: Redis 不可用（10007 / 503）。
        """
        key = build_captcha_key(captcha_id)
        try:
            ttl_ms = int(await self.client.pttl(key))  # pyright: ignore[reportUnknownMemberType]
            raw = await self.client.getdel(key)  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            raise ServiceUnavailableError("验证码服务暂不可用，请稍后重试") from exc
        return _load(raw), ttl_ms

    def _matches(self, record: Mapping[str, object], credential: CaptchaCredential) -> bool:
        """按记录形态分派比对（滑块走轨迹判定，其余走校验码比对）。

        Args:
            record: 挑战记录。
            credential: 用户凭证。

        Returns:
            bool: 校验通过为 True。
        """
        if record.get("kind") == CaptchaKind.SLIDER:
            return self._matches_slider(record, credential)
        return self._matches_code(record, credential)

    def _matches_code(self, record: Mapping[str, object], credential: CaptchaCredential) -> bool:
        """比对校验码（大小写不敏感、常量时间）。

        Args:
            record: 挑战记录。
            credential: 用户凭证。

        Returns:
            bool: 校验码匹配为 True。
        """
        expected = str(record.get("code") or "")
        if not expected:
            return False
        return hmac.compare_digest(expected.upper(), credential.code.strip().upper())

    def _matches_slider(self, record: Mapping[str, object], credential: CaptchaCredential) -> bool:
        """判定滑块轨迹（落点容差 + 轨迹合理性双因子；`y` 轴不校验）。

        Args:
            record: 挑战记录（须含合法整数 `gap_x`）。
            credential: 用户凭证（轨迹点序列 `(x, y, 相对起点毫秒)`）。

        Returns:
            bool: 轨迹通过为 True；缺口缺失 / 非法、点数不足、时间回退、时长过短或落点超差均为 False。
        """
        gap_x = record.get("gap_x")
        if isinstance(gap_x, bool) or not isinstance(gap_x, int):
            return False
        trace = credential.trace
        opts = self._slider
        if len(trace) < opts.min_points:
            return False
        previous_t = -1
        for _x, _y, point_t in trace:
            if point_t < 0 or point_t < previous_t:
                return False
            previous_t = point_t
        if opts.min_duration_ms > 0 and trace[-1][2] - trace[0][2] < opts.min_duration_ms:
            return False
        return abs(trace[-1][0] - gap_x) <= opts.tolerance

    async def _register_failure(self, captcha_id: str, record: Mapping[str, object], ttl_ms: int) -> None:
        """回写失败挑战（保留剩余 TTL）并累计失败次数（失败可重试）。

        Args:
            captcha_id: 挑战编号。
            record: 挑战记录。
            ttl_ms: 剩余有效期（毫秒；`GETDEL` 前取，>0 时按剩余重设）。
        """
        updated = dict(record)
        raw_fails = updated.get("fails")
        fails = raw_fails if isinstance(raw_fails, int) else 0
        updated["fails"] = fails + 1
        try:
            key = build_captcha_key(captcha_id)
            if ttl_ms > 0:
                await self.client.set(key, _dump(updated), px=ttl_ms)  # pyright: ignore[reportUnknownMemberType]
            else:
                await self.client.set(key, _dump(updated))  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            _LOGGER.warning("验证码失败计数回写降级", captcha_id=captcha_id[:8], error=str(exc))
