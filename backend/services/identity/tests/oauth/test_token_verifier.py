"""双类 JWT · 统一校验内核测试（Kiwi 2180 / 2193）：按 aud 分流 / aud 隔离 / api 本地用户令牌 / 失败语义。

用户令牌由 BMS 自签（本机 joserfc 生成密钥对）；校验源切换后的端到端证据（本地令牌经网关）见任务测试记录。
"""

import pytest
from joserfc.jwk import RSAKey

from bms_core.core.exceptions import AuthError, ParamError
from bms_core.oauth.jwt import JwtServiceTokenIssuer
from bms_core.oauth.keys import TokenKey
from bms_core.oauth.null import NullTokenVerifier
from bms_core.oauth.token import (
    TOKEN_AUDIENCE_API,
    TOKEN_AUDIENCE_SERVICE,
    BaseServiceTokenIssuer,
    ServiceTokenSpec,
)
from bms_core.oauth.user_jwt import JwtUserTokenIssuer
from bms_core.oauth.user_token import USER_TOKEN_TYPE_ACCESS, BaseUserTokenIssuer, UserTokenSpec
from bms_core.oauth.verify import BaseTokenVerifier, UnifiedTokenVerifier


def _service_issuer() -> JwtServiceTokenIssuer:
    """构造本地服务 JWT 签发者（RSA）。

    Returns:
        JwtServiceTokenIssuer: 本地签发者。
    """
    key = RSAKey.generate_key(2048, private=True)
    return JwtServiceTokenIssuer(
        issuer="bms",
        keys=[
            TokenKey(
                kid="svc-k1",
                algorithm="RS256",
                public_key=key.as_pem(private=False).decode(),
                private_key=key.as_pem(private=True).decode(),
            )
        ],
        active_kid="svc-k1",
    )


def _user_issuer(*, issuer: str = "bms", access_ttl: int = 1800) -> JwtUserTokenIssuer:
    """构造本地用户令牌签发者（RSA）。

    Args:
        issuer: 签发方。
        access_ttl: access 有效期（秒；负数用于过期分支）。

    Returns:
        JwtUserTokenIssuer: 本地签发者。
    """
    key = RSAKey.generate_key(2048, private=True)
    return JwtUserTokenIssuer(
        issuer=issuer,
        keys=[
            TokenKey(
                kid="usr-k1",
                algorithm="RS256",
                public_key=key.as_pem(private=False).decode(),
                private_key=key.as_pem(private=True).decode(),
            )
        ],
        active_kid="usr-k1",
        access_ttl=access_ttl,
        refresh_ttl=1209600,
    )


def _verifier(
    *, service: JwtServiceTokenIssuer | None = None, user: JwtUserTokenIssuer | None = None
) -> UnifiedTokenVerifier:
    """构造统一校验器（缺省注入本地服务 / 用户签发者）。

    Args:
        service: 服务 JWT 签发者。
        user: 用户令牌签发者。

    Returns:
        UnifiedTokenVerifier: 统一校验器。
    """
    return UnifiedTokenVerifier(
        service_issuer=service if service is not None else _service_issuer(),
        user_token_issuer=user if user is not None else _user_issuer(),
    )


@pytest.mark.kiwi_id(2180)
def test_verifier_contract() -> None:
    """契约继承链与能力键。"""
    assert BaseTokenVerifier.key == BaseTokenVerifier.plugin_key == "token_verifier"
    assert issubclass(UnifiedTokenVerifier, BaseTokenVerifier)
    assert issubclass(NullTokenVerifier, BaseTokenVerifier)
    assert BaseUserTokenIssuer.key == BaseUserTokenIssuer.plugin_key == "user_token"


@pytest.mark.kiwi_id(2180)
async def test_verify_service_token_locally() -> None:
    """服务受众：经本地 JWKS 校验并回填归一声明。"""
    issuer = _service_issuer()
    verifier = _verifier(service=issuer)
    token = (
        await issuer.issue(ServiceTokenSpec(service="platform", scopes=("user:read",), tenant="acme"))
    ).access_token
    verified = await verifier.verify(token, audience=TOKEN_AUDIENCE_SERVICE)
    assert verified.subject == "platform"
    assert verified.service == "platform"
    assert verified.tenant == "acme"
    assert verified.scopes == ("user:read",)
    assert verified.token_type == "service"
    assert verified.issuer == "bms"
    assert verified.audience == (TOKEN_AUDIENCE_SERVICE,)
    assert verified.token_id
    assert verified.expires_at > verified.issued_at


