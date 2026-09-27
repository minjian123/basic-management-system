"""验证码场景策略按租户读取用例（Kiwi 2208，03_04）。

覆盖：`DefaultCaptcha.policy` 读 `sys_config`（覆盖生效 / 缺省回落）/ 渠道降级顺序（短信未配 → 图形码兜底）/
非法值回落 / `send_sms` 自动取按租户冷却与有效期。
"""

from collections.abc import Mapping, Sequence
from typing import cast

import pytest

from bms_core.captcha import default as captcha_default
from bms_core.captcha.base import CAPTCHA_FAIL_THRESHOLD, CAPTCHA_TTL, SMS_COOLDOWN, CaptchaKind
from bms_core.captcha.default import DefaultCaptcha
from bms_core.config.base import BaseConfigSource
from bms_core.config.null import NullConfigSource


class _MappingSource(BaseConfigSource):
    """内存取数替身（返回预置键值子集）。"""

    def __init__(self, values: Mapping[str, object] | None = None) -> None:
        self._values = dict(values or {})

    async def get_many(self, keys: Sequence[str]) -> Mapping[str, str]:
        """返回预置映射的子集。

        Args:
            keys: 参数键序列。

        Returns:
            Mapping[str, str]: 命中键 → 值。
        """
        return {key: cast("str", self._values[key]) for key in keys if key in self._values}


def _captcha(config: BaseConfigSource | None = None) -> DefaultCaptcha:
    """构造验证码实现（不连 Redis；仅测策略）。

    Args:
        config: 参数取数实现（缺省 Null）。

    Returns:
        DefaultCaptcha: 验证码实例。
    """
    return DefaultCaptcha(url=None, config=config)


@pytest.mark.kiwi_id(2208)
async def test_policy_defaults_when_no_config() -> None:
    """无配置（Null）时回落平台默认表。"""
    policy = await _captcha().policy("login")
    assert policy.scene == "login"
    assert policy.required is False
    assert policy.fail_threshold == CAPTCHA_FAIL_THRESHOLD
    assert policy.ttl == CAPTCHA_TTL
    assert policy.cooldown == SMS_COOLDOWN
    assert policy.channels == (CaptchaKind.SLIDER, CaptchaKind.IMAGE)


@pytest.mark.kiwi_id(2208)
async def test_policy_reads_tenant_overrides() -> None:
    """按租户配置覆盖策略字段（覆盖生效）。"""
    source = _MappingSource(
        {
            "captcha.scene.login.required": "true",
            "captcha.scene.login.fail_threshold": "5",
            "captcha.scene.login.ttl": "120",
            "captcha.scene.login.cooldown": "30",
        }
    )
    policy = await _captcha(source).policy("login")
    assert policy.required is True
    assert policy.fail_threshold == 5
    assert policy.ttl == 120
    assert policy.cooldown == 30


@pytest.mark.kiwi_id(2208)
async def test_policy_invalid_values_fall_back() -> None:
    """非法配置值回落默认（不抛错）。"""
    source = _MappingSource(
        {
            "captcha.scene.login.required": "maybe",
            "captcha.scene.login.fail_threshold": "abc",
            "captcha.scene.login.ttl": "0",
        }
    )
    policy = await _captcha(source).policy("login")
    assert policy.required is False
    assert policy.fail_threshold == CAPTCHA_FAIL_THRESHOLD
    assert policy.ttl == CAPTCHA_TTL


@pytest.mark.kiwi_id(2208)
async def test_policy_channels_degradation() -> None:
    """渠道降级：短信开关决定是否出现；图形码恒兜底；短信未配 → 滑块/图形码。"""
    # 短信默认关闭：注册场景仅滑块 + 图形码
    closed = await _captcha().policy("register")
    assert closed.channels == (CaptchaKind.SLIDER, CaptchaKind.IMAGE)

    # 短信开启：注册场景按 sms → slider → image 顺序
    enabled = await _captcha(_MappingSource({"captcha.channel.sms": "true"})).policy("register")
    assert enabled.channels == (CaptchaKind.SMS, CaptchaKind.SLIDER, CaptchaKind.IMAGE)

    # 登录场景不含短信（场景顺序固定 slider → image）
    login = await _captcha(_MappingSource({"captcha.channel.sms": "true"})).policy("login")
    assert login.channels == (CaptchaKind.SLIDER, CaptchaKind.IMAGE)

    # 滑块关闭：图形码兜底仍在
    image_only = await _captcha(_MappingSource({"captcha.channel.slider": "false"})).policy("login")
    assert image_only.channels == (CaptchaKind.IMAGE,)


@pytest.mark.kiwi_id(2208)
async def test_policy_unknown_scene_fallback() -> None:
    """未登记场景回落默认策略（含默认渠道）。"""
    policy = await _captcha().policy("ghost")
    assert policy.scene == "ghost"
    assert policy.required is True
    assert policy.channels == (CaptchaKind.SLIDER, CaptchaKind.IMAGE)


@pytest.mark.kiwi_id(2208)
async def test_policy_bool_value_and_image_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """布尔配置值直通；渠道顺序缺图形码时补兜底。"""
    bool_source = _MappingSource({"captcha.scene.login.required": True})
    assert (await _captcha(bool_source).policy("login")).required is True

    monkeypatch.setitem(captcha_default.CAPTCHA_SCENE_CHANNELS, "ghost", (CaptchaKind.SLIDER,))
    channels = captcha_default._resolve_channels("ghost", {})  # pyright: ignore[reportPrivateUsage]
    assert channels == (CaptchaKind.SLIDER, CaptchaKind.IMAGE)


@pytest.mark.kiwi_id(2208)
async def test_null_source_returns_empty() -> None:
    """Null 取数恒空，确保策略走默认。"""
    assert await NullConfigSource().get_many(("captcha.scene.login.required",)) == {}
