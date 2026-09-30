"""钉钉身份源测试（Kiwi 2201）：新版 OAuth2 授权 / 换用户令牌 / 用户信息解析 / 安全与失败分支 / 工厂。

以 `httpx.MockTransport` 模拟钉钉 `userAccessToken` 与 `contact/users/me` 响应（成功 / 授权失败 / 5xx / 非 JSON），
无需真实钉钉；真实企业凭据联调归阶段十七（见任务详细设计「边界与开放项」）。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import IdentityProviderSettings, Settings
from bms_core.core.exceptions import DingtalkAuthError, DingtalkUnavailableError, PluginError
from bms_core.idp.dingtalk import DingtalkIdentityProvider, DingtalkIdentityProviderFactory

type Handler = Callable[[httpx.Request], httpx.Response]

CLIENT_ID = "client-1"
CLIENT_SECRET = "secret-1"
REDIRECT_URI = "https://app.test/api/v1/auth/sso/dingtalk/callback"
DEFAULT_LOGIN_URL = "https://login.dingtalk.com/oauth2/auth"


class _DingtalkMock:
    """可控钉钉服务：`userAccessToken` / `contact/users/me` 两接口。"""

    def __init__(self) -> None:
        """初始化（默认成功响应）。"""
        self.token_body: object = {"accessToken": "at-1", "expireIn": 7200, "refreshToken": "rt-1"}
        self.token_status = 200
        self.token_raw: bytes | None = None
        self.user_body: object = {"unionId": "union-1", "openId": "open-1", "nick": "Alice", "email": "a@x"}
        self.user_status = 200
        self.user_raw: bytes | None = None
        self.token_forms: ConcurrentStableList[str] = ConcurrentStableList()
        self.token_headers: ConcurrentStableList[str | None] = ConcurrentStableList()

    def handle(self, request: httpx.Request) -> httpx.Response:
        """MockTransport 处理函数（按路径分派）。

        Args:
            request: 出站请求。

        Returns:
            httpx.Response: 模拟响应。
        """
        if request.url.path.endswith("/v1.0/oauth2/userAccessToken"):
            self.token_forms.add(request.content.decode())
            if self.token_raw is not None:
                return httpx.Response(self.token_status, content=self.token_raw)
            return httpx.Response(self.token_status, json=self.token_body)
        if request.url.path.endswith("/v1.0/contact/users/me"):
            self.token_headers.add(request.headers.get("x-acs-dingtalk-access-token"))
            if self.user_raw is not None:
                return httpx.Response(self.user_status, content=self.user_raw)
            return httpx.Response(self.user_status, json=self.user_body)
        return httpx.Response(404, json={})


def _provider(mock: _DingtalkMock, **kwargs: object) -> DingtalkIdentityProvider:
    """构造注入 MockTransport 的钉钉客户端。

    Args:
        mock: 可控服务。
        **kwargs: 覆盖构造参数。

    Returns:
        DingtalkIdentityProvider: 钉钉客户端实例。
    """
    return DingtalkIdentityProvider(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        transport=httpx.MockTransport(mock.handle),
        **kwargs,  # pyright: ignore[reportArgumentType]
    )


@pytest.mark.kiwi_id(2201)
async def test_authorize_builds_oauth_url() -> None:
    """授权跳转：新版 OAuth2 入口含 client_id / scope / prompt / 回调 / state；入口可配。"""
    parsed = urlparse(await _provider(_DingtalkMock()).authorize("state-1"))
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == DEFAULT_LOGIN_URL
    query = parse_qs(parsed.query)
    assert query["client_id"] == [CLIENT_ID]
    assert query["scope"] == ["openid"]
    assert query["prompt"] == ["consent"]
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == [REDIRECT_URI]
    assert query["state"] == ["state-1"]

    custom = _provider(_DingtalkMock(), login_url="https://login.test/auth", scope="openid corpid", prompt="none")
    assert (await custom.authorize("s")).startswith("https://login.test/auth?")


@pytest.mark.kiwi_id(2201)
async def test_exchange_token_success() -> None:
    """换令牌：请求体携带客户端凭据与授权码；响应字段透出（缺失 refreshToken 为 None）。"""
    mock = _DingtalkMock()
    token = await _provider(mock).exchange_token("auth-code")
    assert token.access_token == "at-1"
    assert token.token_type == "Bearer"
    assert token.expires_in == 7200
    assert token.refresh_token == "rt-1"
    form = json.loads(mock.token_forms[0])
    assert form == {
        "clientId": CLIENT_ID,
        "clientSecret": CLIENT_SECRET,
        "code": "auth-code",
        "grantType": "authorization_code",
    }

    mock2 = _DingtalkMock()
    mock2.token_body = {"accessToken": "at-2"}
    token2 = await _provider(mock2).exchange_token("auth-code")
    assert token2.expires_in == 0
    assert token2.refresh_token is None


@pytest.mark.kiwi_id(2201)
async def test_exchange_token_auth_and_unavailable() -> None:
    """换令牌失败：4xx / 未返回令牌 → 授权失败；5xx / 非 JSON / 非对象 / 网络 → 不可达。"""
    rejected = _DingtalkMock()
    rejected.token_status = 400
    with pytest.raises(DingtalkAuthError):
        await _provider(rejected).exchange_token("bad")

    no_token = _DingtalkMock()
    no_token.token_body = {}
    with pytest.raises(DingtalkAuthError):
        await _provider(no_token).exchange_token("bad")

    server_error = _DingtalkMock()
    server_error.token_status = 503
    with pytest.raises(DingtalkUnavailableError):
        await _provider(server_error).exchange_token("bad")

    not_json = _DingtalkMock()
    not_json.token_raw = b"not-json"
    with pytest.raises(DingtalkUnavailableError):
        await _provider(not_json).exchange_token("bad")

    not_object = _DingtalkMock()
    not_object.token_raw = b"[1]"
    with pytest.raises(DingtalkUnavailableError):
        await _provider(not_object).exchange_token("bad")

    def boom(request: httpx.Request) -> httpx.Response:
        del request
        raise httpx.ConnectError("down")

    provider = DingtalkIdentityProvider(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        transport=httpx.MockTransport(boom),
    )
    with pytest.raises(DingtalkUnavailableError):
        await provider.exchange_token("bad")


@pytest.mark.kiwi_id(2201)
async def test_userinfo_union_id_priority_and_fallback() -> None:
    """用户信息：unionId 优先、回落 openId；携带访问令牌头；缺失邮箱为 None、缺昵称回落主体。"""
    mock = _DingtalkMock()
    user = await _provider(mock).userinfo("at-1")
    assert (user.subject, user.username, user.name, user.email) == ("union-1", "Alice", "Alice", "a@x")
    assert user.idp_key == CLIENT_ID
    assert mock.token_headers == ["at-1"]

    fallback = _DingtalkMock()
    fallback.user_body = {"unionId": "", "openId": "open-9"}
    fallback_user = await _provider(fallback).userinfo("at-2")
    assert (fallback_user.subject, fallback_user.username) == ("open-9", "open-9")
    assert fallback_user.email is None


@pytest.mark.kiwi_id(2201)
async def test_userinfo_auth_and_unavailable() -> None:
    """用户信息失败：4xx / 未返回身份 → 授权失败；5xx / 非 JSON / 非对象 → 不可达。"""
    rejected = _DingtalkMock()
    rejected.user_status = 401
    with pytest.raises(DingtalkAuthError):
        await _provider(rejected).userinfo("bad")

    no_subject = _DingtalkMock()
    no_subject.user_body = {"nick": "X"}
    with pytest.raises(DingtalkAuthError):
        await _provider(no_subject).userinfo("bad")

    server_error = _DingtalkMock()
    server_error.user_status = 500
    with pytest.raises(DingtalkUnavailableError):
        await _provider(server_error).userinfo("bad")

    not_json = _DingtalkMock()
    not_json.user_raw = b"not-json"
    with pytest.raises(DingtalkUnavailableError):
        await _provider(not_json).userinfo("bad")

    not_object = _DingtalkMock()
    not_object.user_raw = b"[1]"
    with pytest.raises(DingtalkUnavailableError):
        await _provider(not_object).userinfo("bad")


@pytest.mark.kiwi_id(2201)
def test_factory_reads_settings_and_requires_credentials() -> None:
    """工厂：缺 client_id / client_secret 拒启；配置齐产出实例且字段生效。"""
    defaults = IdentityProviderSettings()
    assert defaults.dingtalk_client_id == ""
    assert defaults.dingtalk_client_secret == ""
    assert defaults.dingtalk_scope == "openid"
    assert defaults.dingtalk_prompt == "consent"

    incomplete = Settings(identity_provider=IdentityProviderSettings(provider="dingtalk", dingtalk_client_id=CLIENT_ID))
    with pytest.raises(PluginError):
        DingtalkIdentityProviderFactory(incomplete).create(None)

    complete = Settings(
        identity_provider=IdentityProviderSettings(
            provider="dingtalk",
            dingtalk_client_id=CLIENT_ID,
            dingtalk_client_secret=CLIENT_SECRET,
            dingtalk_scope="openid corpid",
        )
    )
    provider = DingtalkIdentityProviderFactory(complete).create(None)
    assert isinstance(provider, DingtalkIdentityProvider)
    assert provider.key == "identity_provider"
    assert provider.plugin_name == "dingtalk"
    assert provider._scope == "openid corpid"  # pyright: ignore[reportPrivateUsage]
