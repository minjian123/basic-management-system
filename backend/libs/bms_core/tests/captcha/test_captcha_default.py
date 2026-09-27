"""图形验证码真实实现测试（Kiwi 2204）：出图 / 一次性校验 / 失败计数 / 错误码 / fail-closed / 配置 / 装配。"""

import io
import json
from types import SimpleNamespace
from typing import Any, cast

import fakeredis.aioredis
import pytest
from fastapi import Request
from PIL import Image
from redis.asyncio import Redis

from bms_core.captcha.base import (
    BaseCaptcha,
    CaptchaCredential,
    CaptchaKind,
    build_captcha_key,
    get_captcha,
)
from bms_core.captcha.default import CAPTCHA_CHARS, CaptchaImageOptions, DefaultCaptcha
from bms_core.captcha.null import NullCaptcha
from bms_core.core import plugin as plugin_module
from bms_core.core.config import PluginSelection, Settings
from bms_core.core.exceptions import (
    CaptchaExpiredError,
    CaptchaVerifyError,
    PluginError,
    ServiceUnavailableError,
)
from bms_core.core.plugin import PluginRegistry

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _captcha(client: object, **options: object) -> DefaultCaptcha:
    """构造图形码实现（注入测试客户端）。

    Args:
        client: Redis 客户端替身。
        **options: 出图选项覆盖。

    Returns:
        DefaultCaptcha: 图形码实现。
    """
    image = CaptchaImageOptions.from_options(options) if options else None
    return DefaultCaptcha(url=None, client=cast("Redis", client), image=image)


async def _record(client: Redis, captcha_id: str) -> dict[str, Any]:
    """读取挑战记录（直接查 Redis）。

    Args:
        client: Redis 客户端。
        captcha_id: 挑战编号。

    Returns:
        dict: 挑战记录。
    """
    raw = await client.get(build_captcha_key(captcha_id))
    assert raw is not None
    return cast("dict[str, Any]", json.loads(raw))


def _request(settings: Settings) -> Request:
    """构造最小请求替身（提供者只读 `app.state.settings`）。

    Args:
        settings: 应用配置。

    Returns:
        Request: 请求替身。
    """
    return cast("Request", SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings))))


@pytest.fixture
def redis_client() -> fakeredis.aioredis.FakeRedis:
    """fakeredis 客户端（与真实 redis-py 同接口，decode_responses）。"""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.mark.kiwi_id(2204)
