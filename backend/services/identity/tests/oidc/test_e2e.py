"""OIDC Provider 端到端与 helper 分支测试（Kiwi 2202）。"""

from typing import cast

import pytest
from httpx import AsyncClient
from starlette.datastructures import FormData

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import OidcProviderSettings
from bms_core.core.exceptions import AuthError, OidcInvalidGrantError
from bms_core.db.session import DbSession
from bms_core.db.tenant import TenantContext, TenantLookup, TenantNotFoundError
from bms_core.idp.state.base import BaseIdpStateStore
from bms_core.oauth.oidc_provider import BaseOidcProvider
from bms_core.security.base import BasePasswordHasher
from bms_identity.api import clients as clients_api
from bms_identity.api import oidc as oidc_api
from bms_identity.services.oidc_provider import (
    OidcProviderService,
    clean_scope,
    code_from_payload,
    load_list,
    redirect_error,
    verify_pkce,
    with_query,
)
from bms_identity.services.org_client import OrgCredentialClient

from .conftest import OidcHarness
from .helpers import CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, TENANT_HEADERS, authorize_code, pkce


@pytest.mark.kiwi_id(2202)
async def test_end_to_end_flow(client: AsyncClient, oidc: OidcHarness) -> None:
    """端到端：授权 → 换码 → userinfo。"""
    await oidc.seed_client()
    verifier, challenge = pkce()
    code, _ = await authorize_code(client, code_challenge=challenge, code_challenge_method="S256")
    token = await client.post(
        "/api/v1/oidc/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
        auth=(CLIENT_ID, CLIENT_SECRET),
        headers=TENANT_HEADERS,
    )
    assert token.status_code == 200
    access_token = token.json()["access_token"]
    userinfo = await client.get(
        "/api/v1/oidc/userinfo", headers={**TENANT_HEADERS, "Authorization": f"Bearer {access_token}"}
    )
    assert userinfo.status_code == 200
    assert userinfo.json()["sub"] == "1001"


@pytest.mark.kiwi_id(2202)
def test_issuer_placeholder() -> None:
    """issuer 支持 `{tenant}` 占位；无占位原样返回。"""
    service = OidcProviderService(
        session=cast("DbSession", None),
        provider=cast("BaseOidcProvider", None),
        state_store=cast("BaseIdpStateStore", None),
        org_client=cast("OrgCredentialClient", None),
        password_hasher=cast("BasePasswordHasher", None),
        settings=OidcProviderSettings(issuer="http://gw.test/api/v1/oidc/{tenant}"),
    )
    assert service.issuer_for("demo") == "http://gw.test/api/v1/oidc/demo"
    no_placeholder = OidcProviderService(
        session=cast("DbSession", None),
        provider=cast("BaseOidcProvider", None),
        state_store=cast("BaseIdpStateStore", None),
        org_client=cast("OrgCredentialClient", None),
        password_hasher=cast("BasePasswordHasher", None),
        settings=OidcProviderSettings(issuer="http://gw.test/api/v1/oidc"),
    )
    assert no_placeholder.issuer_for("demo") == "http://gw.test/api/v1/oidc"


@pytest.mark.kiwi_id(2202)
def test_helpers_branches() -> None:
    """helper 分支：scope 归一、PKCE、授权码载荷非法、JSON 解析、URL 拼接。"""
    assert clean_scope("openid profile openid") == "openid profile"
    assert clean_scope(None) == ""

    verifier, challenge = pkce()
    assert verify_pkce(challenge, verifier) is True
    assert verify_pkce(challenge, None) is False
    assert verify_pkce(challenge, "other") is False

    with pytest.raises(OidcInvalidGrantError):
        code_from_payload(None)
    with pytest.raises(OidcInvalidGrantError):
        code_from_payload(ConcurrentStableDict({"client_id": "x"}))

    assert load_list('["a", "b"]') == ["a", "b"]
    assert load_list("{not-json") == []
    assert load_list('{"a": 1}') == []

    assert with_query("http://x/cb", "a=1") == "http://x/cb?a=1"
    assert with_query("http://x/cb?t=1", "a=1") == "http://x/cb?t=1&a=1"
    assert "error=invalid_scope" in redirect_error(REDIRECT_URI, "invalid_scope", "st")


