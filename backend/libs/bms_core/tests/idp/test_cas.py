"""CAS 身份源测试（Kiwi 2199）：授权跳转 / serviceValidate 解析 / 属性映射 / 安全护栏 / 工厂。

以 `httpx.MockTransport` 模拟 CAS `serviceValidate` 响应（成功 / `authenticationFailure` / 非 2xx / 非法 XML），
无需真实 CAS；真实 CAS IdP 联调归凭据就绪时（见任务详细设计「边界与开放项」）。
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import IdentityProviderSettings, Settings
from bms_core.core.exceptions import AuthError, ConfigError, PluginError, ServiceUnavailableError
from bms_core.idp.cas import (
    CasIdentityProvider,
    CasIdentityProviderFactory,
    normalize_attribute_map,
)

type Handler = Callable[[httpx.Request], httpx.Response]

SERVER = "https://cas.test/cas"
REDIRECT_URI = "https://app.test/api/v1/auth/sso/cas/callback"
SERVICE = f"{REDIRECT_URI}?state=state-1"


def _success_xml(
    principal: str = "alice",
    *,
    attributes: ConcurrentStableDict[str, str] | None = None,
    element_form: bool = True,
) -> bytes:
    """构造 CAS 校验成功响应 XML。

    Args:
        principal: `cas:user` 主体。
        attributes: 属性映射（None 用默认 displayName / email）。
        element_form: True 用「元素名即属性名」形态，False 用 `cas:attribute name=` 形态。

    Returns:
        bytes: XML 响应体。
    """
    attrs = (
        ConcurrentStableDict({"displayName": "Alice", "email": "alice@example.com"})
        if attributes is None
        else attributes
    )
    if element_form:
        body = "".join(f"<cas:{name}>{value}</cas:{name}>" for name, value in attrs.items())
    else:
        body = "".join(f'<cas:attribute name="{name}" value="{value}"/>' for name, value in attrs.items())
    return (
        '<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">'
        f"<cas:authenticationSuccess><cas:user>{principal}</cas:user>"
        f"<cas:attributes>{body}</cas:attributes></cas:authenticationSuccess></cas:serviceResponse>"
    ).encode()


def _failure_xml(code: str = "INVALID_TICKET") -> bytes:
    """构造 CAS 校验失败响应 XML。

    Args:
        code: `authenticationFailure` 的 code。

    Returns:
        bytes: XML 响应体。
    """
    return (
        '<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">'
        f'<cas:authenticationFailure code="{code}">bad ticket</cas:authenticationFailure>'
        "</cas:serviceResponse>"
    ).encode()


def _provider(handler: Handler, **kwargs: object) -> CasIdentityProvider:
    """构造注入 MockTransport 的 CAS 客户端。

    Args:
        handler: MockTransport 处理函数。
        **kwargs: 覆盖构造参数。

    Returns:
        CasIdentityProvider: CAS 客户端实例。
    """
    return CasIdentityProvider(
        server_url=SERVER,
        redirect_uri=REDIRECT_URI,
        transport=httpx.MockTransport(handler),
        **kwargs,  # pyright: ignore[reportArgumentType]
    )


def _responder(content: bytes, *, status: int = 200) -> Handler:
    """固定响应的 MockTransport 处理函数。

    Args:
        content: 响应体。
        status: 状态码。

    Returns:
        Handler: 处理函数。
    """

    def handle(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(status, content=content)

    return handle


@pytest.mark.kiwi_id(2199)
async def test_authorize_builds_login_url_with_service() -> None:
    """授权跳转：登录端点 + service（默认回退 redirect_uri；login_path 可配；state 原样保留）。"""
    provider = _provider(_responder(_success_xml()))
    url = await provider.authorize("state-1", service=SERVICE)
    parsed = urlparse(url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == f"{SERVER}/login"
    assert parse_qs(parsed.query)["service"] == [SERVICE]

    fallback = await provider.authorize("state-1")
    assert parse_qs(urlparse(fallback).query)["service"] == [REDIRECT_URI]

    custom = _provider(_responder(_success_xml()), login_path="/sso/login")
    assert urlparse(await custom.authorize("s", service=SERVICE)).path == "/cas/sso/login"


@pytest.mark.kiwi_id(2199)
async def test_exchange_token_success_and_default_mapping() -> None:
    """票据校验成功：请求 service / ticket 正确；身份按默认映射回填（无 username 属性时回落 principal）。"""
    seen: ConcurrentStableDict[str, ConcurrentStableList[str]] = ConcurrentStableDict()

    def handle(request: httpx.Request) -> httpx.Response:
        for key, values in parse_qs(request.url.query.decode()).items():
            seen.set(key, ConcurrentStableList(values))
        return httpx.Response(200, content=_success_xml())

    token = await _provider(handle).exchange_token("ST-1", service=SERVICE)
    assert seen["service"] == [SERVICE]
    assert seen["ticket"] == ["ST-1"]
    assert token.access_token == ""
    identity = token.identity
    assert identity is not None
    assert identity.subject == "alice"
    assert identity.username == "alice"
    assert identity.name == "Alice"
    assert identity.email == "alice@example.com"
    assert identity.idp_key == SERVER


@pytest.mark.kiwi_id(2199)
async def test_exchange_token_attribute_map_override_and_multi_value() -> None:
    """属性映射覆盖：行配置候选优先；多值取首 token；`cas:attribute` 形态兼容；未配置字段回落默认。"""
    provider = _provider(
        _responder(
            _success_xml(element_form=False, attributes=ConcurrentStableDict({"uid": "uid-9", "cn": "First Second"}))
        ),
        attribute_map={"username": ["uid"], "name": ["cn"]},
    )
    token = await provider.exchange_token("ST-2", service=SERVICE)
    identity = token.identity
    assert identity is not None
    assert identity.username == "uid-9"
    assert identity.name == "First"

    # 未覆盖字段仍用默认映射（email 缺省即 None）
    assert identity.email is None


@pytest.mark.kiwi_id(2199)
@pytest.mark.parametrize("code", ["INVALID_TICKET", "INVALID_SERVICE"])
async def test_exchange_token_failure_raises_auth_error(code: str) -> None:
    """`authenticationFailure`（票据无效 / 服务未注册）抛 AuthError，且不外泄原始 XML。"""
    provider = _provider(_responder(_failure_xml(code)))
    with pytest.raises(AuthError) as exc:
        await provider.exchange_token("ST-3", service=SERVICE)
    assert "bad ticket" not in str(exc.value)
    assert code in str(exc.value)


@pytest.mark.kiwi_id(2199)
async def test_exchange_token_unavailable_and_invalid_responses() -> None:
    """IdP 不可达 / 非 2xx / 非法 XML / 含 DOCTYPE / 缺节点 / 缺主体均按 IdP 响应非法处理（20053）。"""
    provider = _provider(_responder(b"", status=500))
    with pytest.raises(ServiceUnavailableError):
        await provider.exchange_token("ST-4", service=SERVICE)

    for content in (
        b"<not-xml",
        b'<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY x "y">]><foo/>',
        b'<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas"></cas:serviceResponse>',
        b'<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">'
        b"<cas:authenticationSuccess><cas:attributes/></cas:authenticationSuccess></cas:serviceResponse>",
    ):
        with pytest.raises(ServiceUnavailableError):
            await _provider(_responder(content)).exchange_token("ST-5", service=SERVICE)

    oversized = _provider(_responder(b"x" * (256 * 1024 + 1)))
    with pytest.raises(ServiceUnavailableError):
        await oversized.exchange_token("ST-6", service=SERVICE)


@pytest.mark.kiwi_id(2199)
async def test_userinfo_unsupported() -> None:
    """CAS 无独立 userinfo 时序：调用抛配置错误。"""
    provider = _provider(_responder(_success_xml()))
    with pytest.raises(ConfigError):
        await provider.userinfo("token-1")


@pytest.mark.kiwi_id(2199)
def test_factory_reads_settings_and_requires_server_url() -> None:
    """工厂：缺 cas_server_url 拒启；配置齐产出 CAS 客户端且路径 / 映射生效。"""
    defaults = IdentityProviderSettings()
    assert defaults.cas_server_url == ""
    assert defaults.cas_login_path == "/login"
    assert defaults.cas_service_validate_path == "/p3/serviceValidate"
    assert defaults.attribute_map == {}

    incomplete = Settings(identity_provider=IdentityProviderSettings(provider="cas"))
    with pytest.raises(PluginError):
        CasIdentityProviderFactory(incomplete).create(None)

    complete = Settings(
        identity_provider=IdentityProviderSettings(
            provider="cas",
            cas_server_url=SERVER,
            cas_login_path="/sso/login",
            attribute_map={"email": ["mail"]},
        )
    )
    provider = CasIdentityProviderFactory(complete).create(None)
    assert isinstance(provider, CasIdentityProvider)
    assert provider.key == "identity_provider"
    assert provider.plugin_name == "cas"
    assert provider._login_path == "/sso/login"  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2199)
def test_normalize_attribute_map_validates_and_ignores_unknown() -> None:
    """映射归一化：非对象 / 值非数组抛配置错误；未知字段忽略；空串剔除。"""
    assert normalize_attribute_map(None) == {}
    assert normalize_attribute_map({"username": ["uid", " "], "other": ["x"]}) == {"username": ("uid",)}

    with pytest.raises(ConfigError):
        normalize_attribute_map(["uid"])
    with pytest.raises(ConfigError):
        normalize_attribute_map({"email": "mail"})


@pytest.mark.kiwi_id(2199)
async def test_exchange_token_attribute_edge_cases() -> None:
    """属性边界：无 attributes 容器、空名属性、空值属性、构造期未知字段覆盖。"""
    no_attributes = (
        b'<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">'
        b"<cas:authenticationSuccess><cas:user>p1</cas:user></cas:authenticationSuccess>"
        b"</cas:serviceResponse>"
    )
    token = await _provider(_responder(no_attributes)).exchange_token("ST-7", service=SERVICE)
    identity = token.identity
    assert identity is not None
    assert (identity.username, identity.name, identity.email) == ("p1", None, None)

    empty_values = (
        b'<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">'
        b"<cas:authenticationSuccess><cas:user>p2</cas:user><cas:attributes>"
        b'<cas:attribute name=""/><cas:username></cas:username><cas:email>e@x</cas:email>'
        b"</cas:attributes></cas:authenticationSuccess></cas:serviceResponse>"
    )
    # 构造期传入未知字段覆盖（应被忽略，不报错）
    provider = _provider(_responder(empty_values), attribute_map={"unknown": ["x"]})
    identity2 = (await provider.exchange_token("ST-8", service=SERVICE)).identity
    assert identity2 is not None
    assert identity2.username == "p2"
    assert identity2.email == "e@x"
