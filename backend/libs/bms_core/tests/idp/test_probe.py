"""身份源连通性探测测试（Kiwi 2203）：四协议 probe + 默认 / 占位 fail-closed。"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from bms_core.idp.base import BaseIdentityProvider, IdentityToken, IdentityUser, IdpProbeResult
from bms_core.idp.cas import CasIdentityProvider
from bms_core.idp.dingtalk import DingtalkIdentityProvider
from bms_core.idp.null import NullIdentityProvider
from bms_core.idp.oidc import OidcIdentityProvider
from bms_core.idp.wecom import WecomIdentityProvider

type Handler = Callable[[httpx.Request], httpx.Response]

ISSUER = "https://idp.example.com/realms/bms"


def _transport(handler: Handler) -> httpx.MockTransport:
    """构造 MockTransport。"""
    return httpx.MockTransport(handler)


def _oidc(handler: Handler) -> OidcIdentityProvider:
    """构造注入 MockTransport 的 OIDC 客户端。"""
    return OidcIdentityProvider(
        issuer=ISSUER,
        client_id="bms",
        client_secret="s",
        redirect_uri="https://app.test/cb",
        transport=_transport(handler),
    )


@pytest.mark.kiwi_id(2203)
async def test_oidc_probe_success_and_failures() -> None:
    """OIDC Discovery 探测：文档合规可达；非 2xx / 非 JSON / 缺字段不可达。"""
    document = {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
    }
    ok = await _oidc(lambda request: httpx.Response(200, json=document)).probe()
    assert ok == IdpProbeResult(reachable=True, protocol="oidc", status=200, detail="Discovery 正常")

    down = await _oidc(lambda request: httpx.Response(503, json={})).probe()
    assert down.reachable is False and down.status == 503

    broken = await _oidc(lambda request: httpx.Response(200, content=b"nope")).probe()
    assert broken.reachable is False

    incomplete = await _oidc(lambda request: httpx.Response(200, json={"issuer": ISSUER})).probe()
    assert incomplete.reachable is False

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    unreachable = await _oidc(boom).probe()
    assert unreachable.reachable is False


@pytest.mark.kiwi_id(2203)
async def test_cas_probe_reachable_and_unreachable() -> None:
    """CAS 端点任意 HTTP 响应可达；网络不可达为 False。"""
    ok = await CasIdentityProvider(
        server_url="https://cas.example.com/cas",
        redirect_uri="https://app.test/cb",
        transport=_transport(lambda request: httpx.Response(200, content=b"<xml/>")),
    ).probe()
    assert ok.reachable is True and ok.protocol == "cas"

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    down = await CasIdentityProvider(
        server_url="https://cas.example.com/cas",
        redirect_uri="https://app.test/cb",
        transport=_transport(boom),
    ).probe()
    assert down.reachable is False


@pytest.mark.kiwi_id(2203)
async def test_wecom_probe_credentials() -> None:
    """企微 gettoken：errcode=0 可达；errcode≠0 记不可达且 detail 含 errcode。"""
    ok = await WecomIdentityProvider(
        corp_id="corp-1",
        agent_id="agent-1",
        secret="s",
        redirect_uri="https://app.test/cb",
        transport=_transport(lambda request: httpx.Response(200, json={"errcode": 0, "access_token": "t"})),
    ).probe()
    assert ok.reachable is True

    bad = await WecomIdentityProvider(
        corp_id="corp-1",
        agent_id="agent-1",
        secret="s",
        redirect_uri="https://app.test/cb",
        transport=_transport(lambda request: httpx.Response(200, json={"errcode": 40001})),
    ).probe()
    assert bad.reachable is False and "40001" in bad.detail


def _dingtalk(handler: Handler) -> DingtalkIdentityProvider:
    """构造注入 MockTransport 的钉钉客户端。"""
    return DingtalkIdentityProvider(
        client_id="c-1",
        client_secret="s",
        redirect_uri="https://app.test/cb",
        transport=_transport(handler),
    )


@pytest.mark.kiwi_id(2203)
async def test_dingtalk_probe_reachable_and_5xx() -> None:
    """钉钉 userAccessToken：4xx 结构化响应可达；5xx / 网络不可达为 False。"""
    ok = await _dingtalk(lambda request: httpx.Response(400, json={"code": "invalid"})).probe()
    assert ok.reachable is True and ok.status == 400

    down = await _dingtalk(lambda request: httpx.Response(503, json={})).probe()
    assert down.reachable is False


@pytest.mark.kiwi_id(2203)
async def test_default_and_null_probe_fail_closed() -> None:
    """契约默认探测不可达；占位身份源 fail-closed。"""

    class _Plain(BaseIdentityProvider):
        async def authorize(self, state: str, **kwargs: object) -> str:
            return "u"

        async def exchange_token(self, code: str, **kwargs: object) -> IdentityToken:
            return IdentityToken(access_token="a")

        async def userinfo(self, access_token: str) -> IdentityUser:
            return IdentityUser(subject="s", username="u")

    default = await _Plain().probe()
    assert default.reachable is False

    placeholder = await NullIdentityProvider().probe()
    assert placeholder.reachable is False and placeholder.protocol == "null"
