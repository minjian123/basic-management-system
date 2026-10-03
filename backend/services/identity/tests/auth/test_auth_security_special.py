"""安全专项用例 · 认证链路（Kiwi 2235）：限流爆破 / 会话劫持 / 越权 / 认证注入。

七类专项按被测物归属分处承载（见任务详细设计 §3.1）：本文件覆盖认证链路四类（限流爆破含 IP 维度、
会话劫持含过期与踢出后重放、越权跨租户与跨用户口径、认证注入边界）；基座横切四类见
`libs/bms_core/tests/security/test_security_controls.py`；XSS 见前端
`frontend/packages/ui-ep/tests/guard-vhtml-sanitize.spec.ts`。

落点说明：本文件与既有认证用例同包（`tests/auth/`）——用例复用本包 `helpers` / `session_helpers`
的替身与夹具（跨包相对导入不可用，`tests/` 无 `__init__.py`），故与既有用例并列而非另起子目录。
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_core.session.memory import MemorySessionStore
from bms_identity.services.session_issuer import hash_refresh_token

from .helpers import (
    TENANT_ID,
    FakeCaptcha,
    FakeOrgClient,
    FakeUserTokenIssuer,
    wire_auth,
)
from .session_helpers import API_SESSIONS, TENANT_HEADERS, login, seed_session, utc_now, wire_login

API_LOGIN = "/api/v1/auth/login"
API_REFRESH = "/api/v1/auth/refresh"
COOKIE = "bms_refresh_token"


@pytest.mark.kiwi_id(2235)
async def test_login_rate_limit_ip_and_account_dimensions(client: AsyncClient, service_app: FastAPI) -> None:
    """限流爆破：IP 维度超限 10005（换账号不绕过）、账号维度超限 10005（换 IP 不绕过）。"""
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret")
    org.set_user("other", password="secret")
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter)
    service_app.state.settings.login.ip_rate_limit = 1
    service_app.state.settings.login.account_rate_limit = 20
    try:
        assert (await login(client)).status_code == 200
        blocked = await login(client, account="other")
        assert blocked.status_code == 429 and blocked.json()["code"] == 10005
        keys = set(limiter._windows)  # pyright: ignore[reportPrivateUsage]
        assert any(key.startswith(f"bms:{TENANT_ID}:rate:ip:") for key in keys)
    finally:
        service_app.state.settings.login.ip_rate_limit = 20

    # 账号维度：放开 IP 后同一账号连续请求超限，换账号不受影响（证明命中账号维度而非 IP 维度）
    limiter.clear()
    service_app.state.settings.login.account_rate_limit = 1
    try:
        assert (await login(client)).status_code == 200
        limited = await login(client)
        assert limited.status_code == 429 and limited.json()["code"] == 10005
        assert (await login(client, account="other")).status_code == 200
        keys = set(limiter._windows)  # pyright: ignore[reportPrivateUsage]
        assert f"bms:{TENANT_ID}:rate:account:admin" in keys
    finally:
        service_app.state.settings.login.account_rate_limit = 20


@pytest.mark.kiwi_id(2235)
async def test_login_failure_escalates_to_captcha_within_ip_window(client: AsyncClient, service_app: FastAPI) -> None:
    """限流爆破：IP 窗口内连续失败达阈值即强制验证码（20101），携带有效凭证后放行并清零。"""
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret")
    captcha = FakeCaptcha(required=False, verified=True, fail_threshold=1)
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter, captcha=captcha)

    failed = await login(client, password="bad")
    assert failed.status_code == 401 and failed.json()["code"] == 20002

    forced = await login(client)
    assert forced.json()["code"] == 20101

    ok = await login(client, captcha={"captcha_id": "c", "kind": "image", "code": "x"})
    assert ok.status_code == 200
    cleared = await login(client, password="bad")
    assert cleared.json()["code"] == 20002


@pytest.mark.kiwi_id(2235)
async def test_session_hijack_forged_and_expired_refresh_rejected(client: AsyncClient, service_app: FastAPI) -> None:
    """会话劫持：伪造 refresh 串与过期会话记录均 401/20001（不是仅靠前端拦截）。"""
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret", user_id=7)
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter)

    client.cookies.clear()
    forged = await client.post(API_REFRESH, headers={"Cookie": f"{COOKIE}=ref-forged"})
    assert forged.status_code == 401 and forged.json()["code"] == 20001

    issuer.mint("ref-expired", sub="7", jti="7001", tenant_id=TENANT_ID)
    await seed_session(
        service_app,
        session_id="7001",
        user_id=7,
        expires_at=utc_now() - timedelta(minutes=1),
        refresh_token_hash=hash_refresh_token("ref-expired"),
    )
    await store.save("7001", ConcurrentStableDict({"user_id": 7, "tenant": TENANT_ID}), tenant=TENANT_ID, ttl=600)
    expired = await client.post(API_REFRESH, headers={"Cookie": f"{COOKIE}=ref-expired"})
    assert expired.status_code == 401 and expired.json()["code"] == 20001


@pytest.mark.kiwi_id(2235)
async def test_session_hijack_replay_after_kick_rejected(client: AsyncClient, service_app: FastAPI) -> None:
    """会话劫持：强制踢出后，被踢会话的旧 refresh 重放即 401（即时生效，不等自然过期）。"""
    issuer, _store, _recorder = await wire_login(service_app)
    assert (await login(client)).status_code == 200
    session_id = issuer.specs[-1].session_id
    old_refresh = client.cookies.get(COOKIE)
    assert old_refresh

    kicked = await client.post(f"{API_SESSIONS}/{session_id}/kick", headers=TENANT_HEADERS)
    assert kicked.status_code == 200

    client.cookies.clear()
    replay = await client.post(API_REFRESH, headers={"Cookie": f"{COOKIE}={old_refresh}"})
    assert replay.status_code == 401


@pytest.mark.kiwi_id(2235)
async def test_cross_tenant_access_rejected(client: AsyncClient, service_app: FastAPI) -> None:
    """越权（跨租户）：显式租户头与令牌租户不一致即拒（401/20001，不落到数据层）。"""
    await wire_login(service_app)
    mismatch = await client.get(API_SESSIONS, headers={"X-Tenant-ID": "acme"})
    assert mismatch.status_code == 401 and mismatch.json()["code"] == 20001


@pytest.mark.kiwi_id(2235)
async def test_cross_user_session_scope_is_platform_admin_pre_rbac(client: AsyncClient, service_app: FastAPI) -> None:
    """越权（跨用户）口径固化：RBAC 就绪前为平台超管口径。

    `require_permission` 当前为 Null 恒定通过，会话 `list/get/kick` 无 actor 归属校验——同租户内
    凭会话 id 可查看 / 踢出他人会话。本用例**固化该现状**（防口径漂移），归属校验归阶段七 RBAC
    （登记于阶段计划「后续阶段待办」）。
    """
    _issuer, _store, _recorder = await wire_login(service_app)
    await seed_session(service_app, session_id="8101", user_id=2002, device="UA-Other")

    listing = await client.get(API_SESSIONS, params={"user_id": 2002}, headers=TENANT_HEADERS)
    assert listing.status_code == 200
    assert listing.json()["data"]["total"] == 1
    assert listing.json()["data"]["list"][0]["session_id"] == "8101"

    kicked = await client.post(f"{API_SESSIONS}/8101/kick", headers=TENANT_HEADERS)
    assert kicked.status_code == 200


@pytest.mark.kiwi_id(2235)
async def test_login_contract_injection_boundaries(client: AsyncClient, service_app: FastAPI) -> None:
    """认证注入：契约层边界（空 / 超长）拦为 10001（不 5xx）；注入样本按字面透传 → 20002。"""
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret")
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter)

    blank = await client.post(API_LOGIN, json={"account": "   ", "password": "x"})
    assert blank.json()["code"] == 10001
    oversize_account = await client.post(API_LOGIN, json={"account": "a" * 65, "password": "x"})
    assert oversize_account.json()["code"] == 10001
    oversize_password = await client.post(API_LOGIN, json={"account": "admin", "password": "x" * 513})
    assert oversize_password.json()["code"] == 10001

    for payload in ("' OR '1'='1", "admin'--", "1; DROP TABLE sys_user; --"):
        resp = await client.post(API_LOGIN, json={"account": payload, "password": "x"})
        assert resp.status_code == 401 and resp.json()["code"] == 20002
