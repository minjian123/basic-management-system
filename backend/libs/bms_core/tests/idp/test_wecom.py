"""企业微信身份源测试（Kiwi 2200）：授权跳转双形态 / gettoken+getuserinfo 身份解析 / 失败分支 / 工厂。

以 `httpx.MockTransport` 模拟企业微信 `gettoken` 与 `getuserinfo` 响应（成功 / 凭据失败 / 授权失败 / 非 2xx / 非
JSON），无需真实企业微信；真实企业凭据联调归阶段十七（见任务详细设计「边界与开放项」）。
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from bms_core.core.config import IdentityProviderSettings, Settings
from bms_core.core.exceptions import ConfigError, PluginError, WecomAuthError, WecomConfigError, WecomUnavailableError
from bms_core.idp.wecom import WecomIdentityProvider, WecomIdentityProviderFactory

type Handler = Callable[[httpx.Request], httpx.Response]

CORP_ID = "corp-1"
AGENT_ID = "agent-1"
SECRET = "secret-1"
REDIRECT_URI = "https://app.test/api/v1/auth/sso/wecom/callback"
DEFAULT_LOGIN_URL = "https://login.work.weixin.qq.com/wwlogin/sso/login"


class _WecomMock:
    """可控企业微信服务：`gettoken` / `getuserinfo` 两接口。"""

    def __init__(self) -> None:
        """初始化（默认成功响应）。"""
        self.token_body: object = {"errcode": 0, "access_token": "tok-1", "expires_in": 7200}
        self.token_status = 200
        self.token_raw: bytes | None = None
        self.userinfo_body: object = {"errcode": 0, "userid": "alice"}
        self.userinfo_status = 200
        self.token_calls = 0
        self.userinfo_calls = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        """MockTransport 处理函数（按路径分派）。

        Args:
            request: 出站请求。

        Returns:
            httpx.Response: 模拟响应。
        """
        path = request.url.path
        if path.endswith("/cgi-bin/gettoken"):
            self.token_calls += 1
            if self.token_raw is not None:
                return httpx.Response(self.token_status, content=self.token_raw)
            return httpx.Response(self.token_status, json=self.token_body)
        if path.endswith("/cgi-bin/auth/getuserinfo"):
            self.userinfo_calls += 1
            return httpx.Response(self.userinfo_status, json=self.userinfo_body)
        return httpx.Response(404, json={"errcode": 0})


def _provider(mock: _WecomMock, **kwargs: object) -> WecomIdentityProvider:
    """构造注入 MockTransport 的企业微信客户端。

    Args:
        mock: 可控服务。
        **kwargs: 覆盖构造参数。

    Returns:
        WecomIdentityProvider: 企业微信客户端实例。
    """
    return WecomIdentityProvider(
        corp_id=CORP_ID,
        agent_id=AGENT_ID,
        secret=SECRET,
        redirect_uri=REDIRECT_URI,
        transport=httpx.MockTransport(mock.handle),
        **kwargs,  # pyright: ignore[reportArgumentType]
    )


@pytest.mark.kiwi_id(2200)
async def test_authorize_qr_and_oauth() -> None:
    """授权跳转：qr 链接含登录类型 / appid / agentid / 回调 / state；oauth 链接含 scope 与锚点；入口可配。"""
    mock = _WecomMock()
    qr = await _provider(mock).authorize("state-1")
    parsed = urlparse(qr)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == DEFAULT_LOGIN_URL
    query = parse_qs(parsed.query)
    assert query["appid"] == [CORP_ID]
    assert query["agentid"] == [AGENT_ID]
    assert query["login_type"] == ["CorpApp"]
    assert query["redirect_uri"] == [REDIRECT_URI]
    assert query["state"] == ["state-1"]

    oauth = await _provider(mock, mode="oauth").authorize("state-2")
    assert oauth.endswith("#wechat_redirect")
    oauth_query = parse_qs(urlparse(oauth).query)
    assert oauth_query["appid"] == [CORP_ID]
    assert oauth_query["agentid"] == [AGENT_ID]
    assert oauth_query["scope"] == ["snsapi_base"]
    assert oauth_query["state"] == ["state-2"]

    custom = _provider(mock, login_url="https://login.test/x", oauth_url="https://oauth.test/y")
    assert (await custom.authorize("s")).startswith("https://login.test/x?")
    custom_oauth = _provider(mock, mode="oauth", oauth_url="https://oauth.test/y")
    assert (await custom_oauth.authorize("s")).startswith("https://oauth.test/y?")


@pytest.mark.kiwi_id(2200)
async def test_exchange_token_member_and_non_member_with_token_cache() -> None:
    """换身份：企业成员取 userid、非成员回落 openid；应用令牌进程内缓存复用（gettoken 只调一次）。"""
    mock = _WecomMock()
    provider = _provider(mock)
    member = await provider.exchange_token("code-1")
    assert member.access_token == ""
    identity = member.identity
    assert identity is not None
    assert (identity.subject, identity.username) == ("alice", "alice")
    assert identity.idp_key == CORP_ID

    mock.userinfo_body = {"errcode": 0, "openid": "openid-9", "external_userid": "ext-1"}
    non_member = await provider.exchange_token("code-2")
    non_member_identity = non_member.identity
    assert non_member_identity is not None
    assert non_member_identity.subject == "openid-9"
    assert mock.token_calls == 1
    assert mock.userinfo_calls == 2


@pytest.mark.kiwi_id(2200)
async def test_exchange_token_config_errors() -> None:
    """凭据类错误：gettoken 返回 errcode / 未返回令牌 / 缺 expires_in 均按配置处理（后者回落缺省 TTL）。"""
    bad_secret = _WecomMock()
    bad_secret.token_body = {"errcode": 40001, "errmsg": "invalid secret"}
    with pytest.raises(WecomConfigError):
        await _provider(bad_secret).exchange_token("code")

    no_token = _WecomMock()
    no_token.token_body = {"errcode": 0}
    with pytest.raises(WecomConfigError):
        await _provider(no_token).exchange_token("code")

    no_ttl = _WecomMock()
    no_ttl.token_body = {"errcode": 0, "access_token": "tok"}
    token = await _provider(no_ttl).exchange_token("code")
    assert token.identity is not None


@pytest.mark.kiwi_id(2200)
async def test_exchange_token_auth_errors() -> None:
    """授权类错误：getuserinfo 返回 errcode（code 无效 / 用户未授权）/ 未返回身份标识。"""
    invalid_code = _WecomMock()
    invalid_code.userinfo_body = {"errcode": 40029, "errmsg": "invalid code"}
    with pytest.raises(WecomAuthError):
        await _provider(invalid_code).exchange_token("code")

    no_subject = _WecomMock()
    no_subject.userinfo_body = {"errcode": 0}
    with pytest.raises(WecomAuthError):
        await _provider(no_subject).exchange_token("code")


@pytest.mark.kiwi_id(2200)
async def test_exchange_token_unavailable() -> None:
    """不可达类错误：非 2xx / 非 JSON / 非对象 / 网络异常均按接口不可用处理。"""
    http_500 = _WecomMock()
    http_500.token_status = 500
    with pytest.raises(WecomUnavailableError):
        await _provider(http_500).exchange_token("code")

    not_json = _WecomMock()
    not_json.token_raw = b"not-json"
    with pytest.raises(WecomUnavailableError):
        await _provider(not_json).exchange_token("code")

    not_object = _WecomMock()
    not_object.token_raw = b"[1, 2]"
    with pytest.raises(WecomUnavailableError):
        await _provider(not_object).exchange_token("code")

    def boom(request: httpx.Request) -> httpx.Response:
        del request
        raise httpx.ConnectError("down")

    provider = WecomIdentityProvider(
        corp_id=CORP_ID,
        agent_id=AGENT_ID,
        secret=SECRET,
        redirect_uri=REDIRECT_URI,
        transport=httpx.MockTransport(boom),
    )
    with pytest.raises(WecomUnavailableError):
        await provider.exchange_token("code")


@pytest.mark.kiwi_id(2200)
async def test_userinfo_unsupported() -> None:
    """企微无独立 userinfo 时序：调用抛配置错误。"""
    with pytest.raises(ConfigError):
        await _provider(_WecomMock()).userinfo("token-1")


@pytest.mark.kiwi_id(2200)
def test_factory_reads_settings_and_requires_credentials() -> None:
    """工厂：缺 corp_id / agent_id / secret 拒启；配置齐产出实例且字段生效。"""
    defaults = IdentityProviderSettings()
    assert defaults.wecom_corp_id == ""
    assert defaults.wecom_agent_id == ""
    assert defaults.wecom_secret == ""
    assert defaults.wecom_mode == "qr"
    assert defaults.wecom_login_type == "CorpApp"

    incomplete = Settings(identity_provider=IdentityProviderSettings(provider="wecom", wecom_corp_id=CORP_ID))
    with pytest.raises(PluginError):
        WecomIdentityProviderFactory(incomplete).create(None)

    complete = Settings(
        identity_provider=IdentityProviderSettings(
            provider="wecom",
            wecom_corp_id=CORP_ID,
            wecom_agent_id=AGENT_ID,
            wecom_secret=SECRET,
            wecom_mode="oauth",
            wecom_login_type="ServiceApp",
        )
    )
    provider = WecomIdentityProviderFactory(complete).create(None)
    assert isinstance(provider, WecomIdentityProvider)
    assert provider.key == "identity_provider"
    assert provider.plugin_name == "wecom"
    assert provider._mode == "oauth"  # pyright: ignore[reportPrivateUsage]
