"""验证码能力域：图形码真实实现（Pillow 出图 + Redis 一次性校验；滑块 / 短信随 03_02 / 03_03 回补）。

- `CaptchaImageOptions`：图形码出图参数（从 `[captcha].options` 解析、带范围校验，非敏感）。
- `DefaultCaptcha`（插件名 `default`）：图形码真实出题（Pillow 经线程池出图，不阻塞事件循环）与
  一次性校验——挑战存 `bms:global:captcha:{uuid}`（JSON，TTL 300 秒），校验用 `GETDEL` 原子取出
  （成功即失效、单次有效），失败回写并累计 `fails`（失败可重试）。
- 降级口径（fail-closed）：Redis 不可用时出题 / 短信抛 `ServiceUnavailableError`（10007 / 503，明确报错）；
  校验判定入口 `verify_credential` 返回 False（不放行、不抛错，保持契约），强制入口 `require_credential`
  转 `CaptchaVerifyError`（20101）；挑战不存在 / 过期走 `CaptchaExpiredError`（20102）。
- 滑块 / 短信本阶段未启用：出题（`kind=slider` / `sms`）与 `send_sms` 抛 `ServiceUnavailableError`
  （明确失败不放行），真实能力由 03_02 / 03_03 在同一实现类内补齐。
"""

from __future__ import annotations

import asyncio
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
    BaseCaptcha,
    CaptchaChallenge,
    CaptchaCredential,
    CaptchaKind,
    CaptchaScenePolicy,
    build_captcha_key,
    default_scene_policy,
)
from bms_core.core.base import BaseObject
from bms_core.core.exceptions import (
    CaptchaExpiredError,
    CaptchaVerifyError,
    PluginError,
    ServiceUnavailableError,
)
from bms_core.core.logging import get_logger

__all__ = [
    "CAPTCHA_CHARS",
    "CaptchaImageOptions",
    "DefaultCaptcha",
]

_LOGGER = get_logger("bms")

CAPTCHA_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
"""图形码字符集（去 `I` / `O` / `0` / `1` 等易混字符）。"""


def _dump(record: Mapping[str, object]) -> str:
    """序列化挑战记录（JSON；不可序列化项经 `default=str` 兜底）。

    Args:
        record: 挑战记录。

    Returns:
        str: JSON 字符串。
    """
    return json.dumps(dict(record), ensure_ascii=False, default=str)


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


class DefaultCaptcha(BaseCaptcha):
    """图形码真实实现（Pillow 出图 + Redis 一次性校验；滑块 / 短信未启用时 fail-closed）。"""

    plugin_name: str = "default"
    """实现名（配置 `[captcha].provider = "default"` 命中）。"""

    def __init__(
        self,
        *,
        url: str | None,
        client: AsyncRedis | None = None,
        image: CaptchaImageOptions | None = None,
    ) -> None:
        """初始化（懒建连；`url` 无缺省值以防被插件注册表自动收集）。

        Args:
            url: Redis 连接串（缺省由装配工厂取 `settings.redis.url` 注入）。
            client: 异步客户端（测试注入 `fakeredis.aioredis.FakeRedis`；缺省按 `url` 懒建）。
            image: 出图参数（缺省平台默认）。
        """
        self._url = url
        self._client = client
        self._image = image or CaptchaImageOptions()

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
        """生成图形码挑战（Pillow 出图经线程池；写入 Redis 记录）。

        Args:
            scene: 使用场景。
            kind: 挑战类型（本期只支持图形；滑块 / 短信抛明确错误）。

        Returns:
            CaptchaChallenge: 挑战值对象（编号 / PNG 字节 / 有效期 / 场景）。

        Raises:
            ServiceUnavailableError: 形态未启用（滑块 / 短信）或 Redis 不可用（10007 / 503）。
        """
        if kind is not CaptchaKind.IMAGE:
            raise ServiceUnavailableError(f"验证码形态尚未启用：{kind}")
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

    async def send_sms(self, phone: str, scene: str = "login") -> CaptchaChallenge:
        """短信验证码发送（本阶段未启用，明确失败不放行；真实实现归 03_03）。

        Args:
            phone: 目标手机号（未使用）。
            scene: 使用场景（未使用）。

        Returns:
            CaptchaChallenge: 不会返回。

        Raises:
            ServiceUnavailableError: 短信形态未启用（10007 / 503）。
        """
        del phone, scene
        raise ServiceUnavailableError("短信验证码尚未启用")

    async def verify_credential(self, credential: CaptchaCredential) -> bool:
        """校验验证码凭证（判定入口，不抛错；成功后挑战即失效）。

        Args:
            credential: 验证码凭证（图形 / 短信用 `code`；滑块 `trace` 归 03_02）。

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
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

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
