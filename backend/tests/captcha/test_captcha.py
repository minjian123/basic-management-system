"""验证码基座契约测试（Kiwi 41）：继承 / key 与常量 / 挑战值对象 / 占位恒定通过 / 依赖解析。"""

from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_captcha
from app.captcha.base import CAPTCHA_SCENES, CAPTCHA_TTL, BaseCaptcha, CaptchaChallenge, build_captcha_key
from app.captcha.null import NullCaptcha
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.main import ApplicationFactory, lifespan


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
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位验证码；路由经 get_captcha 取到实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.captcha, NullCaptcha)

        @app.get("/captcha")
        async def captcha_info(captcha: Annotated[BaseCaptcha, Depends(get_captcha)]) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
            return {"key": captcha.key, "type": type(captcha).__name__}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/captcha")

        assert resp.status_code == 200
        assert resp.json() == {"key": "captcha", "type": "NullCaptcha"}
