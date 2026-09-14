"""IdP 与会话存储基座契约测试（Kiwi 54）：契约 / 标识 / 常量 / 数据契约 / 占位固定返回 / 依赖解析。"""

from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_identity_provider, get_session_store
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.idp.base import (
    IDP_PROTOCOLS,
    BaseIdentityProvider,
    IdentityToken,
    IdentityUser,
    NullIdentityProvider,
)
from app.main import create_app
from app.session.base import (
    DEFAULT_SESSION_TTL,
    BaseSessionStore,
    NullSessionStore,
)


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
    app = create_app()
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
