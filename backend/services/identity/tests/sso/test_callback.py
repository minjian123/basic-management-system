"""SSO 回调闭环端点测试（Kiwi 2197）：换码验签 + 映射定位 + 会话签发 + 分支语义。"""

import hashlib
import json
from typing import cast

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableSet
from bms_core.db.tenant import TenantContext
from bms_identity.models.identity_provider import SysIdentityProvider
from bms_identity.models.session import SysSession
from bms_identity.models.user_identity import SysUserIdentity

from .conftest import SsoHarness
from .helpers import IDP_KEY, TENANT, TENANT_HEADERS, TENANT_ID

CALLBACK = f"/api/v1/auth/sso/{IDP_KEY}/callback"
OTHER_CALLBACK = "/api/v1/auth/sso/azure/callback"


async def _flow_callback(
    client: AsyncClient,
    sso: SsoHarness,
    *,
    code: str = "code-1",
    headers: ConcurrentStableDict[str, str] | None = None,
    sign_nonce: str | None = "flow",
):
    """发起授权后回调（ID Token nonce 默认取流程载荷）。

    Args:
        client: 测试客户端。
        sso: 装配套件。
        code: 授权码。
        headers: 请求头（None 用演示租户头）。
        sign_nonce: 签发的 nonce（"flow" 表示取流程 nonce；None 不签 ID Token）。

    Returns:
        httpx.Response: 回调响应。
    """
    state, _, payload = await sso.start_flow(client)
    if sign_nonce == "flow":
        sso.idp.make_id_token(nonce=cast("str", payload["nonce"]))
    elif sign_nonce is not None:
        sso.idp.make_id_token(nonce=sign_nonce)
    return await client.get(
        f"{CALLBACK}?state={state}&code={code}",
        headers=headers if headers is not None else TENANT_HEADERS,
    )


