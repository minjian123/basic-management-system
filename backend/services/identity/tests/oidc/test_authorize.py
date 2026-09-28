"""OIDC 授权端点测试（Kiwi 2202）。"""

import pytest
from httpx import ASGITransport, AsyncClient

from bms_core.idp.state.base import build_idp_state_key

from .conftest import OidcHarness
from .helpers import CLIENT_ID, REDIRECT_URI, TENANT, TENANT_HEADERS, pkce

_AUTHORIZE = "/api/v1/oidc/authorize"


def _params(**overrides: str) -> dict[str, str]:
    """构造授权请求参数（缺省合规）。

    Args:
        **overrides: 覆盖字段。

    Returns:
        dict[str, str]: 查询参数。
    """
    params: dict[str, str] = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "openid",
        "state": "st-1",
        "nonce": "n-1",
    }
    params.update(overrides)
    return params


@pytest.mark.kiwi_id(2202)
async def test_authorize_success_stores_code(client: AsyncClient, oidc: OidcHarness) -> None:
    """授权成功：授权码落 `oidccode` 命名空间，302 回跳含 code / state。"""
    await oidc.seed_client()
    _, challenge = pkce()
    response = await client.get(
        _AUTHORIZE,
        params=_params(code_challenge=challenge, code_challenge_method="S256"),
        headers=TENANT_HEADERS,
    )
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith(REDIRECT_URI)
    assert "state=st-1" in location
    code = location.split("code=", 1)[1].split("&", 1)[0]
    entry = oidc.states._items[build_idp_state_key(code, tenant_code=TENANT, namespace="oidccode")]  # pyright: ignore[reportPrivateUsage]
    payload = entry[0]
    assert payload["client_id"] == CLIENT_ID
    assert payload["redirect_uri"] == REDIRECT_URI
    assert payload["subject"] == "1001"
    assert payload["tenant_code"] == TENANT
    assert payload["nonce"] == "n-1"


@pytest.mark.kiwi_id(2202)
async def test_authorize_unauthenticated_401(oidc: OidcHarness) -> None:
    """未登录且未配登录页：401（不跳转）。"""
    await oidc.seed_client()
    async with AsyncClient(transport=ASGITransport(app=oidc.app), base_url="http://test") as anon:
        response = await anon.get(_AUTHORIZE, params=_params(), headers=TENANT_HEADERS)
    assert response.status_code == 401
    assert response.json()["error"] == "access_denied"


@pytest.mark.kiwi_id(2202)
async def test_authorize_unauthenticated_login_redirect(oidc: OidcHarness) -> None:
    """未登录且配置登录页：302 到 login_url（附 return_to）。"""
    await oidc.seed_client()
    oidc.app.state.settings.oidc_provider.login_url = "http://frontend.test/login"
    try:
        async with AsyncClient(transport=ASGITransport(app=oidc.app), base_url="http://test") as anon:
            response = await anon.get(_AUTHORIZE, params=_params(), headers=TENANT_HEADERS)
    finally:
        oidc.app.state.settings.oidc_provider.login_url = ""
    assert response.status_code == 302
    assert response.headers["location"].startswith("http://frontend.test/login?return_to=")


@pytest.mark.kiwi_id(2202)
async def test_authorize_unknown_client_no_redirect(client: AsyncClient, oidc: OidcHarness) -> None:
    """未知客户端：400 标准错误（不回跳）。"""
    response = await client.get(_AUTHORIZE, params=_params(client_id="ghost"), headers=TENANT_HEADERS)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


@pytest.mark.kiwi_id(2202)
async def test_authorize_unregistered_redirect_uri(client: AsyncClient, oidc: OidcHarness) -> None:
    """未注册 redirect_uri：400 标准错误（不回跳，防开放重定向）。"""
    await oidc.seed_client()
    response = await client.get(_AUTHORIZE, params=_params(redirect_uri="http://evil.test/cb"), headers=TENANT_HEADERS)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


@pytest.mark.kiwi_id(2202)
async def test_authorize_invalid_scope_redirects_error(client: AsyncClient, oidc: OidcHarness) -> None:
    """scope 缺 openid：302 回跳带 error=invalid_scope。"""
    await oidc.seed_client()
    response = await client.get(_AUTHORIZE, params=_params(scope="profile"), headers=TENANT_HEADERS)
    assert response.status_code == 302
    assert "error=invalid_scope" in response.headers["location"]


@pytest.mark.kiwi_id(2202)
async def test_authorize_public_client_requires_pkce(client: AsyncClient, oidc: OidcHarness) -> None:
    """公共客户端缺 PKCE：302 回跳带 error=invalid_request。"""
    await oidc.seed_client(public=True)
    response = await client.get(_AUTHORIZE, params=_params(), headers=TENANT_HEADERS)
    assert response.status_code == 302
    assert "error=invalid_request" in response.headers["location"]


@pytest.mark.kiwi_id(2202)
async def test_authorize_disabled_client(client: AsyncClient, oidc: OidcHarness) -> None:
    """停用客户端：400 标准错误。"""
    await oidc.seed_client(status="disabled")
    response = await client.get(_AUTHORIZE, params=_params(), headers=TENANT_HEADERS)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


@pytest.mark.kiwi_id(2202)
async def test_authorize_missing_params(client: AsyncClient, oidc: OidcHarness) -> None:
    """缺必需参数：400 标准错误。"""
    await oidc.seed_client()
    response = await client.get(_AUTHORIZE, headers=TENANT_HEADERS)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


@pytest.mark.kiwi_id(2202)
async def test_authorize_tenant_mismatch(client: AsyncClient, oidc: OidcHarness) -> None:
    """`tenant` 参数与登录态不一致：400 标准错误。"""
    await oidc.seed_client()
    response = await client.get(_AUTHORIZE, params={**_params(), "tenant": "other"}, headers=TENANT_HEADERS)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


@pytest.mark.kiwi_id(2202)
async def test_authorize_response_type_and_grant(client: AsyncClient, oidc: OidcHarness) -> None:
    """response_type 非 code / 客户端未授权授权码：302 回跳 error。"""
    await oidc.seed_client()
    wrong_type = await client.get(_AUTHORIZE, params=_params(response_type="token"), headers=TENANT_HEADERS)
    assert wrong_type.status_code == 302
    assert "error=unsupported_response_type" in wrong_type.headers["location"]

    await oidc.seed_client(client_id="cc-only", grant_types=["client_credentials"], redirect_uris=[REDIRECT_URI])
    not_granted = await client.get(_AUTHORIZE, params=_params(client_id="cc-only"), headers=TENANT_HEADERS)
    assert not_granted.status_code == 302
    assert "error=unauthorized_client" in not_granted.headers["location"]


@pytest.mark.kiwi_id(2202)
async def test_authorize_pkce_method_must_be_s256(client: AsyncClient, oidc: OidcHarness) -> None:
    """PKCE 方法非 S256：302 回跳 error=invalid_request。"""
    await oidc.seed_client()
    _, challenge = pkce()
    response = await client.get(
        _AUTHORIZE,
        params=_params(code_challenge=challenge, code_challenge_method="plain"),
        headers=TENANT_HEADERS,
    )
    assert response.status_code == 302
    assert "error=invalid_request" in response.headers["location"]
