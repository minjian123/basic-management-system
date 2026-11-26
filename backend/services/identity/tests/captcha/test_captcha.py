"""验证码基座契约（Kiwi 41）：继承 / key 与常量 / 挑战值对象 / 占位恒定通过 / 依赖解析。

重写口径（13_11）：依赖解析读装配态应用，不再自建壳、不往应用挂探针路由。
"""

from dataclasses import FrozenInstanceError

import pytest
from fastapi import FastAPI

from bms_core.captcha.base import CAPTCHA_SCENES, CAPTCHA_TTL, BaseCaptcha, CaptchaChallenge, build_captcha_key
from bms_core.captcha.null import NullCaptcha
from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseCapability, BaseNullObject


@pytest.mark.kiwi_id(41)
def test_inheritance_and_key() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseCaptcha, BaseCapability)
    assert issubclass(NullCaptcha, BaseCaptcha)
    assert issubclass(NullCaptcha, BaseNullObject)
    assert BaseCaptcha.key == "captcha"

    captcha = NullCaptcha()
    assert captcha.placeholder is True
    assert "占位实现" in captcha.describe()


@pytest.mark.kiwi_id(41)
def test_key_ttl_and_scenes() -> None:
    """验证码 key 拼接、TTL 与场景常量就位。"""
    assert build_captcha_key("u1") == "bms:global:captcha:u1"
    assert CAPTCHA_TTL == 300
    assert CAPTCHA_SCENES == ("login", "reset_password", "bind", "unbind", "register")


@pytest.mark.kiwi_id(41)
async def test_challenge_value_object() -> None:
    """generate 返回挑战值对象：编号非空、图片空字节、有效期与场景就位、值对象不可变。"""
    challenge = await NullCaptcha().generate("login")
    assert isinstance(challenge, CaptchaChallenge)
    assert challenge.captcha_id
    assert challenge.image == b""
    assert challenge.expires_in == CAPTCHA_TTL
    assert challenge.scene == "login"

    bind = await NullCaptcha().generate("bind")
    assert bind.scene == "bind"
    assert bind.captcha_id != challenge.captcha_id

    with pytest.raises(FrozenInstanceError):
        challenge.scene = "bind"  # pyright: ignore[reportAttributeAccessIssue]


@pytest.mark.kiwi_id(41)
async def test_null_captcha_always_passes() -> None:
    """占位实现恒定通过（不连 Redis、不校验编号与验证码）。"""
    captcha = NullCaptcha()
    assert await captcha.verify("any-id", "0000") is True
    assert await captcha.verify(build_captcha_key("x"), "") is True


@pytest.mark.kiwi_id(41)
async def test_dependency_provider_resolves(service_app: FastAPI) -> None:
    """依赖解析：装配态验证码是占位实现，且装配器记录的提供者与本应用一致。

    插件实例按应用隔离（13_11）：不比跨应用实例同一性。
    """
    captcha = service_app.state.captcha
    assert isinstance(captcha, NullCaptcha)
    assert service_app.state.plugin_providers["captcha"] in {"null", "default"}
