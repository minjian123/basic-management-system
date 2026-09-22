"""验证码渠道扩展基座契约测试（Kiwi 879）：三形态契约 / 常量与场景 / 数据契约 / 策略 / 脱敏 / 双入口 / 占位四端点。"""

from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from bms_core.api.base import API_PREFIX
from bms_core.api.deps import get_captcha
from bms_core.captcha.base import (
    CAPTCHA_FAIL_THRESHOLD,
    CAPTCHA_SCENE_POLICIES,
    CAPTCHA_SCENES,
    CAPTCHA_TTL,
    NULL_CAPTCHA_PAYLOAD,
    SLIDER_TOLERANCE,
    SMS_CAPTCHA_TTL,
    SMS_COOLDOWN,
    BaseCaptcha,
    CaptchaChallenge,
    CaptchaCredential,
    CaptchaKind,
    CaptchaScenePolicy,
    build_captcha_key,
    default_scene_policy,
    mask_phone,
)
from bms_core.captcha.null import NullCaptcha
from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.error_codes import ErrorCode
from bms_core.core.exceptions import (
    AuthError,
    BizError,
    CaptchaError,
    CaptchaExpiredError,
    CaptchaTooFrequentError,
    CaptchaVerifyError,
)
from bms_platform.api.captcha import router as captcha_router
from bms_platform.main import ApplicationFactory, lifespan


class _FailingCaptcha(BaseCaptcha):
    """测试替身：凭证校验恒定失败（覆盖强制校验抛错路径）。

    仅继承端口基类（未声明实现名）——不污染进程级插件注册表。
    """

    async def generate(self, scene: str = "login", *, kind: CaptchaKind = CaptchaKind.IMAGE) -> CaptchaChallenge:
        return CaptchaChallenge(captcha_id="fake", image=b"", kind=kind, scene=scene)

    async def send_sms(self, phone: str, scene: str = "login") -> CaptchaChallenge:
        return CaptchaChallenge(captcha_id="fake", image=b"", kind=CaptchaKind.SMS, scene=scene)

    async def verify_credential(self, credential: CaptchaCredential) -> bool:
        return False

    async def policy(self, scene: str) -> CaptchaScenePolicy:
        return CaptchaScenePolicy(scene=scene)


@pytest.mark.kiwi_id(879)
def test_contract_inheritance_and_identity() -> None:
    """契约继承链、能力域标识与占位标记（插件键未新增）。"""
    assert issubclass(BaseCaptcha, BaseCapability)
    assert issubclass(NullCaptcha, BaseCaptcha)
    assert issubclass(NullCaptcha, BaseNullObject)
    assert BaseCaptcha.key == "captcha"
    assert BaseCaptcha.plugin_key == "captcha"

    captcha = NullCaptcha()
    assert captcha.placeholder is True
    assert "captcha:null" in captcha.describe()
    assert "占位实现" in captcha.describe()


@pytest.mark.kiwi_id(879)
def test_constants_and_scenes() -> None:
    """常量与场景枚举（图形码既有常量与 key 拼接不变，场景补解绑 / 注册两项）。"""
    assert CAPTCHA_TTL == 300
    assert SMS_CAPTCHA_TTL == 300
    assert SMS_COOLDOWN == 60
    assert CAPTCHA_FAIL_THRESHOLD == 3
    assert SLIDER_TOLERANCE == 10
    assert NULL_CAPTCHA_PAYLOAD == "{}"
    assert CAPTCHA_SCENES == ("login", "reset_password", "bind", "unbind", "register")
    assert build_captcha_key("u1") == "bms:global:captcha:u1"


@pytest.mark.kiwi_id(879)
def test_challenge_and_credential_contracts() -> None:
    """数据契约与向后兼容：挑战既有位置参数可用、新增字段带默认值、值对象不可变。"""
    legacy = CaptchaChallenge("cid", b"")
    assert legacy.scene == "login"
    assert legacy.expires_in == CAPTCHA_TTL
    assert legacy.kind is CaptchaKind.IMAGE
    assert legacy.payload == ""
    assert legacy.target == ""
    assert legacy.cooldown == 0

    challenge = CaptchaChallenge(
        captcha_id="cid",
        image=b"png",
        expires_in=CAPTCHA_TTL,
        scene="login",
        kind=CaptchaKind.SLIDER,
        payload='{"width": 300}',
    )
    assert isinstance(challenge, BaseObject)
    with pytest.raises(FrozenInstanceError):
        challenge.kind = CaptchaKind.SMS  # pyright: ignore[reportAttributeAccessIssue]

    credential = CaptchaCredential(captcha_id="cid")
    assert credential.kind is CaptchaKind.IMAGE
    assert credential.code == ""
    assert credential.trace == ()
    assert credential.scene == "login"

    slider = CaptchaCredential(
        captcha_id="cid",
        kind=CaptchaKind.SLIDER,
        trace=((0, 0, 0), (60, 12, 120)),
        scene="login",
    )
    assert slider.trace == ((0, 0, 0), (60, 12, 120))

    policy = CaptchaScenePolicy(scene="login")
    assert (policy.required, policy.fail_threshold, policy.ttl, policy.cooldown) == (
        True,
        CAPTCHA_FAIL_THRESHOLD,
        CAPTCHA_TTL,
        SMS_COOLDOWN,
    )


