"""图形验证码真实实现 · 真 Redis 集成用例（integration 标记；需 BMS_TEST_REDIS_URL，未配置则跳过）。"""

import json
import os
from collections.abc import AsyncIterator
from typing import cast

import pytest
from redis.asyncio import Redis

from bms_core.captcha.base import CaptchaCredential, CaptchaKind, build_captcha_key
from bms_core.captcha.default import DefaultCaptcha
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import CaptchaTooFrequentError
from bms_core.ratelimit.base import build_rate_limit_key
from bms_core.ratelimit.redis import RedisRateLimiter

pytestmark = pytest.mark.integration


@pytest.fixture
async def captcha() -> AsyncIterator[DefaultCaptcha]:
    """真 Redis 图形码实现（未配置 `BMS_TEST_REDIS_URL` 时跳过）。"""
    url = os.environ.get("BMS_TEST_REDIS_URL")
    if not url:
        pytest.skip("未配置 BMS_TEST_REDIS_URL，跳过真实 Redis 集成用例")
    instance = DefaultCaptcha(url=url)
    try:
        yield instance
    finally:
        await instance.aclose()


async def _code_of(client: Redis, captcha_id: str) -> str:
    """读取挑战记录中的校验码。

    Args:
        client: Redis 客户端。
        captcha_id: 挑战编号。

    Returns:
        str: 校验码。
    """
    raw = await client.get(build_captcha_key(captcha_id))
    assert raw is not None
    return cast("str", json.loads(raw)["code"])


@pytest.mark.kiwi_id(2204)
async def test_image_roundtrip_against_real_redis(captcha: DefaultCaptcha) -> None:
    """真 Redis：出题 → 正确码通过 → 单次失效被拒；失败回写并计数。"""
    challenge = await captcha.generate("login")
    code = await _code_of(captcha.client, challenge.captcha_id)
    assert len(code) == 4

    credential = CaptchaCredential(captcha_id=challenge.captcha_id, kind=CaptchaKind.IMAGE, code=code.lower())
    assert await captcha.verify_credential(credential)
    assert not await captcha.verify_credential(credential)

    second = await captcha.generate("login")
    assert not await captcha.verify_credential(
        CaptchaCredential(captcha_id=second.captcha_id, kind=CaptchaKind.IMAGE, code="0000")
    )
    raw = await captcha.client.get(build_captcha_key(second.captcha_id))
    assert raw is not None
    assert cast("dict[str, object]", json.loads(raw))["fails"] == 1

    await captcha.client.delete(build_captcha_key(second.captcha_id))  # pyright: ignore[reportUnknownMemberType]


@pytest.mark.kiwi_id(2205)
async def test_slider_roundtrip_against_real_redis(captcha: DefaultCaptcha) -> None:
    """真 Redis：滑块出题 → 正确轨迹通过 → 单次失效被拒；错位失败计数。"""
    challenge = await captcha.generate("login", kind=CaptchaKind.SLIDER)
    assert challenge.image == b""
    record = await _record_of(captcha.client, challenge.captcha_id)
    assert record["kind"] == "slider"

    correct = ((0, 0, 0), (cast("int", record["gap_x"]), 0, 300))
    credential = CaptchaCredential(captcha_id=challenge.captcha_id, kind=CaptchaKind.SLIDER, trace=correct)
    assert await captcha.verify_credential(credential)
    assert not await captcha.verify_credential(credential)

    second = await captcha.generate("login", kind=CaptchaKind.SLIDER)
    wrong = ((0, 0, 0), (cast("int", record["gap_x"]) + 100, 0, 300))
    assert not await captcha.verify_credential(
        CaptchaCredential(captcha_id=second.captcha_id, kind=CaptchaKind.SLIDER, trace=wrong)
    )
    assert (await _record_of(captcha.client, second.captcha_id))["fails"] == 1

    await captcha.client.delete(build_captcha_key(second.captcha_id))  # pyright: ignore[reportUnknownMemberType]


@pytest.mark.kiwi_id(2206)
async def test_sms_roundtrip_against_real_redis() -> None:
    """真 Redis：短信发送 → 正确码通过 → 单次失效被拒；真限流下二次发送冷却命中 20103。"""
    url = os.environ.get("BMS_TEST_REDIS_URL")
    if not url:
        pytest.skip("未配置 BMS_TEST_REDIS_URL，跳过真实 Redis 集成用例")
    phone = "13899990000"
    cooldown_key = build_rate_limit_key(dimension="sms-cooldown", target=f"{phone}:login")
    account_key = build_rate_limit_key(dimension="sms-account", target=phone)
    captcha = DefaultCaptcha(url=url, rate_limiter=RedisRateLimiter(url=url))
    try:
        await captcha.client.delete(cooldown_key, account_key)  # pyright: ignore[reportUnknownMemberType]
        challenge = await captcha.send_sms(phone, "login")
        assert challenge.kind is CaptchaKind.SMS
        assert challenge.target == "138****0000"
        assert challenge.cooldown == 60

        code = await _code_of(captcha.client, challenge.captcha_id)
        credential = CaptchaCredential(captcha_id=challenge.captcha_id, kind=CaptchaKind.SMS, code=code)
        assert await captcha.verify_credential(credential)
        assert not await captcha.verify_credential(credential)

        with pytest.raises(CaptchaTooFrequentError) as raised:
            await captcha.send_sms(phone, "login")
        assert raised.value.code == 20103
    finally:
        await captcha.client.delete(cooldown_key, account_key)  # pyright: ignore[reportUnknownMemberType]
        await captcha.aclose()


async def _record_of(client: Redis, captcha_id: str) -> ConcurrentStableDict[str, object]:
    """读取挑战记录（真 Redis）。

    Args:
        client: Redis 客户端。
        captcha_id: 挑战编号。

    Returns:
        ConcurrentStableDict[str, object]: 挑战记录。
    """
    raw = await client.get(build_captcha_key(captcha_id))
    assert raw is not None
    return ConcurrentStableDict(cast("dict[str, object]", json.loads(raw)))
