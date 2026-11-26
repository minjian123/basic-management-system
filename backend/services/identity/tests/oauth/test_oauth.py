"""开放接口 OAuth2 服务端与 scope 基座契约测试（Kiwi 46）：契约 / 标识 / 常量 / 数据契约 / 占位固定返回 / 依赖解析。"""

from dataclasses import FrozenInstanceError

import pytest
from fastapi import FastAPI

from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.oauth.base import (
    GRANT_TYPES,
    NULL_ACCESS_TOKEN,
    TOKEN_TYPE_BEARER,
    BaseOAuthServer,
    BaseScopeChecker,
    ClientCredentials,
    OAuthToken,
)
from bms_core.oauth.null import NullOAuthServer, NullScopeChecker


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
    second = await server.issue_token(
        ClientCredentials(client_id="c2", client_secret="s2", scopes=ConcurrentStableFrozenList(("user:read",)))
    )

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
async def test_dependency_providers_resolve(service_app: FastAPI) -> None:
    """依赖解析：装配态两个占位实现就位，且提供者与本应用一致；占位令牌固定返回。

    插件实例按应用隔离（13_11）：不比跨应用实例同一性。
    """
    server = service_app.state.oauth_server
    checker = service_app.state.scope_checker
    assert isinstance(server, NullOAuthServer)
    assert isinstance(checker, NullScopeChecker)
    assert service_app.state.plugin_providers["oauth_server"] == "null"
    assert service_app.state.plugin_providers["scope_checker"] == "null"

    token = await server.issue_token(ClientCredentials(client_id="c", client_secret="s"))
    assert isinstance(token, OAuthToken)
    assert token.access_token == NULL_ACCESS_TOKEN
    assert token.token_type == TOKEN_TYPE_BEARER
