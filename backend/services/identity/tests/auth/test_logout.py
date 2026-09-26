"""登出端点测试（Kiwi 2194）：黑名单 + 会话撤销 + 删标记；幂等。"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_core.security.session import DefaultSessionSecurity
from bms_core.session.memory import MemorySessionStore

from .helpers import FakeOrgClient, FakeUserTokenIssuer, wire_auth

API_LOGIN = "/api/v1/auth/login"
API_LOGOUT = "/api/v1/auth/logout"
API_REFRESH = "/api/v1/auth/refresh"
COOKIE = "bms_refresh_token"


async def _prepare(client: AsyncClient, service_app: FastAPI) -> tuple[FakeUserTokenIssuer, MemorySessionStore]:
    """装配替身并完成一次登录。

    Args:
        client: 测试客户端。
        service_app: 应用实例。

    Returns:
        tuple[FakeUserTokenIssuer, MemorySessionStore]: (签发者替身, 会话存储替身)。
    """
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret", user_id=9)
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter)
    resp = await client.post(API_LOGIN, json={"account": "admin", "password": "secret"})
    assert resp.status_code == 200
    return issuer, store


@pytest.mark.kiwi_id(2194)
async def test_logout_revokes_and_is_idempotent(client: AsyncClient, service_app: FastAPI) -> None:
    """登出：标记删除 + 黑名单写入 + cookie 清除；refresh 随即失效；重复登出 200。"""
    issuer, store = await _prepare(client, service_app)
    session_id = issuer.specs[-1].session_id
    assert client.cookies.get(COOKIE)

    resp = await client.post(API_LOGOUT)
    assert resp.status_code == 200
    assert client.cookies.get(COOKIE) is None
    assert await store.load(session_id, tenant="demo") is None
    key = DefaultSessionSecurity(secret_key="").blacklist_key(session_id)
    assert await store.is_blacklisted(key) is True

    after = await client.post(API_REFRESH)
    assert after.status_code == 401

    again = await client.post(API_LOGOUT)
    assert again.status_code == 200


@pytest.mark.kiwi_id(2194)
async def test_logout_without_cookie(client: AsyncClient, service_app: FastAPI) -> None:
    """无 cookie 登出：幂等 200。"""
    await _prepare(client, service_app)
    client.cookies.clear()
    resp = await client.post(API_LOGOUT)
    assert resp.status_code == 200


@pytest.mark.kiwi_id(2194)
async def test_logout_with_invalid_token(client: AsyncClient, service_app: FastAPI) -> None:
    """无效 refresh cookie：登出仍 200（幂等，尽力清理）。"""
    await _prepare(client, service_app)
    client.cookies.clear()
    resp = await client.post(API_LOGOUT, headers={"Cookie": f"{COOKIE}=ref-unknown"})
    assert resp.status_code == 200


@pytest.mark.kiwi_id(2194)
async def test_logout_missing_jti_and_tenant(client: AsyncClient, service_app: FastAPI) -> None:
    """refresh 缺 jti / 租户不一致：登出仍 200（尽力而为）。"""
    issuer, _store = await _prepare(client, service_app)
    issuer.mint("ref-nojti", jti=None)
    client.cookies.clear()
    assert (await client.post(API_LOGOUT, headers={"Cookie": f"{COOKIE}=ref-nojti"})).status_code == 200

    issuer.mint("ref-mismatch", jti="sid-1", tenant_id="other")
    client.cookies.clear()
    assert (await client.post(API_LOGOUT, headers={"Cookie": f"{COOKIE}=ref-mismatch"})).status_code == 200


@pytest.mark.kiwi_id(2194)
async def test_logout_ghost_session(client: AsyncClient, service_app: FastAPI) -> None:
    """refresh 指向不存在的会话记录：登出仍 200（revoke 未命中 / TTL 兜底）。"""
    issuer, _store = await _prepare(client, service_app)
    issuer.mint("ref-ghost", jti="ghost-2", tenant_id="demo")
    client.cookies.clear()
    assert (await client.post(API_LOGOUT, headers={"Cookie": f"{COOKIE}=ref-ghost"})).status_code == 200
