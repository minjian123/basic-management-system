"""IdP 与会话存储基座契约测试（Kiwi 54）：契约 / 标识 / 常量 / 数据契约 / 占位固定返回 / 依赖解析。"""

from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from bms_core.api.deps import get_identity_provider, get_session_store
from bms_core.application import service_lifespan as lifespan
from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.exceptions import ConfigError
from bms_core.idp.base import (
    IDP_PROTOCOLS,
    BaseIdentityProvider,
    IdentityClaims,
    IdentityToken,
    IdentityUser,
)
from bms_core.idp.null import NullIdentityProvider
from bms_core.session.base import DEFAULT_SESSION_TTL, BaseSessionStore
from bms_core.session.null import NullSessionStore
from bms_identity.main import ApplicationFactory


@pytest.mark.kiwi_id(54)
def test_inheritance_and_keys() -> None:
    """两契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseIdentityProvider, BaseCapability)
    assert issubclass(NullIdentityProvider, BaseIdentityProvider)
    assert issubclass(NullIdentityProvider, BaseNullObject)
    assert BaseIdentityProvider.key == "identity_provider"

    assert issubclass(BaseSessionStore, BaseCapability)
    assert issubclass(NullSessionStore, BaseSessionStore)
    assert issubclass(NullSessionStore, BaseNullObject)
    assert BaseSessionStore.key == "session_store"

    for placeholder in (NullIdentityProvider(), NullSessionStore()):
        assert placeholder.placeholder is True
        assert "占位实现" in placeholder.describe()


@pytest.mark.kiwi_id(54)
def test_constants() -> None:
    """协议清单与默认会话 TTL 常量。"""
    assert IDP_PROTOCOLS == ("oidc", "cas", "wecom", "dingtalk")
    assert len(set(IDP_PROTOCOLS)) == len(IDP_PROTOCOLS)
    assert DEFAULT_SESSION_TTL == 1209600


@pytest.mark.kiwi_id(54)
def test_data_contracts_defaults_and_frozen() -> None:
    """`IdentityToken` / `IdentityUser` 默认值正确且不可变。"""
    token = IdentityToken(access_token="t")
    assert token.token_type == "Bearer"
    assert token.expires_in == 0

    user = IdentityUser(subject="s", username="u")
    assert user.email is None
    assert user.tenant is None

    field = "subject"
    with pytest.raises(FrozenInstanceError):
        setattr(user, field, "other")


@pytest.mark.kiwi_id(54)
async def test_null_identity_provider_fixed() -> None:
    """占位身份源三方法固定返回（不连外部 IdP）。"""
    provider = NullIdentityProvider()
    url = await provider.authorize("state-1")
    assert url
    assert await provider.exchange_token("code-1") == IdentityToken(access_token="null-idp-token")
    user = await provider.userinfo("token-1")
    assert user.subject == "null-idp-subject"
    assert user.username == "null-idp-user"


@pytest.mark.kiwi_id(54)
async def test_null_session_store() -> None:
    """占位会话存储：写 / 删空操作、读返回占位会话。"""
    store = NullSessionStore()
    assert await store.save("sess-1", {"user": "1"}) is None
    assert await store.load("sess-1") == {"session_id": "sess-1"}
    assert await store.delete("sess-1") is None


@pytest.mark.kiwi_id(54)
async def test_dependency_providers_resolve() -> None:
    """依赖解析：应用装配两占位单例；路由经两提供者取到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.identity_provider, NullIdentityProvider)
        assert isinstance(app.state.session_store, NullSessionStore)

        @app.get("/idp-probe")
        async def probe(  # pyright: ignore[reportUnusedFunction]
            provider: Annotated[BaseIdentityProvider, Depends(get_identity_provider)],
            store: Annotated[BaseSessionStore, Depends(get_session_store)],
        ) -> dict[str, object]:
            user = await provider.userinfo("t")
            session = await store.load("sess-1")
            return {
                "idp_key": provider.key,
                "idp_subject": user.subject,
                "session_key": store.key,
                "session": session,
            }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/idp-probe")

        assert resp.status_code == 200
        assert resp.json() == {
            "idp_key": "identity_provider",
            "idp_subject": "null-idp-subject",
            "session_key": "session_store",
            "session": {"session_id": "sess-1"},
        }


@pytest.mark.kiwi_id(2179)
def test_contract_extensions() -> None:
    """契约扩展：`id_token` / `refresh_token` / `idp_key` 默认与赋值；`IdentityClaims` 不可变。"""
    token = IdentityToken(access_token="t", id_token="id-token", refresh_token="refresh")
    assert token.id_token == "id-token"
    assert token.refresh_token == "refresh"
    assert IdentityToken(access_token="t").id_token is None
    assert IdentityToken(access_token="t").refresh_token is None

    assert IdentityUser(subject="s", username="u").idp_key == ""

    claims = IdentityClaims(subject="s", idp_key="issuer", issuer="issuer", audience=("api",), expires_at=1)
    assert claims.audience == ("api",)
    assert claims.payload == {}
    field = "subject"
    with pytest.raises(FrozenInstanceError):
        setattr(claims, field, "other")


@pytest.mark.kiwi_id(2179)
async def test_verify_token_default_and_null() -> None:
    """`BaseIdentityProvider.verify_token` 默认不支持该协议抛配置错误；占位实现返回占位声明。"""

    class _PlainProvider(BaseIdentityProvider):
        async def authorize(self, state: str) -> str:
            return "u"

        async def exchange_token(self, code: str) -> IdentityToken:
            return IdentityToken(access_token="a")

        async def userinfo(self, access_token: str) -> IdentityUser:
            return IdentityUser(subject="s", username="u")

    with pytest.raises(ConfigError):
        await _PlainProvider().verify_token("t")

    placeholder = await NullIdentityProvider().verify_token("t")
    assert placeholder.subject == "null-idp-subject"
    assert placeholder.idp_key == "null"