@pytest.mark.kiwi_id(879)
def test_scene_policy_table_and_fallback() -> None:
    """平台默认策略表覆盖全量场景且顺序一致；未登记场景回落通用默认（不抛错）。"""
    assert tuple(policy.scene for policy in CAPTCHA_SCENE_POLICIES) == CAPTCHA_SCENES
    assert [policy.scene for policy in CAPTCHA_SCENE_POLICIES if not policy.required] == ["login"]
    for policy in CAPTCHA_SCENE_POLICIES:
        assert policy.fail_threshold == CAPTCHA_FAIL_THRESHOLD
        assert policy.ttl == CAPTCHA_TTL
        assert policy.cooldown == SMS_COOLDOWN

    assert default_scene_policy("login") is CAPTCHA_SCENE_POLICIES[0]

    fallback = default_scene_policy("ghost")
    assert fallback.scene == "ghost"
    assert fallback.required is True
    assert fallback.fail_threshold == CAPTCHA_FAIL_THRESHOLD


@pytest.mark.kiwi_id(879)
def test_mask_phone() -> None:
    """手机号脱敏（保留前 3 后 4；长度不足时保留前 3，不原样回显）。"""
    assert mask_phone("13812345678") == "138****5678"
    assert mask_phone("1234567") == "123****"
    assert mask_phone("") == "****"


@pytest.mark.kiwi_id(879)
async def test_placeholder_generate_three_kinds() -> None:
    """占位出题：三形态按挑战类型回带形态参数，短信取短信有效期与冷却。"""
    captcha = NullCaptcha()

    image = await captcha.generate("login")
    assert image.kind is CaptchaKind.IMAGE
    assert image.image == b""
    assert image.expires_in == CAPTCHA_TTL
    assert image.cooldown == 0
    assert image.payload == NULL_CAPTCHA_PAYLOAD
    assert image.target == ""

    slider = await captcha.generate("register", kind=CaptchaKind.SLIDER)
    assert (slider.kind, slider.scene) == (CaptchaKind.SLIDER, "register")
    assert slider.expires_in == CAPTCHA_TTL

    sms = await captcha.generate("bind", kind=CaptchaKind.SMS)
    assert sms.kind is CaptchaKind.SMS
    assert sms.expires_in == SMS_CAPTCHA_TTL
    assert sms.cooldown == SMS_COOLDOWN

    assert image.captcha_id != slider.captcha_id


@pytest.mark.kiwi_id(879)
async def test_placeholder_send_sms_and_policy() -> None:
    """占位短信发送：不真发、目标脱敏、取短信口径；场景策略取平台默认表。"""
    captcha = NullCaptcha()

    challenge = await captcha.send_sms("13812345678", "reset_password")
    assert challenge.kind is CaptchaKind.SMS
    assert challenge.target == "138****5678"
    assert challenge.cooldown == SMS_COOLDOWN
    assert challenge.expires_in == SMS_CAPTCHA_TTL
    assert challenge.scene == "reset_password"
    assert challenge.image == b""

    assert await captcha.policy("login") == CAPTCHA_SCENE_POLICIES[0]
    assert (await captcha.policy("ghost")).scene == "ghost"


