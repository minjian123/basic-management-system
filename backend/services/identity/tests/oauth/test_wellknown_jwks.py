"""双类 JWT · JWKS 公开端点（Kiwi 2180 / 2193）：路由 / 合并公钥集 / 冲突 fail-closed / 空集 / 豁免路径。

`GET /.well-known/jwks.json` 由 identity 服务宿主，同端点发布服务令牌与用户令牌公钥；无密钥时返回空集。

重写口径（13_11）：端点直接读 `request.app.state` 的两类签发者，而写 `app.state` 属 P5 禁止项；
故用结构化替身承载 state、**直接调端点函数**验证合并 / 冲突 / 空集三条分支，路由挂载另用装配态断言。
"""

from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI, HTTPException, Request
from joserfc.jwk import RSAKey

from bms_core.db.tenant import DEFAULT_EXEMPT_PATHS
from bms_core.oauth.jwt import JwtServiceTokenIssuer
from bms_core.oauth.keys import TokenKey
from bms_core.oauth.user_jwt import JwtUserTokenIssuer
from bms_identity.domains.auth.api.wellknown import get_jwks

JWKS_PATH = "/.well-known/jwks.json"


def _service_issuer(kid: str = "svc-k1") -> JwtServiceTokenIssuer:
    """构造带公钥的服务 JWT 签发者。

    Args:
        kid: 密钥标识。

    Returns:
        JwtServiceTokenIssuer: 签发者。
    """
    key = RSAKey.generate_key(2048, private=True)
    return JwtServiceTokenIssuer(
        issuer="bms",
        keys=[
            TokenKey(
                kid=kid,
                algorithm="RS256",
                public_key=key.as_pem(private=False).decode(),
                private_key=key.as_pem(private=True).decode(),
            )
        ],
        active_kid=kid,
    )


def _user_issuer(kid: str = "usr-k1") -> JwtUserTokenIssuer:
    """构造带公钥的用户令牌签发者。

    Args:
        kid: 密钥标识（须带 `usr-` 前缀）。

    Returns:
        JwtUserTokenIssuer: 签发者。
    """
    key = RSAKey.generate_key(2048, private=True)
    return JwtUserTokenIssuer(
        issuer="bms",
        keys=[
            TokenKey(
                kid=kid,
                algorithm="RS256",
                public_key=key.as_pem(private=False).decode(),
                private_key=key.as_pem(private=True).decode(),
            )
        ],
        active_kid=kid,
        access_ttl=1800,
        refresh_ttl=1209600,
    )


def _request(**state: object) -> Request:
    """构造只承载 `state` 的请求（端点只读 `request.app.state` 的两个签发者）。

    Args:
        **state: 应用 state 上的属性。

    Returns:
        Request: 请求对象。
    """
    return Request(scope={"type": "http", "app": SimpleNamespace(state=SimpleNamespace(**state))})


@pytest.mark.kiwi_id(2180)
def test_jwks_path_is_tenant_exempt() -> None:
    """JWKS 端点纳入租户解析豁免缺省集。"""
    assert JWKS_PATH in DEFAULT_EXEMPT_PATHS


@pytest.mark.kiwi_id(2193)
async def test_jwks_route_merges_service_and_user_keys() -> None:
    """合并发布两类公钥（服务 `svc-*` + 用户 `usr-*`），只含公钥、按 kid 排序。"""
    payload = await get_jwks(_request(service_token=_service_issuer(), user_token=_user_issuer()))

    assert list(payload) == ["keys"]
    keys = cast("list[dict[str, object]]", payload["keys"])
    assert [item["kid"] for item in keys] == ["svc-k1", "usr-k1"]
    assert all(item["alg"] == "RS256" for item in keys)
    assert all("d" not in item for item in keys)


@pytest.mark.kiwi_id(2193)
async def test_jwks_route_conflict_is_unavailable() -> None:
    """两域 kid 冲突（同 kid 不同用途）→ 503（fail-closed，不发布有歧义的键集）。"""
    with pytest.raises(HTTPException) as captured:
        await get_jwks(_request(service_token=_service_issuer(kid="usr-k1"), user_token=_user_issuer(kid="usr-k1")))
    assert captured.value.status_code == 503


@pytest.mark.kiwi_id(2180)
async def test_jwks_route_empty_without_keys() -> None:
    """无密钥时返回空公钥集（不失败）。"""
    payload = await get_jwks(
        _request(
            service_token=JwtServiceTokenIssuer(issuer="bms", keys=[]),
            user_token=JwtUserTokenIssuer(issuer="bms", keys=[], access_ttl=1800, refresh_ttl=1209600),
        )
    )
    assert payload == {"keys": []}


@pytest.mark.kiwi_id(2193)
def test_jwks_route_registered_on_identity_app(service_app: FastAPI) -> None:
    """路由已挂载（装配态）：路径出现在 OpenAPI（端点由 identity 服务宿主）。"""
    assert JWKS_PATH in service_app.openapi()["paths"]
