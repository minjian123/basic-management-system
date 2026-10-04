"""refresh cookie 作用域与登出清理测试（Kiwi 2243；需求 01-7）。

覆盖：
- 登录 / 刷新轮换下发的 refresh cookie 作用路径为 `/`——浏览器按 `Path` 前缀匹配回传，而前端地址是
  网关外部路径 `/api/{service_key}/v1/...`，服务内路径 `/api/v1/auth` 永不回传（静默续期恒 401）；
- 登出按**当前路径（`/`）与历史路径（`/api/v1/auth`）各下发一次删除**（清理面干净）；
- 安全口径不回退：`HttpOnly` / `SameSite=lax` 保持，`remember_me` 的 `Max-Age` 语义不变。
"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_core.session.memory import MemorySessionStore

from .helpers import FakeOrgClient, FakeUserTokenIssuer, wire_auth

API_LOGIN = "/api/v1/auth/login"
API_LOGOUT = "/api/v1/auth/logout"
API_REFRESH = "/api/v1/auth/refresh"
COOKIE = "bms_refresh_token"
LEGACY_PATH = "/api/v1/auth"


async def _prepare(client: AsyncClient, service_app: FastAPI, *, remember_me: bool = True) -> None:
    """装配替身并完成一次登录。

    Args:
        client: 测试客户端。
        service_app: 应用实例。
        remember_me: 是否勾选「记住我」（true 时 cookie 带持久 `Max-Age`）。
    """
    issuer, org, store, limiter = FakeUserTokenIssuer(), FakeOrgClient(), MemorySessionStore(), MemoryRateLimiter()
    org.set_user("admin", password="secret", user_id=1001)
    wire_auth(service_app, issuer=issuer, org=org, store=store, limiter=limiter)
    resp = await client.post(API_LOGIN, json={"account": "admin", "password": "secret", "remember_me": remember_me})
    assert resp.status_code == 200


def _cookie_headers(response: Response) -> ConcurrentStableList[str]:
    """取响应中全部 `Set-Cookie` 头（小写化，便于断言）。

    Args:
        response: httpx 响应对象。

    Returns:
        ConcurrentStableList[str]: 全部 `Set-Cookie` 头。
    """
    return ConcurrentStableList(str(item).lower() for item in response.headers.get_list("set-cookie"))


@pytest.mark.kiwi_id(2243)
async def test_refresh_cookie_scope_is_root(client: AsyncClient, service_app: FastAPI) -> None:
    """登录与刷新轮换均下发 `Path=/`（同源可见，浏览器才回传）。"""
    await _prepare(client, service_app)

    login = await client.post(API_LOGIN, json={"account": "admin", "password": "secret", "remember_me": True})
    assert login.status_code == 200
    issued = _cookie_headers(login)
    assert len(issued) == 1
    header = issued[0]
    assert f"{COOKIE}=" in header
    assert "path=/" in header
    assert "httponly" in header
    assert "samesite=lax" in header
    assert "max-age=1209600" in header

    rotated = await client.post(API_REFRESH)
    assert rotated.status_code == 200
    rotated_header = _cookie_headers(rotated)[0]
    assert f"{COOKIE}=" in rotated_header and "path=/" in rotated_header
    assert "max-age=1209600" in rotated_header


@pytest.mark.kiwi_id(2243)
async def test_logout_clears_current_and_legacy_paths(client: AsyncClient, service_app: FastAPI) -> None:
    """登出：当前路径（`/`）与历史路径（`/api/v1/auth`）各下发一次删除。"""
    await _prepare(client, service_app)

    resp = await client.post(API_LOGOUT)
    assert resp.status_code == 200
    deletions = [header for header in _cookie_headers(resp) if COOKIE in header]
    assert len(deletions) == 2
    assert any("path=/" in header for header in deletions)
    assert any(f"path={LEGACY_PATH}" in header for header in deletions)
    for header in deletions:
        assert "max-age=0" in header
    assert client.cookies.get(COOKIE) is None