@pytest.mark.kiwi_id(879)
async def test_verify_entrypoints_and_error_codes() -> None:
    """双入口校验：判定恒定通过、兼容入口委托；替身失败时强制入口抛验证码错误；错误码与 HTTP 状态就位。"""
    captcha = NullCaptcha()
    credential = CaptchaCredential(captcha_id="cid", code="0000")
    assert await captcha.verify_credential(credential) is True
    assert await captcha.verify("cid", "0000") is True
    assert await captcha.require_credential(credential) is None

    with pytest.raises(CaptchaVerifyError) as raised:
        await _FailingCaptcha().require_credential(credential)
    assert raised.value.code == int(ErrorCode.CAPTCHA_VERIFY_FAILED)
    assert raised.value.http_status == 200
    assert isinstance(raised.value, BizError)

    assert issubclass(CaptchaError, AuthError)
    assert issubclass(CaptchaVerifyError, CaptchaError)
    assert issubclass(CaptchaExpiredError, CaptchaError)
    assert issubclass(CaptchaTooFrequentError, CaptchaError)

    assert (
        int(ErrorCode.CAPTCHA_VERIFY_FAILED),
        int(ErrorCode.CAPTCHA_EXPIRED),
        int(ErrorCode.CAPTCHA_TOO_FREQUENT),
    ) == (
        20101,
        20102,
        20103,
    )
    assert CaptchaExpiredError().http_status == 404
    assert CaptchaTooFrequentError().http_status == 429


@pytest.mark.kiwi_id(879)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位验证码；路由经 `get_captcha` 取到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.captcha, NullCaptcha)

        @app.get("/captcha-probe")
        async def captcha_probe(captcha: Annotated[BaseCaptcha, Depends(get_captcha)]) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
            return {"key": captcha.key, "type": type(captcha).__name__}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/captcha-probe")

        assert resp.status_code == 200
        assert resp.json() == {"key": "captcha", "type": "NullCaptcha"}


@pytest.mark.kiwi_id(879)
async def test_placeholder_routes(client: AsyncClient) -> None:
    """占位四端点：出题（三形态）/ 短信发送（脱敏目标）/ 凭证校验 / 场景策略；四端点免登录。"""
    assert captcha_router.dependencies == []

    image = await client.post(f"{API_PREFIX}/captcha/challenges", json={"scene": "login"})
    assert image.status_code == 200
    data = image.json()["data"]
    assert data["kind"] == "image"
    assert data["image"] == ""
    assert data["payload"] == NULL_CAPTCHA_PAYLOAD
    assert data["expires_in"] == CAPTCHA_TTL
    assert data["cooldown"] == 0
    assert data["target"] == ""
    assert data["scene"] == "login"

    slider = await client.post(f"{API_PREFIX}/captcha/challenges", json={"scene": "register", "kind": "slider"})
    assert slider.json()["data"]["kind"] == "slider"

    sms = await client.post(f"{API_PREFIX}/captcha/sms", json={"phone": "13812345678", "scene": "bind"})
    assert sms.json()["data"]["target"] == "138****5678"
    assert sms.json()["data"]["cooldown"] == SMS_COOLDOWN
    assert sms.json()["data"]["expires_in"] == SMS_CAPTCHA_TTL

    verify = await client.post(
        f"{API_PREFIX}/captcha/verify",
        json={"captcha_id": "cid", "kind": "slider", "trace": [[0, 0, 0], [60, 12, 120]]},
    )
    assert verify.status_code == 200
    assert verify.json()["data"] == {"verified": True}

    policy = await client.get(f"{API_PREFIX}/captcha/scenes/register/policy")
    assert policy.json()["data"] == {
        "scene": "register",
        "required": True,
        "fail_threshold": CAPTCHA_FAIL_THRESHOLD,
        "ttl": CAPTCHA_TTL,
        "cooldown": SMS_COOLDOWN,
    }

    optional = await client.get(f"{API_PREFIX}/captcha/scenes/login/policy")
    assert optional.json()["data"]["required"] is False


@pytest.mark.kiwi_id(879)
async def test_route_invalid_scene_and_kind(client: AsyncClient) -> None:
    """异常分支：未登记场景 → 10001；非法挑战类型 → 10001。"""
    unknown = await client.get(f"{API_PREFIX}/captcha/scenes/ghost/policy")
    assert unknown.json()["code"] == int(ErrorCode.PARAM)

    bad_kind = await client.post(f"{API_PREFIX}/captcha/challenges", json={"scene": "login", "kind": "ghost"})
    assert bad_kind.json()["code"] == int(ErrorCode.PARAM)

    bad_scene = await client.post(f"{API_PREFIX}/captcha/sms", json={"phone": "13812345678", "scene": "ghost"})
    assert bad_scene.json()["code"] == int(ErrorCode.PARAM)

    bad_verify = await client.post(f"{API_PREFIX}/captcha/verify", json={"captcha_id": "", "scene": "login"})
    assert bad_verify.json()["code"] == int(ErrorCode.PARAM)