@pytest.mark.kiwi_id(2193)
async def test_verify_user_token_locally() -> None:
    """用户受众：经本地用户令牌 JWKS 校验并回填声明（校验源已由 IdP 切至 BMS 自签）。"""
    user = _user_issuer()
    verifier = _verifier(user=user)
    pair = await user.issue_pair(
        UserTokenSpec(subject="1001", session_id="sess-1", tenant_id="acme", scopes=("profile",))
    )
    verified = await verifier.verify(pair.access_token, audience=TOKEN_AUDIENCE_API)
    assert verified.subject == "1001"
    assert verified.token_type == USER_TOKEN_TYPE_ACCESS
    assert verified.tenant == "acme"
    assert verified.scopes == ("profile",)
    assert verified.service == ""
    assert verified.issuer == "bms"
    assert verified.audience == (TOKEN_AUDIENCE_API,)
    assert verified.token_id == "sess-1"


@pytest.mark.kiwi_id(2193)
async def test_user_refresh_rejected_as_access() -> None:
    """用户 refresh 不得当 access 用（网关链路只接受 `type=access`）。"""
    user = _user_issuer()
    verifier = _verifier(user=user)
    pair = await user.issue_pair(UserTokenSpec(subject="1001", session_id="sess-1"))
    with pytest.raises(AuthError):
        await verifier.verify(pair.refresh_token, audience=TOKEN_AUDIENCE_API)


@pytest.mark.kiwi_id(2193)
async def test_audience_isolation() -> None:
    """aud 隔离双向：用户 token 以 service 期望被拒、服务 token 以 api 期望被拒。"""
    service = _service_issuer()
    user = _user_issuer()
    verifier = _verifier(service=service, user=user)

    pair = await user.issue_pair(UserTokenSpec(subject="1001", session_id="sess-1"))
    with pytest.raises(AuthError):
        await verifier.verify(pair.access_token, audience=TOKEN_AUDIENCE_SERVICE)

    service_token = (await service.issue(ServiceTokenSpec(service="platform"))).access_token
    with pytest.raises(AuthError):
        await verifier.verify(service_token, audience=TOKEN_AUDIENCE_API)


@pytest.mark.kiwi_id(2180)
async def test_unknown_audience_rejected() -> None:
    """未登记受众抛参数错误。"""
    verifier = _verifier()
    with pytest.raises(ParamError):
        await verifier.verify("token", audience="open")


@pytest.mark.kiwi_id(2193)
async def test_expired_and_wrong_issuer_rejected() -> None:
    """过期 / 签发方不符均抛认证错误。"""
    service = _service_issuer()
    verifier = _verifier(service=service, user=_user_issuer())
    expired_user = _user_issuer(access_ttl=-3600)
    with pytest.raises(AuthError):
        await verifier.verify(
            (await expired_user.issue_pair(UserTokenSpec(subject="1001", session_id="sess-1"))).access_token,
            audience=TOKEN_AUDIENCE_API,
        )

    other_issuer = _user_issuer(issuer="other")
    with pytest.raises(AuthError):
        await verifier.verify(
            (await other_issuer.issue_pair(UserTokenSpec(subject="1001", session_id="sess-1"))).access_token,
            audience=TOKEN_AUDIENCE_API,
        )

    expired_service = (await service.issue(ServiceTokenSpec(service="platform", ttl=-3600))).access_token
    with pytest.raises(AuthError):
        await verifier.verify(expired_service, audience=TOKEN_AUDIENCE_SERVICE)


@pytest.mark.kiwi_id(2180)
async def test_null_verifier_placeholder() -> None:
    """占位校验器恒定返回占位声明。"""
    verified = await NullTokenVerifier().verify("any", audience=TOKEN_AUDIENCE_API)
    assert verified.subject == "null-subject"
    assert verified.audience == (TOKEN_AUDIENCE_API,)


@pytest.mark.kiwi_id(2193)
def test_verifier_resolves_in_app() -> None:
    """装配：默认配置下应用解析统一校验器 + 本地服务 / 用户签发者（不依赖 IdP 配置）。"""
    import asyncio

    from bms_core.application import service_lifespan
    from bms_identity.main import ApplicationFactory

    async def _run() -> None:
        app = ApplicationFactory().create(None)
        async with service_lifespan(app):
            assert isinstance(app.state.token_verifier, UnifiedTokenVerifier)
            assert isinstance(app.state.service_token, BaseServiceTokenIssuer)
            assert isinstance(app.state.user_token, JwtUserTokenIssuer)
            assert isinstance(app.state.user_token, BaseUserTokenIssuer)

    asyncio.run(_run())
