"""OIDC IdP 接入测试（Kiwi 2179）：OIDC 客户端 / JWKS 验签 / 部署件护栏 / 真实 IdP 集成。

本机以 `httpx.MockTransport` 造 Discovery / JWKS / token / userinfo，无需真实 IdP；
真机集成用例经 `IDP_TEST_*` 环境变量开启，未配置自动跳过（见任务测试记录）。
"""

import base64
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from joserfc import jwt
from joserfc.jwk import RSAKey

from bms_core.core.config import IdentityProviderSettings, Settings
from bms_core.core.exceptions import AuthError, ConfigError, PluginError, ServiceUnavailableError
from bms_core.idp.base import IdentityClaims
from bms_core.idp.oidc import OidcIdentityProvider, OidcIdentityProviderFactory

ISSUER = "http://idp.test/realms/bms"
CLIENT_ID = "bms-backend"
CLIENT_SECRET = "client-secret"
REDIRECT_URI = "http://app.test/api/v1/auth/callback"

_BACKEND_ROOT = Path(__file__).resolve().parents[4]
_REALM_FILE = _BACKEND_ROOT.parent / "deploy" / "keycloak" / "bms-realm.json"

type Handler = Callable[[httpx.Request], httpx.Response]


def _metadata(issuer: str = ISSUER, *, drop: str | None = None) -> dict[str, str]:
    """构造 OIDC Discovery 文档。

    Args:
        issuer: 签发方。
        drop: 需删除的字段（验证缺字段分支）。

    Returns:
        dict[str, str]: Discovery 文档。
    """
    doc = {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/protocol/openid-connect/auth",
        "token_endpoint": f"{issuer}/protocol/openid-connect/token",
        "userinfo_endpoint": f"{issuer}/protocol/openid-connect/userinfo",
        "jwks_uri": f"{issuer}/protocol/openid-connect/certs",
    }
    if drop is not None:
        doc.pop(drop, None)
    return doc


def _key_pair() -> tuple[RSAKey, dict[str, object]]:
    """生成 RSA 密钥与对应公钥 JWK（kid=k1）。

    Returns:
        tuple[RSAKey, dict[str, object]]: 私钥与公钥 JWK。
    """
    key = RSAKey.generate_key(2048, private=True)
    public = cast("dict[str, object]", key.as_dict(private=False))
    public["kid"] = "k1"
    return key, public


def _token(
    key: RSAKey,
    *,
    kid: str = "k1",
    alg: str = "RS256",
    iss: str = ISSUER,
    aud: object = CLIENT_ID,
    exp_delta: int = 300,
    subject: str = "user-1",
) -> str:
    """签发测试 JWT。

    Args:
        key: 签名私钥。
        kid: 密钥标识（写入 header）。
        alg: 签名算法。
        iss: 签发方。
        aud: 受众。
        exp_delta: 过期时间偏移（秒；负数为已过期）。
        subject: 主体标识。

    Returns:
        str: JWT 紧凑串。
    """
    now = int(time.time())
    return jwt.encode(
        {"alg": alg, "kid": kid},
        {
            "iss": iss,
            "sub": subject,
            "aud": aud,
            "exp": now + exp_delta,
            "iat": now,
            "preferred_username": "alice",
            "email": "alice@example.com",
        },
        key,
    )