async def test_generate_image_and_record(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """出图非空且为 PNG、尺寸按选项、记录落 Redis（码字符集 / 场景 / 计数）。"""
    captcha = _captcha(redis_client)
    challenge = await captcha.generate("login")

    assert challenge.kind is CaptchaKind.IMAGE
    assert challenge.image.startswith(_PNG_MAGIC)
    assert Image.open(io.BytesIO(challenge.image)).size == (160, 60)
    assert challenge.expires_in == 300
    assert challenge.payload == "{}"
    assert challenge.target == ""
    assert challenge.cooldown == 0

    record = await _record(redis_client, challenge.captcha_id)
    assert record["kind"] == "image"
    assert record["scene"] == "login"
    assert record["fails"] == 0
    assert len(record["code"]) == 4
    assert all(char in CAPTCHA_CHARS for char in record["code"])
    await captcha.aclose()


@pytest.mark.kiwi_id(2204)
async def test_verify_success_single_use(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """正确码校验通过（大小写不敏感）且挑战单次失效（二次使用 20102）。"""
    captcha = _captcha(redis_client)
    challenge = await captcha.generate("login")
    code = (await _record(redis_client, challenge.captcha_id))["code"]

    assert await captcha.verify_credential(
        CaptchaCredential(captcha_id=challenge.captcha_id, kind=CaptchaKind.IMAGE, code=code.lower())
    )
    assert not await captcha.verify_credential(
        CaptchaCredential(captcha_id=challenge.captcha_id, kind=CaptchaKind.IMAGE, code=code)
    )

    with pytest.raises(CaptchaExpiredError) as raised:
        await captcha.require_credential(CaptchaCredential(captcha_id=challenge.captcha_id, code=code))
    assert raised.value.code == 20102
    assert raised.value.http_status == 404
    await captcha.aclose()


@pytest.mark.kiwi_id(2204)
async def test_verify_failure_counts_and_retry(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """失败码校验返回 False、记录 fails 递增且保留 TTL（可重试）。"""
    captcha = _captcha(redis_client)
    challenge = await captcha.generate("login")

    for expected in (1, 2):
        assert not await captcha.verify_credential(CaptchaCredential(captcha_id=challenge.captcha_id, code="zzzz"))
        record = await _record(redis_client, challenge.captcha_id)
        assert record["fails"] == expected
        assert await redis_client.ttl(build_captcha_key(challenge.captcha_id)) > 0

    record = await _record(redis_client, challenge.captcha_id)
    assert await captcha.verify_credential(CaptchaCredential(captcha_id=challenge.captcha_id, code=record["code"]))
    await captcha.aclose()


@pytest.mark.kiwi_id(2204)
async def test_require_credential_error_codes(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """强制入口错误码：码不符 20101、挑战不存在 20102。"""
    captcha = _captcha(redis_client)
    challenge = await captcha.generate("login")

    with pytest.raises(CaptchaVerifyError) as mismatch:
        await captcha.require_credential(CaptchaCredential(captcha_id=challenge.captcha_id, code="zzzz"))
    assert mismatch.value.code == 20101
    assert mismatch.value.http_status == 200

    with pytest.raises(CaptchaExpiredError) as absent:
        await captcha.require_credential(CaptchaCredential(captcha_id="absent", code="zzzz"))
    assert absent.value.code == 20102

    record = await _record(redis_client, challenge.captcha_id)
    assert (
        await captcha.require_credential(CaptchaCredential(captcha_id=challenge.captcha_id, code=record["code"]))
        is None
    )
    await captcha.aclose()


@pytest.mark.kiwi_id(2204)
async def test_redis_unavailable_fail_closed() -> None:
    """Redis 不可用 fail-closed：出题 10007/503、校验 False、强制入口 20101。"""

    class _Broken:
        """恒抛连接异常的客户端替身。"""

        async def set(self, *args: object, **kwargs: object) -> None:
            """恒定抛错。"""
            raise ConnectionError("redis down")

        async def pttl(self, *args: object, **kwargs: object) -> None:
            """恒定抛错。"""
            raise ConnectionError("redis down")

        async def getdel(self, *args: object, **kwargs: object) -> None:
            """恒定抛错。"""
            raise ConnectionError("redis down")

    captcha = _captcha(_Broken())
    with pytest.raises(ServiceUnavailableError) as raised:
        await captcha.generate("login")
    assert raised.value.code == 10007
    assert raised.value.http_status == 503

    credential = CaptchaCredential(captcha_id="x", code="y")
    assert not await captcha.verify_credential(credential)
    with pytest.raises(CaptchaVerifyError) as forced:
        await captcha.require_credential(credential)
    assert forced.value.code == 20101


@pytest.mark.kiwi_id(2204)
async def test_unsupported_kinds_fail_closed(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """短信本阶段未启用，明确失败不放行（滑块已随 03_02 启用）。"""
    captcha = _captcha(redis_client)
    with pytest.raises(ServiceUnavailableError):
        await captcha.generate("login", kind=CaptchaKind.SMS)
    with pytest.raises(ServiceUnavailableError):
        await captcha.send_sms("13812345678", "bind")
    await captcha.aclose()


@pytest.mark.kiwi_id(2204)
async def test_image_options_parse_and_validate(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """出图选项：缺省 / 覆盖生效、非法值拒启、渲染尺寸随选项。"""
    default = CaptchaImageOptions.from_options({})
    assert (default.width, default.height, default.length, default.font_size) == (160, 60, 4, 36)
    assert default == CaptchaImageOptions.from_options(None)

    custom = CaptchaImageOptions.from_options(
        {"width": "120", "height": 50, "length": 5, "noise_lines": 0, "noise_dots": 0}
    )
    assert (custom.width, custom.height, custom.length, custom.font_size) == (120, 50, 5, 36)

    bad_options: tuple[dict[str, object], ...] = (
        {"width": "abc"},
        {"width": []},
        {"length": 99},
        {"height": True},
        {"noise_dots": -1},
    )
    for bad in bad_options:
        with pytest.raises(PluginError):
            CaptchaImageOptions.from_options(bad)

    captcha = DefaultCaptcha(url=None, client=redis_client, image=custom)
    challenge = await captcha.generate("login")
    assert Image.open(io.BytesIO(challenge.image)).size == (120, 50)
    await captcha.aclose()


@pytest.mark.kiwi_id(2204)
async def test_load_and_write_variants() -> None:
    """挑战记录反序列化边界与失败回写降级（不抛业务错）。"""

    class _Stub:
        """固定 `getdel` 返回值、`set` 可控的客户端替身。"""

        def __init__(self, value: object, *, fail_write: bool = False, ttl_ms: int = 300000) -> None:
            self._value = value
            self._fail_write = fail_write
            self._ttl_ms = ttl_ms

        async def pttl(self, key: str) -> int:
            """返回固定剩余有效期（毫秒）。"""
            return self._ttl_ms

        async def getdel(self, key: str) -> object:
            """返回固定原始值。"""
            return self._value

        async def set(self, *args: object, **kwargs: object) -> None:
            """可选定抛错。"""
            if self._fail_write:
                raise ConnectionError("redis down")

    credential = CaptchaCredential(captcha_id="x", code="AB")
    assert await _captcha(_Stub(b'{"code": "AB"}')).verify_credential(credential)
    assert not await _captcha(_Stub(123)).verify_credential(credential)
    assert not await _captcha(_Stub("{bad")).verify_credential(credential)
    assert not await _captcha(_Stub("[1]")).verify_credential(credential)
    assert not await _captcha(_Stub(None)).verify_credential(credential)
    assert not await _captcha(_Stub('{"code": ""}')).verify_credential(credential)

    mismatch = _captcha(_Stub('{"code": "ZZ", "fails": 0}', fail_write=True))
    assert not await mismatch.verify_credential(credential)

    no_expiry = _captcha(_Stub('{"code": "ZZ"}', ttl_ms=-1))
    assert not await no_expiry.verify_credential(credential)


@pytest.mark.kiwi_id(2204)
async def test_policy_defaults() -> None:
    """场景策略取平台默认（本阶段不读配置）。"""
    captcha = _captcha(fakeredis.aioredis.FakeRedis(decode_responses=True))
    login = await captcha.policy("login")
    assert login.scene == "login"
    assert login.required is False
    assert login.fail_threshold == 3
    assert (await captcha.policy("ghost")).scene == "ghost"
    await captcha.aclose()


@pytest.mark.kiwi_id(2204)
def test_provider_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """提供者装配：默认配置解析 DefaultCaptcha、provider 空回落 NullCaptcha。"""
    registry = PluginRegistry()
    registry.register("captcha", "default", lambda: DefaultCaptcha(url="redis://localhost:6379/0"))
    registry.register("captcha", "null", lambda: NullCaptcha())
    monkeypatch.setattr(plugin_module, "_DEFAULT_REGISTRY", registry)

    real = get_captcha(_request(Settings(captcha=PluginSelection(provider="default"))))
    assert isinstance(real, DefaultCaptcha)
    assert real.key == "captcha"

    fallback = get_captcha(_request(Settings(captcha=PluginSelection(provider=""))))
    assert isinstance(fallback, NullCaptcha)


@pytest.mark.kiwi_id(2204)
async def test_lazy_client_and_aclose() -> None:
    """默认实现懒建客户端（不建连）与释放幂等。"""
    captcha = DefaultCaptcha(url="redis://localhost:6379/0")
    assert isinstance(captcha, BaseCaptcha)
    assert captcha.client is not None
    await captcha.aclose()
    await captcha.aclose()
