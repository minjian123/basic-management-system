"""双类 JWT · 统一校验内核测试（Kiwi 2180）：按 aud 分流 / aud 隔离 / api 经 IdP / 失败语义。

用户 JWT 经 `httpx.MockTransport` 造 Discovery / JWKS 校验（无须真实 IdP）；真机集成用例见任务测试记录。
"""

import time
from collections.abc import Callable

import httpx
import pytest
from joserfc import jwt
from joserfc.jwk import RSAKey

from bms_core.core.exceptions import AuthError, ParamError, ServiceUnavailableError
from bms_core.idp.null import NullIdentityProvider
from bms_core.idp.oidc import OidcIdentityProvider
from bms_core.oauth.jwt import JwtServiceTokenIssuer
from bms_core.oauth.keys import TokenKey
from bms_core.oauth.null import NullTokenVerifier
from bms_core.oauth.token import (
    TOKEN_AUDIENCE_API,
    TOKEN_AUDIENCE_SERVICE,
    BaseServiceTokenIssuer,
    ServiceTokenSpec,
)
from bms_core.oauth.verify import BaseTokenVerifier, UnifiedTokenVerifier

ISSUER = "http://idp.test/realms/bms"
CLIENT_ID = "bms-backend"


def _service_issuer(kid: str = "k1") -> JwtServiceTokenIssuer:
    """构造本地服务 JWT 签发者（RSA）。

    Args:
        kid: 密钥标识。

    Returns:
        JwtServiceTokenIssuer: 本地签发者。
    """
    key = RSAKey.generate_key(2048, private=True)
    return JwtServiceTokenIssuer(
        issuer="bms",
        keys=[
            TokenKey(
                kid=kid,
                algorithm="RS256",
                public_key=key.as_pem(private=False).decode(),
                private_key=key.as_pem(private=True).decode(),
            )
        ],
        active_kid=kid,
    )


def _idp_material() -> tuple[RSAKey, dict[str, object]]:
    """生成 IdP 侧密钥与公钥 JWK。

    Returns:
        tuple[RSAKey, dict[str, object]]: 私钥与公钥 JWK（kid=k1）。
    """
    key = RSAKey.generate_key(2048, private=True)
    public: dict[str, object] = dict(key.as_dict(private=False))
    public["kid"] = "k1"
    return key, public


def _idp(handler: Callable[[httpx.Request], httpx.Response]) -> OidcIdentityProvider:
    """用 MockTransport 构造 OIDC 客户端。

    Args:
        handler: 请求处理器。

    Returns:
        OidcIdentityProvider: 客户端。
    """
    return OidcIdentityProvider(
        issuer=ISSUER,
        client_id=CLIENT_ID,
        client_secret="secret",
        redirect_uri="http://app.test/callback",
        transport=httpx.MockTransport(handler),
    )


def _user_token(key: RSAKey, *, aud: str = "api", exp_delta: int = 300) -> str:
    """签发用户 JWT（IdP 侧密钥）。

    Args:
        key: 私钥。
        aud: 受众。
        exp_delta: 过期偏移（秒）。

    Returns:
        str: 紧凑 JWT。
    """
    now = int(time.time())
    return jwt.encode(
        {"alg": "RS256", "kid": "k1"},
        {"iss": ISSUER, "sub": "user-1", "aud": aud, "exp": now + exp_delta, "iat": now, "scope": "profile"},
        key,
    )


def _handler(
    public: dict[str, object] | None = None,
    *,
    unreachable: bool = False,
    drop_jwks: bool = False,
) -> Callable[[httpx.Request], httpx.Response]:
    """构造 IdP MockTransport 处理器（仅校验路径用 Discovery / JWKS）。

    Args:
        public: JWKS 公钥。
        unreachable: 全部请求抛连接错误。
        drop_jwks: Discovery 缺 `jwks_uri`。

    Returns:
        Callable: 请求处理器。
    """

    def handle(request: httpx.Request) -> httpx.Response:
        if unreachable:
            raise httpx.ConnectError("down", request=request)
        if request.url.path.endswith("/.well-known/openid-configuration"):
            doc = {"issuer": ISSUER, "jwks_uri": f"{ISSUER}/protocol/openid-connect/certs"}
            if drop_jwks:
                doc.pop("jwks_uri")
            return httpx.Response(200, json=doc)
        if request.url.path.endswith("/certs"):
            return httpx.Response(200, json={"keys": [public]})
        return httpx.Response(404)

    return handle


@pytest.mark.kiwi_id(2180)
def test_verifier_contract() -> None:
    """契约继承链与能力键。"""
    assert BaseTokenVerifier.key == BaseTokenVerifier.plugin_key == "token_verifier"
    assert issubclass(UnifiedTokenVerifier, BaseTokenVerifier)
    assert issubclass(NullTokenVerifier, BaseTokenVerifier)