def _compact(header: Mapping[str, object], payload: Mapping[str, object]) -> str:
    """手工拼装紧凑 JWT（用于构造非白名单算法的票据）。

    Args:
        header: JOSE 头。
        payload: 声明载荷。

    Returns:
        str: 紧凑 JWT 串。
    """

    def encode(part: Mapping[str, object]) -> str:
        raw = json.dumps(part, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{encode(header)}.{encode(payload)}.{encode({'sig': 1})}"


def _handler(
    *,
    public: Mapping[str, object],
    id_token: str | None = None,
    jwks_calls: list[int] | None = None,
    drop: str | None = None,
    public_supplier: Callable[[], Mapping[str, object]] | None = None,
) -> Handler:
    """构造 MockTransport 处理器（路由 Discovery / JWKS / token / userinfo）。

    Args:
        public: JWKS 公钥。
        id_token: 换码响应中的 ID Token。
        jwks_calls: 记录 JWKS 调用次数的容器。
        drop: Discovery 缺字段（验证失败分支）。
        public_supplier: 动态 JWKS 供应（密钥轮换场景）。

    Returns:
        Handler: 请求处理器。
    """

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json=_metadata(drop=drop))
        if path.endswith("/certs"):
            if jwks_calls is not None:
                jwks_calls.append(1)
            keys = public_supplier() if public_supplier is not None else public
            return httpx.Response(200, json={"keys": [keys]})
        if path.endswith("/token"):
            return httpx.Response(
                200,
                json={
                    "access_token": "access-token",
                    "token_type": "Bearer",
                    "expires_in": 300,
                    "id_token": id_token,
                    "refresh_token": "refresh-token",
                },
            )
        if path.endswith("/userinfo"):
            return httpx.Response(200, json={"sub": "user-1", "preferred_username": "alice", "email": "a@x.test"})
        return httpx.Response(404)

    return handle


