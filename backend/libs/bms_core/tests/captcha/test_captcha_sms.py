"""短信验证码真实实现测试（Kiwi 2206）：生成 / 通知下发 / 一次性校验 / 冷却与限次 / 脱敏回显 /
fail-closed / 渠道不可用 / 选项 / 装配。"""

import json
from types import SimpleNamespace
from typing import Any, cast

import fakeredis.aioredis
import pytest
from fastapi import Request
from redis.asyncio import Redis

from bms_core.captcha.base import (
    CaptchaCredential,
    CaptchaKind,
    build_captcha_key,
    get_captcha,
)
from bms_core.captcha.default import (
    SMS_CAPTCHA_DIGITS,
    CaptchaSmsOptions,
    DefaultCaptcha,
)
from bms_core.captcha.null import NullCaptcha
from bms_core.core import plugin as plugin_module
from bms_core.core.assembly import DefaultCaptchaFactory
from bms_core.core.config import PluginSelection, Settings
from bms_core.core.context import current_client_ip
from bms_core.core.exceptions import (
    CaptchaExpiredError,
    CaptchaTooFrequentError,
    CaptchaVerifyError,
    ParamError,
    PluginError,
    ServiceUnavailableError,
)
from bms_core.core.plugin import PluginRegistry
from bms_core.notify.base import BaseNotifier, NotificationMessage, SendResult
from bms_core.ratelimit.memory import MemoryRateLimiter


class _RecordingNotifier(BaseNotifier):
    """测试替身：记录收到的通知消息，可配置送达结果或抛错。

    仅继承端口基类（未声明实现名）——不污染进程级插件注册表。
    """

    def __init__(self, *, delivered: bool = True, error: Exception | None = None) -> None:
        self.messages: list[NotificationMessage] = []
        self._delivered = delivered
        self._error = error

    async def send(self, message: NotificationMessage) -> SendResult:
        """记录消息并返回配置的送达结果（或抛配置的异常）。"""
        if self._error is not None:
            raise self._error
        self.messages.append(message)
        return SendResult(delivered=self._delivered, message_id="test-id")


def _captcha(
    client: object,
    *,
    notifier: BaseNotifier | None = None,
    rate_limiter: object | None = None,
    **options: object,
) -> DefaultCaptcha:
    """构造短信实现（注入测试客户端 / 通知器 / 限流器；选项经 `sms_` 前缀键）。

    Args:
        client: Redis 客户端替身。
        notifier: 通知器替身（缺省占位通知器）。
        rate_limiter: 限流器替身（缺省占位限流器恒定放行）。
        **options: 短信选项覆盖。

    Returns:
        DefaultCaptcha: 验证码实现。
    """
    sms = CaptchaSmsOptions.from_options(options) if options else None
    return DefaultCaptcha(
        url=None,
        client=cast("Redis", client),
        sms=sms,
        notifier=notifier,
        rate_limiter=cast("Any", rate_limiter),
    )


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


async def _keys(client: Redis) -> list[str]:
    """列出验证码 key（校验挑战是否被清理）。

    Args:
        client: Redis 客户端。

    Returns:
        list[str]: 验证码 key 列表。
    """
    return [str(key) for key in await client.keys(build_captcha_key("*"))]  # pyright: ignore[reportUnknownMemberType]


@pytest.fixture
def redis_client() -> fakeredis.aioredis.FakeRedis:
    """fakeredis 客户端（与真实 redis-py 同接口，decode_responses）。"""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.mark.kiwi_id(2206)
