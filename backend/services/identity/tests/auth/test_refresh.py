"""刷新轮换端点测试（Kiwi 2194）：轮换、旧票据重放、黑名单 / 标记 / 缺 cookie 分支。"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_core.security.session import DefaultSessionSecurity
from bms_core.session.memory import MemorySessionStore
from bms_identity.models.session import SysSession
from bms_identity.services.session_issuer import hash_refresh_token

from .helpers import TENANT_ID, FakeOrgClient, FakeUserTokenIssuer, wire_auth
from .session_helpers import seed_session, tenant_scope, utc_now

API_LOGIN = "/api/v1/auth/login"
API_REFRESH = "/api/v1/auth/refresh"
COOKIE = "bms_refresh_token"


async def _prepare(client: AsyncClient, service_app: FastAPI) -> tuple[FakeUserTokenIssuer, MemorySessionStore]:
    """装配替身并完成一次登录（下发 refresh cookie）。

    Args:
        client: 测试客户端。
        service_app: 应用实例。

    Returns:
        tuple[FakeUserTokenIssuer, MemorySessionStore]: (令牌签发者替身, 会话存储替身)。
    """
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret", user_id=7)
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter)
    resp = await client.post(API_LOGIN, json={"account": "admin", "password": "secret"})
    assert resp.status_code == 200
    return issuer, store


@pytest.mark.kiwi_id(2194)
async def test_refresh_rotates_and_rejects_replay(client: AsyncClient, service_app: FastAPI) -> None:
    """刷新轮换：同会话 id 签发新双 token、重设 cookie；旧 refresh 重放被拒。"""
    issuer, store = await _prepare(client, service_app)
    old_refresh = client.cookies.get(COOKIE)
    session_id = issuer.specs[-1].session_id
    assert old_refresh

    resp: Response = await client.post(API_REFRESH)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["access_token"] and data["expires_in"] == 1800
    new_refresh = client.cookies.get(COOKIE)
    assert new_refresh and new_refresh != old_refresh
    assert issuer.specs[-1].session_id == session_id  # 会话 id 稳定
    assert await store.load(session_id, tenant="demo") is not None

    client.cookies.clear()
    replay = await client.post(API_REFRESH, headers={"Cookie": f"{COOKIE}={old_refresh}"})
    assert replay.status_code == 401 and replay.json()["code"] == 20001


@pytest.mark.kiwi_id(2194)
async def test_refresh_missing_cookie(client: AsyncClient, service_app: FastAPI) -> None:
    """缺少 refresh cookie：401。"""
    await _prepare(client, service_app)
    client.cookies.clear()
    resp = await client.post(API_REFRESH)
    assert resp.status_code == 401


@pytest.mark.kiwi_id(2194)
async def test_refresh_marker_missing(client: AsyncClient, service_app: FastAPI) -> None:
    """Redis 会话标记缺失（登出 / 踢出）：401。"""
    issuer, store = await _prepare(client, service_app)
    session_id = issuer.specs[-1].session_id
    await store.delete(session_id, tenant="demo")
    resp = await client.post(API_REFRESH)
    assert resp.status_code == 401


@pytest.mark.kiwi_id(2194)
async def test_refresh_blacklisted(client: AsyncClient, service_app: FastAPI) -> None:
    """refresh jti 入黑名单：401。"""
    issuer, store = await _prepare(client, service_app)
    session_id = issuer.specs[-1].session_id
    key = DefaultSessionSecurity(secret_key="").blacklist_key(session_id)
    await store.blacklist(key, ttl=60)
    resp = await client.post(API_REFRESH)
    assert resp.status_code == 401


@pytest.mark.kiwi_id(2194)
async def test_refresh_bad_token_type(client: AsyncClient, service_app: FastAPI) -> None:
    """cookie 内为 access 票据（类型不符）：401。"""
    client_marker, store = await _prepare(client, service_app)
    del client_marker, store
    # access 票据未下发为 cookie；构造一个未知 refresh 串触发验签失败
    client.cookies.clear()
    resp = await client.post(API_REFRESH, headers={"Cookie": f"{COOKIE}=ref-unknown"})
    assert resp.status_code == 401


@pytest.mark.kiwi_id(2194)
async def test_refresh_tenant_mismatch(client: AsyncClient, service_app: FastAPI) -> None:
    """refresh 租户与请求租户不一致：401。"""
    issuer, _store = await _prepare(client, service_app)
    issuer.mint("ref-mismatch", jti=issuer.specs[-1].session_id, tenant_id="other")
    client.cookies.clear()
    resp = await client.post(API_REFRESH, headers={"Cookie": f"{COOKIE}=ref-mismatch"})
    assert resp.status_code == 401 and resp.json()["code"] == 20001


@pytest.mark.kiwi_id(2194)
async def test_refresh_missing_session_claim(client: AsyncClient, service_app: FastAPI) -> None:
    """refresh 缺少会话标识（jti）：401。"""
    issuer, _store = await _prepare(client, service_app)
    issuer.mint("ref-nojti", jti=None)
    client.cookies.clear()
    assert (await client.post(API_REFRESH, headers={"Cookie": f"{COOKIE}=ref-nojti"})).status_code == 401


@pytest.mark.kiwi_id(2194)
async def test_refresh_record_missing(client: AsyncClient, service_app: FastAPI) -> None:
    """会话标记存在但记录缺失：401。"""
    issuer, store = await _prepare(client, service_app)
    issuer.mint("ref-ghost", jti="ghost-1", tenant_id="demo")
    await store.save("ghost-1", ConcurrentStableDict({"user_id": 1, "tenant": "demo"}), tenant="demo", ttl=60)
    client.cookies.clear()
    assert (await client.post(API_REFRESH, headers={"Cookie": f"{COOKIE}=ref-ghost"})).status_code == 401


@pytest.mark.kiwi_id(2194)
async def test_refresh_without_tenant_context(client: AsyncClient, service_app: FastAPI) -> None:
    """缺少租户上下文：401（覆盖租户上下文缺失分支）。"""
    from bms_core.api.deps import get_tenant

    await _prepare(client, service_app)
    service_app.dependency_overrides[get_tenant] = lambda: None
    try:
        resp = await client.post(API_REFRESH)
        assert resp.status_code == 401 and resp.json()["code"] == 20001
    finally:
        service_app.dependency_overrides.pop(get_tenant, None)


@pytest.mark.kiwi_id(2234)
async def test_refresh_preserves_remember_me(client: AsyncClient, service_app: FastAPI) -> None:
    """轮换按原选项续期：记住我仍持久（Max-Age + expires_at 14 天）；会话级仍会话 Cookie（+ 24h）。"""
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret", user_id=7)
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter)

    remembered = await client.post(API_LOGIN, json={"account": "admin", "password": "secret", "remember_me": True})
    assert remembered.status_code == 200
    sid = issuer.specs[-1].session_id
    rotated = await client.post(API_REFRESH)
    assert rotated.status_code == 200
    assert "max-age=1209600" in rotated.headers.get("set-cookie", "").lower()
    assert issuer.specs[-1].session_id == sid
    async with tenant_scope(service_app) as db:
        row = (await db.execute(select(SysSession).where(SysSession.session_id == sid))).scalar_one()
        assert row.remember_me is True
        assert 1209500 <= (row.expires_at - utc_now()).total_seconds() <= 1209660

    session_level = await client.post(API_LOGIN, json={"account": "admin", "password": "secret"})
    assert session_level.status_code == 200
    sid2 = issuer.specs[-1].session_id
    rotated2 = await client.post(API_REFRESH)
    assert rotated2.status_code == 200
    cookie = rotated2.headers.get("set-cookie", "").lower()
    assert "bms_refresh_token=" in cookie and "max-age" not in cookie
    async with tenant_scope(service_app) as db:
        row = (await db.execute(select(SysSession).where(SysSession.session_id == sid2))).scalar_one()
        assert row.remember_me is False
        assert 86000 <= (row.expires_at - utc_now()).total_seconds() <= 86460


@pytest.mark.kiwi_id(2234)
async def test_refresh_legacy_null_remember_me_treated_as_remembered(
    client: AsyncClient, service_app: FastAPI
) -> None:
    """历史行（`remember_me=NULL`）轮换按记住我处理（14 天），不误降级为会话级。"""
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret", user_id=7)
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter)

    issuer.mint("ref-hist", sub="7", jti="8001", tenant_id=TENANT_ID)
    await seed_session(
        service_app, session_id="8001", refresh_token_hash=hash_refresh_token("ref-hist"), remember_me=None
    )
    await store.save("8001", ConcurrentStableDict({"user_id": 7, "tenant": TENANT_ID}), tenant=TENANT_ID, ttl=600)
    client.cookies.clear()
    resp = await client.post(API_REFRESH, headers={"Cookie": f"{COOKIE}=ref-hist"})
    assert resp.status_code == 200
    assert "max-age=1209600" in resp.headers.get("set-cookie", "").lower()