def _provider(handler: Handler) -> OidcIdentityProvider:
    """用 MockTransport 构造 OIDC 客户端。

    Args:
        handler: 请求处理器。

    Returns:
        OidcIdentityProvider: 客户端实例。
    """
    return OidcIdentityProvider(
        issuer=ISSUER,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.kiwi_id(2179)
async def test_authorize_builds_authorization_url() -> None:
    """授权入口 URL 含授权码流程必填参数。"""
    _, public = _key_pair()
    provider = _provider(_handler(public=public))
    url = await provider.authorize("state-1")
    assert url.startswith(f"{ISSUER}/protocol/openid-connect/auth?")
    query = parse_qs(urlparse(url).query)
    assert query["response_type"] == ["code"]
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == [REDIRECT_URI]
    assert query["scope"] == ["openid profile email"]
    assert query["state"] == ["state-1"]


@pytest.mark.kiwi_id(2179)
async def test_exchange_token_and_userinfo_mapping() -> None:
    """换码映射令牌（含 id_token / refresh_token）；userinfo 映射身份（idp_key=issuer）。"""
    key, public = _key_pair()
    provider = _provider(_handler(public=public, id_token=_token(key)))
    token = await provider.exchange_token("code-1")
    assert token.access_token == "access-token"
    assert token.token_type == "Bearer"
    assert token.expires_in == 300
    assert token.refresh_token == "refresh-token"
    assert token.id_token == _token(key)

    user = await provider.userinfo("access-token")
    assert user.subject == "user-1"
    assert user.username == "alice"
    assert user.email == "a@x.test"
    assert user.idp_key == ISSUER


@pytest.mark.kiwi_id(2179)
async def test_verify_token_success() -> None:
    """票据经 JWKS 验签通过并回读声明（idp_key 取 issuer）。"""
    key, public = _key_pair()
    provider = _provider(_handler(public=public))
    claims = await provider.verify_token(_token(key), audience=CLIENT_ID)
    assert isinstance(claims, IdentityClaims)
    assert claims.subject == "user-1"
    assert claims.issuer == ISSUER
    assert claims.idp_key == ISSUER
    assert claims.audience == (CLIENT_ID,)
    assert claims.expires_at > 0
    assert claims.payload["preferred_username"] == "alice"


@pytest.mark.kiwi_id(2179)
async def test_verify_token_rejects_bad_tokens() -> None:
    """签名 / 过期 / iss / aud 不符均抛认证错误；算法白名单拒绝对称算法。"""
    key, public = _key_pair()
    provider = _provider(_handler(public=public))

    with pytest.raises(AuthError):
        await provider.verify_token(_token(key)[:-3] + "abc", audience=CLIENT_ID)
    with pytest.raises(AuthError):
        await provider.verify_token(_token(key, exp_delta=-3600), audience=CLIENT_ID)
    with pytest.raises(AuthError):
        await provider.verify_token(_token(key, iss="http://evil.test/realms/bms"), audience=CLIENT_ID)
    with pytest.raises(AuthError):
        await provider.verify_token(_token(key, aud="other"), audience=CLIENT_ID)

    hs_token = _compact({"alg": "HS256", "typ": "JWT"}, {"iss": ISSUER, "sub": "u", "exp": int(time.time()) + 300})
    with pytest.raises(AuthError):
        await provider.verify_token(hs_token)


@pytest.mark.kiwi_id(2179)
async def test_verify_token_refreshes_jwks_on_kid_miss() -> None:
    """首次 JWKS 无匹配 kid 时强制刷新一次再验签（容忍密钥轮换）。"""
    key, public = _key_pair()
    rotated = dict(public)
    rotated["kid"] = "k2"
    calls: list[int] = []
    state = {"served": 0}

    def supplier() -> Mapping[str, object]:
        state["served"] += 1
        return rotated if state["served"] == 1 else public

    provider = _provider(_handler(public=public, jwks_calls=calls, public_supplier=supplier))
    claims = await provider.verify_token(_token(key), audience=CLIENT_ID)
    assert claims.subject == "user-1"
    assert len(calls) == 2


@pytest.mark.kiwi_id(2179)
async def test_idp_unreachable_and_missing_endpoint() -> None:
    """IdP 不可达抛服务不可用；Discovery 缺字段抛配置错误。"""

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    _, public = _key_pair()
    down = _provider(unreachable)
    with pytest.raises(ServiceUnavailableError):
        await down.authorize("s")

    missing = _provider(_handler(public=public, drop="authorization_endpoint"))
    with pytest.raises(ConfigError):
        await missing.authorize("s")


@pytest.mark.kiwi_id(2179)
async def test_verify_token_list_audience() -> None:
    """`aud` 为数组时归一化为元组并按给定受众命中。"""
    key, public = _key_pair()
    provider = _provider(_handler(public=public))
    token = _token(key, aud=["api", "bms-backend"])
    claims = await provider.verify_token(token, audience="bms-backend")
    assert claims.audience == ("api", "bms-backend")


@pytest.mark.kiwi_id(2179)
async def test_verify_token_without_iat() -> None:
    """缺失 `iat` / `aud` 时声明归一化（时间取 0、受众取空），不整体失败。"""
    key, public = _key_pair()
    provider = _provider(_handler(public=public))
    token = jwt.encode(
        {"alg": "RS256", "kid": "k1"},
        {"iss": ISSUER, "sub": "user-1", "exp": int(time.time()) + 300},
        key,
    )
    claims = await provider.verify_token(token)
    assert claims.issued_at == 0
    assert claims.audience == ()


@pytest.mark.kiwi_id(2179)
async def test_jwks_error_branches() -> None:
    """JWKS 验签端点异常分支：不可达 / 非对象 / 非法内容均按契约抛错。"""
    key, _ = _key_pair()
    token = _token(key)

    def unreachable(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json=_metadata())
        raise httpx.ConnectError("jwks down", request=request)

    with pytest.raises(ServiceUnavailableError):
        await _provider(unreachable).verify_token(token)

    def not_object(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json=_metadata())
        return httpx.Response(200, json=["not", "an", "object"])

    with pytest.raises(AuthError):
        await _provider(not_object).verify_token(token)

    def malformed(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json=_metadata())
        return httpx.Response(200, json={"keys": [{"kty": "bogus"}]})

    with pytest.raises(AuthError):
        await _provider(malformed).verify_token(token)


@pytest.mark.kiwi_id(2179)
async def test_token_endpoint_non_object_response() -> None:
    """令牌端点响应非对象时抛配置错误。"""
    key, _ = _key_pair()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json=_metadata())
        return httpx.Response(200, json=["unexpected"])

    provider = _provider(handler)
    with pytest.raises(ConfigError):
        await provider.exchange_token("code-1")
    assert key