@pytest.mark.kiwi_id(2180)
async def test_verify_service_token_locally() -> None:
    """服务受众：经本地 JWKS 校验并回填归一声明。"""
    issuer = _service_issuer()
    verifier = UnifiedTokenVerifier(service_issuer=issuer, identity_provider=NullIdentityProvider())
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


@pytest.mark.kiwi_id(2180)
async def test_verify_user_token_via_idp() -> None:
    """用户受众：经 IdP（MockTransport）校验并回填声明。"""
    key, public = _idp_material()
    verifier = UnifiedTokenVerifier(service_issuer=_service_issuer(), identity_provider=_idp(_handler(public)))
    verified = await verifier.verify(_user_token(key), audience=TOKEN_AUDIENCE_API)
    assert verified.subject == "user-1"
    assert verified.issuer == ISSUER
    assert verified.audience == (TOKEN_AUDIENCE_API,)
    assert verified.scopes == ("profile",)
    assert verified.service == ""


@pytest.mark.kiwi_id(2180)
async def test_audience_isolation() -> None:
    """aud 隔离：用户 token 以 service 期望被拒、服务 token 以 api 期望被拒。"""
    idp_key, public = _idp_material()
    issuer = _service_issuer()
    verifier = UnifiedTokenVerifier(service_issuer=issuer, identity_provider=_idp(_handler(public)))

    with pytest.raises(AuthError):
        await verifier.verify(_user_token(idp_key), audience=TOKEN_AUDIENCE_SERVICE)

    service_token = (await issuer.issue(ServiceTokenSpec(service="platform"))).access_token
    with pytest.raises(AuthError):
        await verifier.verify(service_token, audience=TOKEN_AUDIENCE_API)


@pytest.mark.kiwi_id(2180)
async def test_unknown_audience_rejected() -> None:
    """未登记受众抛参数错误。"""
    verifier = UnifiedTokenVerifier(service_issuer=_service_issuer(), identity_provider=NullIdentityProvider())
    with pytest.raises(ParamError):
        await verifier.verify("token", audience="open")


@pytest.mark.kiwi_id(2180)
async def test_expired_and_wrong_issuer_rejected() -> None:
    """过期 / issuer 不符均抛认证错误（两类）。"""
    idp_key, public = _idp_material()
    issuer = _service_issuer()
    verifier = UnifiedTokenVerifier(service_issuer=issuer, identity_provider=_idp(_handler(public)))

    with pytest.raises(AuthError):
        await verifier.verify(_user_token(idp_key, exp_delta=-3600), audience=TOKEN_AUDIENCE_API)
    with pytest.raises(AuthError):
        await verifier.verify(_user_token(idp_key, aud="other"), audience=TOKEN_AUDIENCE_API)

    expired_service = (await issuer.issue(ServiceTokenSpec(service="platform", ttl=-3600))).access_token
    with pytest.raises(AuthError):
        await verifier.verify(expired_service, audience=TOKEN_AUDIENCE_SERVICE)


@pytest.mark.kiwi_id(2180)
async def test_idp_unreachable_raises_service_unavailable() -> None:
    """IdP 不可达抛服务不可用（10007）。"""
    verifier = UnifiedTokenVerifier(
        service_issuer=_service_issuer(),
        identity_provider=_idp(_handler(unreachable=True)),
    )
    with pytest.raises(ServiceUnavailableError):
        await verifier.verify("any", audience=TOKEN_AUDIENCE_API)


@pytest.mark.kiwi_id(2180)
async def test_null_verifier_placeholder() -> None:
    """占位校验器恒定返回占位声明。"""
    verified = await NullTokenVerifier().verify("any", audience=TOKEN_AUDIENCE_API)
    assert verified.subject == "null-subject"
    assert verified.audience == (TOKEN_AUDIENCE_API,)


@pytest.mark.kiwi_id(2180)
def test_verifier_resolves_in_app() -> None:
    """装配：默认配置下应用解析到 `UnifiedTokenVerifier`，本地签发者为 `JwtServiceTokenIssuer`。"""
    import asyncio

    from bms_core.application import service_lifespan
    from bms_core.oauth.jwt import JwtServiceTokenIssuer as _Issuer
    from bms_identity.main import ApplicationFactory

    async def _run() -> None:
        app = ApplicationFactory().create(None)
        async with service_lifespan(app):
            assert isinstance(app.state.token_verifier, UnifiedTokenVerifier)
            assert isinstance(app.state.service_token, _Issuer)
            assert isinstance(app.state.service_token, BaseServiceTokenIssuer)

    asyncio.run(_run())