@pytest.mark.kiwi_id(2202)
def test_issuer_invalid_template_falls_back() -> None:
    """issuer 模板非法（单花括号）时原样返回，不抛错。"""
    service = OidcProviderService(
        session=cast("DbSession", None),
        provider=cast("BaseOidcProvider", None),
        state_store=cast("BaseIdpStateStore", None),
        org_client=cast("OrgCredentialClient", None),
        password_hasher=cast("BasePasswordHasher", None),
        settings=OidcProviderSettings(issuer="{tenant"),
    )
    assert service.issuer_for("demo") == "{tenant"


@pytest.mark.kiwi_id(2202)
def test_api_layer_helpers() -> None:
    """API helper 分支：租户缺失、JSON 数组非法、Basic 头非法、表单缺值。"""
    with pytest.raises(AuthError):
        clients_api._require_tenant(None)  # pyright: ignore[reportPrivateUsage]
    assert clients_api._load_list("{bad") == []  # pyright: ignore[reportPrivateUsage]
    assert clients_api._load_list('{"a": 1}') == []  # pyright: ignore[reportPrivateUsage]

    assert oidc_api._decode_basic("!!!") is None  # pyright: ignore[reportPrivateUsage]
    assert oidc_api._decode_basic("bm9jb2xvbg==") is None  # pyright: ignore[reportPrivateUsage]
    assert oidc_api._form_str(FormData({}), "x") is None  # pyright: ignore[reportPrivateUsage]
    assert oidc_api._form_str(FormData({"x": ""}), "x") is None  # pyright: ignore[reportPrivateUsage]
    assert oidc_api._bearer(None) is None  # pyright: ignore[reportPrivateUsage]
    assert oidc_api._bearer("Basic x") is None  # pyright: ignore[reportPrivateUsage]


class _FakeTenantSource:
    """测试替身：按编码返回租户上下文。"""

    def __init__(self) -> None:
        """初始化。"""
        self.calls: ConcurrentStableList[str] = ConcurrentStableList()

    async def by_code(self, code: str) -> TenantContext:
        """返回租户上下文（带雪花主键）。

        Args:
            code: 租户编码。

        Returns:
            TenantContext: 租户上下文。
        """
        self.calls.add(code)
        tenant_id = 1001 if code == "demo" else 2002
        return TenantContext(code=code, db_key=f"tenant_{code}", name=code, tenant_id=tenant_id)

    async def single_active(self) -> TenantContext | None:
        """唯一启用租户解析（本替身恒返回演示租户）。

        Returns:
            TenantContext: 演示租户上下文。
        """
        return TenantContext(code="demo", db_key="tenant_demo", name="demo", tenant_id=1001)


@pytest.mark.kiwi_id(2202)
async def test_resolve_tenant_branches() -> None:
    """`_resolve` 四分支：参数命中上下文 / 参数回落租户源 / 上下文 / 均缺报错。"""
    source = _FakeTenantSource()
    context = TenantContext(code="demo", db_key="tenant_demo", name="demo", tenant_id=1001)
    lookup = cast("TenantLookup", source)
    assert await oidc_api._resolve("demo", context, lookup) is context  # pyright: ignore[reportPrivateUsage]
    assert await oidc_api._resolve("other", context, lookup) is not context  # pyright: ignore[reportPrivateUsage]
    assert await oidc_api._resolve(None, context, lookup) is context  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(TenantNotFoundError):
        await oidc_api._resolve(None, None, lookup)  # pyright: ignore[reportPrivateUsage]