@pytest.mark.kiwi_id(2179)
def test_identity_provider_settings_and_factory() -> None:
    """`[identity_provider]` 默认值；工厂配置不全拒启、配置齐产出 OIDC 客户端。"""
    defaults = IdentityProviderSettings()
    assert defaults.provider == ""
    assert defaults.client_id == "bms-backend"
    assert defaults.client_secret == ""
    assert defaults.scopes == ["openid", "profile", "email"]

    incomplete = Settings(identity_provider=IdentityProviderSettings(provider="oidc", issuer=ISSUER))
    with pytest.raises(PluginError):
        OidcIdentityProviderFactory(incomplete).create(None)

    complete = Settings(
        identity_provider=IdentityProviderSettings(
            provider="oidc",
            issuer=ISSUER,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
        )
    )
    provider = OidcIdentityProviderFactory(complete).create(None)
    assert isinstance(provider, OidcIdentityProvider)
    assert provider.key == "identity_provider"


@pytest.mark.kiwi_id(2179)
def test_oidc_provider_resolves_in_app() -> None:
    """provider=oidc 且配置齐时应用可启动、依赖解析到 OidcIdentityProvider（独立进程装配）。"""
    env = dict(os.environ)
    env.update(
        {
            "BMS_IDENTITY_PROVIDER__PROVIDER": "oidc",
            "BMS_IDENTITY_PROVIDER__ISSUER": ISSUER,
            "BMS_IDENTITY_PROVIDER__CLIENT_ID": CLIENT_ID,
            "BMS_IDENTITY_PROVIDER__CLIENT_SECRET": CLIENT_SECRET,
        }
    )
    code = (
        "import asyncio\n"
        "from bms_core.idp.oidc import OidcIdentityProvider\n"
        "from bms_identity.main import ApplicationFactory\n"
        "async def main() -> None:\n"
        "    app = ApplicationFactory().create(None)\n"
        "    async with app.router.lifespan_context(app):\n"
        "        assert isinstance(app.state.identity_provider, OidcIdentityProvider)\n"
        "asyncio.run(main())\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.kiwi_id(2179)
def test_realm_deployment_has_no_plaintext_secret() -> None:
    """部署件护栏：realm JSON 可解析、客户端字段正确、secret 为环境变量占位（无明文）。"""
    realm = json.loads(_REALM_FILE.read_text(encoding="utf-8"))
    assert realm["realm"] == "bms"
    assert realm["enabled"] is True
    client = next(item for item in realm["clients"] if item["clientId"] == "bms-backend")
    assert client["secret"] == "${KEYCLOAK_CLIENT_SECRET}"
    assert client["publicClient"] is False
    assert client["standardFlowEnabled"] is True
    assert client["serviceAccountsEnabled"] is True
    assert isinstance(client["redirectUris"], list) and client["redirectUris"]


@pytest.mark.integration
@pytest.mark.kiwi_id(2179)
async def test_real_keycloak_jwks_verification() -> None:
    """真机集成：经 client_credentials 取令牌并经 JWKS 验签通过（未配置环境时跳过）。"""
    issuer = os.environ.get("IDP_TEST_ISSUER")
    client_id = os.environ.get("IDP_TEST_CLIENT_ID")
    client_secret = os.environ.get("IDP_TEST_CLIENT_SECRET")
    if not (issuer and client_id and client_secret):
        pytest.skip("未配置真实 Keycloak 环境（IDP_TEST_ISSUER / IDP_TEST_CLIENT_ID / IDP_TEST_CLIENT_SECRET）")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{issuer}/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        response.raise_for_status()
        access_token = response.json()["access_token"]

    provider = OidcIdentityProvider(
        issuer=issuer,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri="http://localhost/api/v1/auth/callback",
    )
    claims = await provider.verify_token(access_token)
    assert claims.issuer == issuer
    assert claims.idp_key == issuer
    assert claims.subject