@pytest.mark.kiwi_id(2197)
async def test_callback_success_issues_session_and_cookie(client: AsyncClient, sso: SsoHarness) -> None:
    """成功闭环：200 + 租户回执 + refresh cookie + 租户库会话落库 + PKCE 换码。"""
    sso.org.set_user(1001)
    await sso.seed_provider()
    await sso.seed_mapping()

    response = await _flow_callback(client, sso)
    assert response.status_code == 200
    assert response.json()["data"] == {"tenant": TENANT}
    cookie = response.cookies["bms_refresh_token"]
    assert cookie.startswith("ref-")
    set_cookie = response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie and "Path=/api/v1/auth" in set_cookie and "SameSite=lax" in set_cookie

    assert "code_verifier=" in sso.idp.token_forms[-1]
    assert "code=code-1" in sso.idp.token_forms[-1]
    async with sso.tenant_scope() as session:
        rows = (await session.execute(select(SysSession))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.user_id == 1001
    assert row.refresh_token_hash == hashlib.sha256(cookie.encode()).hexdigest()
    assert sso.issuer.specs[-1].tenant_id == TENANT_ID
    assert sso.org.login_states[-1]["success"] is True
    assert "profile" in sso.org.calls and "login-state" in sso.org.calls

    replay = await client.get(
        f"{CALLBACK}?state=consumed-state&code=code-1",
        headers=TENANT_HEADERS,
    )
    assert replay.status_code == 400 and replay.json()["code"] == 20052


@pytest.mark.kiwi_id(2197)
async def test_callback_success_without_id_token_uses_userinfo(client: AsyncClient, sso: SsoHarness) -> None:
    """回退分支：IdP 未返 ID Token 时以 userinfo subject 定位映射并签发。"""
    sso.org.set_user(1001)
    await sso.seed_provider()
    await sso.seed_mapping()
    response = await _flow_callback(client, sso, sign_nonce=None)
    assert response.status_code == 200 and response.json()["code"] == 0


@pytest.mark.kiwi_id(2197)
async def test_callback_redirect_responses(client: AsyncClient, sso: SsoHarness) -> None:
    """可配跳转：成功 / 失败均 302（带参数），失败含错误码与提示。"""
    sso.org.set_user(1001)
    await sso.seed_provider()
    await sso.seed_mapping()
    sso.app.state.settings.sso.success_redirect = "http://app.test/sso/ok"
    sso.app.state.settings.sso.failure_redirect = "http://app.test/sso/fail"

    ok = await _flow_callback(client, sso)
    assert ok.status_code == 302
    assert ok.headers["location"] == "http://app.test/sso/ok?tenant=demo"
    assert "bms_refresh_token" in ok.cookies

    fail = await client.get(f"{CALLBACK}?state=missing&code=x", headers=TENANT_HEADERS)
    assert fail.status_code == 302
    location = fail.headers["location"]
    assert location.startswith("http://app.test/sso/fail?")
    assert "error=20052" in location and "message=" in location


@pytest.mark.kiwi_id(2197)
async def test_callback_state_failures(client: AsyncClient, sso: SsoHarness, monkeypatch: pytest.MonkeyPatch) -> None:
    """流程状态失败分支：未知 / 重放 / 身份源不符 / 租户不符 / IdP 错误 / 缺授权码。"""
    await sso.seed_provider()

    unknown = await client.get(f"{CALLBACK}?state=none&code=x", headers=TENANT_HEADERS)
    assert unknown.status_code == 400 and unknown.json()["code"] == 20052

    state, _, _ = await sso.start_flow(client)
    mismatch = await client.get(f"{OTHER_CALLBACK}?state={state}&code=x", headers=TENANT_HEADERS)
    assert mismatch.status_code == 400 and mismatch.json()["code"] == 20052
    assert state not in sso.states._items  # pyright: ignore[reportPrivateUsage]

    source = sso.app.state.tenant_source
    original = source.by_code

    async def fake_by_code(code: str) -> TenantContext:
        if code == "other":
            return TenantContext(code="other", db_key="tenant_other", name="其他租户")
        return await original(code)

    monkeypatch.setattr(source, "by_code", fake_by_code)
    state, _, _ = await sso.start_flow(client)
    wrong_tenant = await client.get(
        f"{CALLBACK}?state={state}&code=x",
        headers={"X-Tenant-ID": "other"},
    )
    assert wrong_tenant.status_code == 400 and wrong_tenant.json()["code"] == 20052

    state, _, _ = await sso.start_flow(client)
    denied = await client.get(
        f"{CALLBACK}?state={state}&error=access_denied",
        headers=TENANT_HEADERS,
    )
    assert denied.status_code == 400 and denied.json()["code"] == 20052
    assert "access_denied" in denied.json()["message"]

    state, _, _ = await sso.start_flow(client)
    no_code = await client.get(f"{CALLBACK}?state={state}", headers=TENANT_HEADERS)
    assert no_code.status_code == 400 and no_code.json()["code"] == 20052


@pytest.mark.kiwi_id(2197)
async def test_callback_provider_and_idp_failures(client: AsyncClient, sso: SsoHarness) -> None:
    """提供方 / IdP 失败分支：回调期停用 20051；换码 500 → 20053；nonce 与过期 → 20052。"""
    sso.org.set_user(1001)
    await sso.seed_provider()
    await sso.seed_mapping()

    state, _, _ = await sso.start_flow(client)
    await sso.set_provider_status("disabled")
    disabled = await client.get(f"{CALLBACK}?state={state}&code=x", headers=TENANT_HEADERS)
    assert disabled.status_code == 404 and disabled.json()["code"] == 20051

    await sso.set_provider_status("enabled")
    sso.idp.token_status = 500
    exchange_failed = await _flow_callback(client, sso, sign_nonce=None)
    assert exchange_failed.status_code == 503 and exchange_failed.json()["code"] == 20053

    sso.idp.token_status = 200
    wrong_nonce = await _flow_callback(client, sso, sign_nonce="not-the-flow-nonce")
    assert wrong_nonce.status_code == 400 and wrong_nonce.json()["code"] == 20052
    assert "ID Token" in wrong_nonce.json()["message"]

    state, _, payload = await sso.start_flow(client)
    sso.idp.make_id_token(nonce=cast("str", payload["nonce"]), exp_delta=-3600)
    expired = await client.get(f"{CALLBACK}?state={state}&code=code-1", headers=TENANT_HEADERS)
    assert expired.status_code == 400 and expired.json()["code"] == 20052

    sso.idp.jwks_status = 500
    jwks_down = await _flow_callback(client, sso)
    assert jwks_down.status_code == 503 and jwks_down.json()["code"] == 20053


@pytest.mark.kiwi_id(2197)
async def test_callback_identity_mapping_and_org_failures(client: AsyncClient, sso: SsoHarness) -> None:
    """映射与 org 失败分支：未命中 / 租户不符 20054；双行冲突 20055；禁用 20004；org 不可达 10007。"""
    await sso.seed_provider()
    sso.org.set_user(1001)

    unmatched = await _flow_callback(client, sso)
    assert unmatched.status_code == 403 and unmatched.json()["code"] == 20054

    async with sso.platform_scope() as session:
        session.add(
            SysUserIdentity(idp_key=f"{TENANT_ID}:{IDP_KEY}", external_id="sub-1", tenant_id="other", user_id=1001)
        )
        await session.commit()
    wrong_tenant = await _flow_callback(client, sso)
    assert wrong_tenant.status_code == 403 and wrong_tenant.json()["code"] == 20054
    async with sso.platform_scope() as session:
        await session.execute(delete(SysUserIdentity))
        await session.commit()

    await sso.seed_mapping(duplicate=True)
    conflict = await _flow_callback(client, sso)
    assert conflict.status_code == 409 and conflict.json()["code"] == 20055
    async with sso.platform_scope() as session:
        await session.execute(delete(SysUserIdentity))
        await session.commit()

    await sso.seed_mapping()
    sso.org.users = ConcurrentStableDict()
    org_missing = await _flow_callback(client, sso)
    assert org_missing.status_code == 403 and org_missing.json()["code"] == 20054

    sso.org.set_user(1001, status="disabled")
    disabled = await _flow_callback(client, sso)
    assert disabled.status_code == 401 and disabled.json()["code"] == 20004

    sso.org.set_user(1001)
    sso.org.fail_profile = True
    unavailable = await _flow_callback(client, sso)
    assert unavailable.status_code == 503 and unavailable.json()["code"] == 10007


@pytest.mark.kiwi_id(2197)
async def test_callback_config_and_dependency_failures(client: AsyncClient, sso: SsoHarness) -> None:
    """回调期配置 / 依赖失败：行配置非法 / 换码契约非法 / 验签配置缺失 / userinfo 不可达（20053）。"""
    sso.org.set_user(1001)
    await sso.seed_provider()
    await sso.seed_mapping()

    state, _, payload = await sso.start_flow(client)
    sso.idp.make_id_token(nonce=cast("str", payload["nonce"]))
    async with sso.tenant_scope() as session:
        row = (await session.execute(select(SysIdentityProvider))).scalars().one()
        row.config = "{not-json"
        await session.commit()
    bad_config = await client.get(f"{CALLBACK}?state={state}&code=code-1", headers=TENANT_HEADERS)
    assert bad_config.status_code == 503 and bad_config.json()["code"] == 20053

    async with sso.tenant_scope() as session:
        row = (await session.execute(select(SysIdentityProvider))).scalars().one()
        row.config = json.dumps(dict(sso.provider_config()))
        await session.commit()

    sso.idp.token_bad_json = True
    bad_token = await _flow_callback(client, sso)
    assert bad_token.status_code == 503 and bad_token.json()["code"] == 20053
    sso.idp.token_bad_json = False

    async with sso.tenant_scope() as session:
        row = (await session.execute(select(SysIdentityProvider))).scalars().one()
        row.icon = "bump"
        await session.commit()
    sso.idp.discovery_drop = ConcurrentStableSet({"jwks_uri"})
    bad_verify = await _flow_callback(client, sso)
    assert bad_verify.status_code == 503 and bad_verify.json()["code"] == 20053

    sso.idp.discovery_drop = None
    sso.idp.id_token = None
    sso.idp.userinfo_status = 500
    bad_userinfo = await _flow_callback(client, sso, sign_nonce=None)
    assert bad_userinfo.status_code == 503 and bad_userinfo.json()["code"] == 20053
