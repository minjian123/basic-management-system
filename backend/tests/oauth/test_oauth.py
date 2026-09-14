"""开放接口 OAuth2 服务端与 scope 基座契约测试（Kiwi 46）：契约 / 标识 / 常量 / 数据契约 / 占位固定返回 / 依赖解析。"""

from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_oauth_server, get_scope_checker
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.main import create_app
from app.oauth.base import (
    GRANT_TYPES,
    NULL_ACCESS_TOKEN,
    TOKEN_TYPE_BEARER,
    BaseOAuthServer,
    BaseScopeChecker,
    ClientCredentials,
    NullOAuthServer,
    NullScopeChecker,
    OAuthToken,
)


@pytest.mark.kiwi_id(46)
def test_oauth_server_inheritance_and_key() -> None:
    """服务端契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseOAuthServer, BaseCapability)
    assert issubclass(NullOAuthServer, BaseOAuthServer)
    assert issubclass(NullOAuthServer, BaseNullObject)
    assert BaseOAuthServer.key == "oauth_server"

    server = NullOAuthServer()
    assert server.placeholder is True
    assert "占位实现" in server.describe()


@pytest.mark.kiwi_id(46)
def test_scope_checker_inheritance_and_key() -> None:
    """scope 契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseScopeChecker, BaseCapability)
    assert issubclass(NullScopeChecker, BaseScopeChecker)
    assert issubclass(NullScopeChecker, BaseNullObject)
    assert BaseScopeChecker.key == "scope_checker"

    checker = NullScopeChecker()
    assert checker.placeholder is True
    assert "占位实现" in checker.describe()


@pytest.mark.kiwi_id(46)
def test_grant_types_and_token_type_constants() -> None:
    """授权类型清单无重复；令牌类型为 Bearer。"""
    assert GRANT_TYPES == ("client_credentials", "authorization_code", "refresh_token")
    assert len(set(GRANT_TYPES)) == len(GRANT_TYPES)
    assert TOKEN_TYPE_BEARER == "Bearer"


@pytest.mark.kiwi_id(46)
def test_data_contracts_defaults_and_frozen() -> None:
    """`ClientCredentials` / `OAuthToken` 默认值正确且不可变。"""
    credentials = ClientCredentials(client_id="c1", client_secret="s1")
    assert credentials.scopes == ()

    token = OAuthToken(access_token="abc")
    assert token.token_type == TOKEN_TYPE_BEARER
    assert token.expires_in == 0
    assert token.scopes == ()

    field = "expires_in"
    with pytest.raises(FrozenInstanceError):
        setattr(token, field, 1)


@pytest.mark.kiwi_id(46)
async def test_null_server_returns_fixed_token() -> None:
    """占位服务端固定返回占位令牌（不签发、不因入参变化）。"""
    server = NullOAuthServer()
    first = await server.issue_token(ClientCredentials(client_id="c1", client_secret="s1"))
    second = await server.issue_token(ClientCredentials(client_id="c2", client_secret="s2", scopes=("user:read",)))

    assert first == OAuthToken(access_token=NULL_ACCESS_TOKEN)
    assert first == second
    assert first.access_token == "null-access-token"
    assert first.expires_in == 0
    assert first.scopes == ()


@pytest.mark.kiwi_id(46)
async def test_null_server_revoke_is_noop() -> None:
    """占位撤销为空操作。"""
    server = NullOAuthServer()
    assert await server.revoke("any-token") is None


@pytest.mark.kiwi_id(46)
def test_null_scope_checker_always_allows() -> None:
    """占位 scope 校验恒定允许（不校验）。"""
    checker = NullScopeChecker()
    assert checker.check((), "user:read") is True
    assert checker.check(("user:read",), "user:write") is True
    assert checker.check(["a", "b"], "admin") is True


@pytest.mark.kiwi_id(46)
async def test_dependency_providers_resolve() -> None:
    """依赖解析：应用装配两占位单例；路由经两提供者取到同一实例。"""
    app = create_app()
    assert isinstance(app.state.oauth_server, NullOAuthServer)
    assert isinstance(app.state.scope_checker, NullScopeChecker)

    @app.get("/oauth-probe")
    async def probe(  # pyright: ignore[reportUnusedFunction]
        server: Annotated[BaseOAuthServer, Depends(get_oauth_server)],
        checker: Annotated[BaseScopeChecker, Depends(get_scope_checker)],
    ) -> dict[str, object]:
        token = await server.issue_token(ClientCredentials(client_id="c", client_secret="s"))
        return {
            "server_key": server.key,
            "checker_key": checker.key,
            "token": token.access_token,
            "allowed": checker.check(("user:read",), "user:read"),
        }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/oauth-probe")

    assert resp.status_code == 200
    assert resp.json() == {
        "server_key": "oauth_server",
        "checker_key": "scope_checker",
        "token": "null-access-token",
        "allowed": True,
    }