async def test_send_sms_challenge_record_and_notify(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """发送：挑战字段（脱敏目标 / 冷却 / 有效期 / 空 payload）、Redis 记录（6 位数字码）、通知消息。"""
    notifier = _RecordingNotifier()
    captcha = _captcha(redis_client, notifier=notifier)
    challenge = await captcha.send_sms("13812345678", "login")

    assert challenge.kind is CaptchaKind.SMS
    assert challenge.image == b""
    assert challenge.payload == ""
    assert challenge.target == "138****5678"
    assert challenge.cooldown == 60
    assert challenge.expires_in == 300
    assert challenge.scene == "login"
    assert "code" not in challenge.payload

    record = await _record(redis_client, challenge.captcha_id)
    assert record["kind"] == "sms"
    assert record["scene"] == "login"
    assert record["fails"] == 0
    code = str(record["code"])
    assert len(code) == 6
    assert all(char in SMS_CAPTCHA_DIGITS for char in code)

    assert len(notifier.messages) == 1
    message = notifier.messages[0]
    assert message.channel.value == "sms"
    assert message.recipient == "13812345678"
    assert code in message.content
    assert "5 分钟" in message.content
    assert message.title == ""
    assert message.biz_type == "captcha"
    assert message.biz_id == challenge.captcha_id
    await captcha.aclose()


@pytest.mark.kiwi_id(2206)
async def test_verify_sms_success_single_use(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """正确码校验通过且单次失效（二次使用 20102）。"""
    captcha = _captcha(redis_client, notifier=_RecordingNotifier())
    challenge = await captcha.send_sms("13812345678", "bind")
    code = str((await _record(redis_client, challenge.captcha_id))["code"])

    credential = CaptchaCredential(captcha_id=challenge.captcha_id, kind=CaptchaKind.SMS, code=code)
    assert await captcha.verify_credential(credential)
    assert not await captcha.verify_credential(credential)

    with pytest.raises(CaptchaExpiredError) as raised:
        await captcha.require_credential(credential)
    assert raised.value.code == 20102
    assert raised.value.http_status == 404
    await captcha.aclose()


@pytest.mark.kiwi_id(2206)
async def test_verify_sms_failure_counts_and_retry(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """错误码被拒（20101）、fails 递增且保留 TTL、可重试。"""
    captcha = _captcha(redis_client, notifier=_RecordingNotifier())
    challenge = await captcha.send_sms("13812345678", "reset_password")

    wrong = CaptchaCredential(captcha_id=challenge.captcha_id, kind=CaptchaKind.SMS, code="000000")
    with pytest.raises(CaptchaVerifyError) as raised:
        await captcha.require_credential(wrong)
    assert raised.value.code == 20101

    record = await _record(redis_client, challenge.captcha_id)
    assert record["fails"] == 1
    assert await redis_client.ttl(build_captcha_key(challenge.captcha_id)) > 0

    code = str(record["code"])
    correct = CaptchaCredential(captcha_id=challenge.captcha_id, kind=CaptchaKind.SMS, code=code)
    assert await captcha.verify_credential(correct)
    await captcha.aclose()


@pytest.mark.kiwi_id(2206)
async def test_sms_cooldown_does_not_reset(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """冷却期内重复发送被拒（20103/429），且不重置倒计时（reset_after 不回退）。"""
    captcha = _captcha(redis_client, notifier=_RecordingNotifier(), rate_limiter=MemoryRateLimiter())
    first = await captcha.send_sms("13812345678", "login")

    with pytest.raises(CaptchaTooFrequentError) as second:
        await captcha.send_sms("13812345678", "login")
    assert second.value.code == 20103
    assert second.value.http_status == 429
    second_reset = cast("int", cast("dict[str, object]", second.value.data)["reset_after"])

    with pytest.raises(CaptchaTooFrequentError) as third:
        await captcha.send_sms("13812345678", "login")
    third_reset = cast("int", cast("dict[str, object]", third.value.data)["reset_after"])
    assert third_reset <= second_reset

    record = await _record(redis_client, first.captcha_id)
    assert record["kind"] == "sms"
    await captcha.aclose()


@pytest.mark.kiwi_id(2206)
async def test_sms_account_limit(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """账号（手机号）维度超频被拒（不同场景绕过冷却但仍受账号上限约束）。"""
    captcha = _captcha(
        redis_client,
        notifier=_RecordingNotifier(),
        rate_limiter=MemoryRateLimiter(),
        sms_account_limit=2,
        sms_ip_limit=100,
    )
    await captcha.send_sms("13812345678", "login")
    await captcha.send_sms("13812345678", "bind")

    with pytest.raises(CaptchaTooFrequentError) as raised:
        await captcha.send_sms("13812345678", "register")
    assert raised.value.code == 20103
    await captcha.aclose()


@pytest.mark.kiwi_id(2206)
async def test_sms_ip_limit(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """来源 IP 维度超频被拒（IP 缺失时跳过该维，其余维度照常）。"""
    token = current_client_ip.set("9.9.9.9")
    try:
        captcha = _captcha(
            redis_client,
            notifier=_RecordingNotifier(),
            rate_limiter=MemoryRateLimiter(),
            sms_account_limit=100,
            sms_ip_limit=2,
        )
        await captcha.send_sms("13800000001", "login")
        await captcha.send_sms("13800000002", "bind")
        with pytest.raises(CaptchaTooFrequentError) as raised:
            await captcha.send_sms("13800000003", "register")
        assert raised.value.code == 20103
        await captcha.aclose()
    finally:
        current_client_ip.reset(token)


@pytest.mark.kiwi_id(2206)
async def test_sms_redis_unavailable_fail_closed() -> None:
    """Redis 不可用 fail-closed：写入挑战抛错 → 10007 / 503。"""

    class _Broken:
        """恒抛连接异常的客户端替身。"""

        async def set(self, *args: object, **kwargs: object) -> None:
            """恒定抛错。"""
            raise ConnectionError("redis down")

    captcha = _captcha(_Broken(), notifier=_RecordingNotifier())
    with pytest.raises(ServiceUnavailableError) as raised:
        await captcha.send_sms("13812345678", "login")
    assert raised.value.code == 10007
    assert raised.value.http_status == 503


@pytest.mark.kiwi_id(2206)
async def test_sms_channel_unavailable_discards_challenge(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """通知渠道不可用（未送达 / 抛异常）明确报错并删除已写入挑战（不静默放行）。"""
    captcha = _captcha(redis_client, notifier=_RecordingNotifier(delivered=False))
    with pytest.raises(ServiceUnavailableError) as raised:
        await captcha.send_sms("13812345678", "login")
    assert raised.value.code == 10007
    assert await _keys(redis_client) == []
    await captcha.aclose()

    captcha_error = _captcha(redis_client, notifier=_RecordingNotifier(error=RuntimeError("smtp down")))
    with pytest.raises(ServiceUnavailableError):
        await captcha_error.send_sms("13812345678", "login")
    assert await _keys(redis_client) == []
    await captcha_error.aclose()


@pytest.mark.kiwi_id(2206)
async def test_sms_channel_failure_cleanup_degraded() -> None:
    """发送失败时删除挑战降级（删除抛错仅日志，不影响报错）。"""

    class _StubStore:
        """`set` 成功、`delete` 抛错的客户端替身。"""

        async def set(self, *args: object, **kwargs: object) -> None:
            """空实现（写入成功）。"""

        async def delete(self, *args: object, **kwargs: object) -> None:
            """恒定抛错。"""
            raise ConnectionError("redis down")

    captcha = _captcha(_StubStore(), notifier=_RecordingNotifier(delivered=False))
    with pytest.raises(ServiceUnavailableError):
        await captcha.send_sms("13812345678", "login")


@pytest.mark.kiwi_id(2206)
async def test_generate_sms_rejected(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """短信形态经 `send_sms`，出题端点传 `kind=sms` 判参数错误（10001）。"""
    captcha = _captcha(redis_client)
    with pytest.raises(ParamError) as raised:
        await captcha.generate("login", kind=CaptchaKind.SMS)
    assert raised.value.code == 10001
    await captcha.aclose()


@pytest.mark.kiwi_id(2206)
async def test_generate_unknown_kind_rejected(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """非法形态（枚举外取值）防御分支也判参数错误（10001），不误入出图路径。"""
    captcha = _captcha(redis_client)
    with pytest.raises(ParamError):
        await captcha.generate("login", kind=cast("CaptchaKind", "ghost"))
    await captcha.aclose()


@pytest.mark.kiwi_id(2206)
def test_sms_options_parse_and_validate() -> None:
    """短信选项：缺省 / 覆盖生效；非整数 / 越界 → PluginError。"""
    default = CaptchaSmsOptions.from_options({})
    assert (default.code_length, default.account_limit, default.ip_limit, default.window) == (6, 5, 20, 3600)
    assert default == CaptchaSmsOptions.from_options(None)

    custom = CaptchaSmsOptions.from_options(
        {"sms_code_length": "8", "sms_account_limit": 3, "sms_ip_limit": 50, "sms_window": "600"}
    )
    assert (custom.code_length, custom.account_limit, custom.ip_limit, custom.window) == (8, 3, 50, 600)

    bad_options: tuple[dict[str, object], ...] = (
        {"sms_code_length": "abc"},
        {"sms_code_length": 3},
        {"sms_account_limit": 0},
        {"sms_ip_limit": -1},
        {"sms_window": 10},
        {"sms_window": True},
    )
    for bad in bad_options:
        with pytest.raises(PluginError):
            CaptchaSmsOptions.from_options(bad)


@pytest.mark.kiwi_id(2206)
def test_sms_factory_injects_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    """装配工厂：注入通知器 / 限流器 / 短信选项；默认配置解析 DefaultCaptcha；provider 空回落 NullCaptcha。"""
    factory = DefaultCaptchaFactory(
        Settings(
            captcha=PluginSelection(provider="default", options={"sms_code_length": "7"}),
            config_source=PluginSelection(provider=""),
        )
    )
    captcha = factory.create()
    assert isinstance(captcha, DefaultCaptcha)

    registry = PluginRegistry()
    registry.register("captcha", "default", lambda: DefaultCaptcha(url="redis://localhost:6379/0"))
    registry.register("captcha", "null", lambda: NullCaptcha())
    monkeypatch.setattr(plugin_module, "_DEFAULT_REGISTRY", registry)

    real = get_captcha(_request(Settings(captcha=PluginSelection(provider="default"))))
    assert isinstance(real, DefaultCaptcha)

    fallback = get_captcha(_request(Settings(captcha=PluginSelection(provider=""))))
    assert isinstance(fallback, NullCaptcha)


def _request(settings: Settings) -> Request:
    """构造最小请求替身（提供者只读 `app.state.settings`）。

    Args:
        settings: 应用配置。

    Returns:
        Request: 请求替身。
    """
    return cast("Request", SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings))))
