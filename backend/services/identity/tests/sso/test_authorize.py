"""SSO 授权跳转端点测试（Kiwi 2197）：state / nonce / PKCE 生成与失败分支。"""

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient

from .conftest import REDIRECT_URI, SsoHarness
from .helpers import CLIENT_ID, IDP_KEY, ISSUER, TENANT_HEADERS, TENANT_ID

AUTHORIZE = f"/api/v1/auth/sso/{IDP_KEY}/authorize"


def _challenge(verifier: str) -> str:
    """按 S256 计算 PKCE 挑战。

    Args:
        verifier: 校验串。

    Returns:
        str: BASE64URL(SHA256(verifier))（去填充）。
    """
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


@pytest.mark.kiwi_id(2197)
async def test_authorize_redirects_with_state_nonce_pkce(client: AsyncClient, sso: SsoHarness) -> None:
    """授权跳转：302 到 IdP + state / nonce / S256 PKCE 与流程载荷落存。"""
    await sso.seed_provider()
    state, location, payload = await sso.start_flow(client)

    assert location.startswith(f"{ISSUER}/protocol/openid-connect/auth")
    query = parse_qs(urlparse(location).query)
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == [REDIRECT_URI]
    assert query["response_type"] == ["code"]
    assert query["state"] == [state]
    assert query["code_challenge_method"] == ["S256"]
    assert query["nonce"] == [payload["nonce"]]
    verifier = str(payload["code_verifier"])
    assert len(verifier) > 0 and query["code_challenge"] == [_challenge(verifier)]
    assert payload["tenant_code"] == "demo"
    assert payload["tenant_id"] == TENANT_ID
    assert payload["idp_key"] == IDP_KEY
    assert payload["redirect_uri"] == REDIRECT_URI


@pytest.mark.kiwi_id(2197)
async def test_authorize_derives_redirect_uri_and_disables_pkce(client: AsyncClient, sso: SsoHarness) -> None:
    """配置派生：行配置缺 redirect_uri 时按回调基址派生；pkce=false 不带挑战。"""
    sso.app.state.settings.sso.callback_base_url = "http://cb.test"
    sso.app.state.settings.sso.pkce = False
    await sso.seed_provider(config=sso.provider_config(redirect_uri=None))

    state, location, payload = await sso.start_flow(client)
    query = parse_qs(urlparse(location).query)
    derived = f"http://cb.test/api/v1/auth/sso/{IDP_KEY}/callback"
    assert query["redirect_uri"] == [derived]
    assert payload["redirect_uri"] == derived
    assert "code_challenge" not in query and "code_challenge_method" not in query
    assert payload["code_verifier"] == ""
    assert state  # 流程状态仍落存


@pytest.mark.kiwi_id(2197)
async def test_authorize_provider_errors(client: AsyncClient, sso: SsoHarness) -> None:
    """失败分支：未知 / 停用身份源 20051；密钥引用缺失 20053；发现不可达 20053 且回滚状态。"""
    unknown = await client.get("/api/v1/auth/sso/nope/authorize", headers=TENANT_HEADERS)
    assert unknown.status_code == 404 and unknown.json()["code"] == 20051

    await sso.seed_provider(status="disabled")
    disabled = await client.get(AUTHORIZE, headers=TENANT_HEADERS)
    assert disabled.status_code == 404 and disabled.json()["code"] == 20051

    await sso.set_provider_status("enabled")
    await sso.seed_provider(
        idp_key="broken",
        config=sso.provider_config(client_secret_ref="env:SSO_TEST_MISSING_SECRET"),
    )
    broken = await client.get("/api/v1/auth/sso/broken/authorize", headers=TENANT_HEADERS)
    assert broken.status_code == 503 and broken.json()["code"] == 20053

    sso.idp.discovery_status = 500
    unavailable = await client.get(AUTHORIZE, headers=TENANT_HEADERS)
    assert unavailable.status_code == 503 and unavailable.json()["code"] == 20053
    assert sso.states._items == {}  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2197)
async def test_authorize_rate_limited_by_provider_dimension(client: AsyncClient, sso: SsoHarness) -> None:
    """限流：provider 维度阈值 1 时第二次请求 429（10005）。"""
    sso.app.state.settings.sso.provider_rate_limit = 1
    await sso.seed_provider()
    first = await client.get(AUTHORIZE, headers=TENANT_HEADERS)
    assert first.status_code == 302
    second = await client.get(AUTHORIZE, headers=TENANT_HEADERS)
    assert second.status_code == 429 and second.json()["code"] == 10005
