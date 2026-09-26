"""强制踢出端点测试（Kiwi 2195）：即时生效、refresh 失效、幂等与错误分支、广播占位。"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.api.deps import get_tenant
from bms_core.security.session import DefaultSessionSecurity

from .session_helpers import API_SESSIONS, TENANT_HEADERS, login, wire_login

API_REFRESH = "/api/v1/auth/refresh"


def _blacklist_key(session_id: str) -> str:
    """会话黑名单键（与配置 `secret_key=""` 一致）。

    Args:
        session_id: 会话 id。

    Returns:
        str: 黑名单键。
    """
    return DefaultSessionSecurity(secret_key="").blacklist_key(session_id)


@pytest.mark.kiwi_id(2195)
async def test_kick_immediate_and_broadcast(client: AsyncClient, service_app: FastAPI) -> None:
    """踢出：返回撤销结果 + 标记删除 + 黑名单 + 广播占位 + 详情可见 revoked_at。"""
    issuer, store, recorder = wire_login(service_app)
    assert (await login(client)).status_code == 200
    session_id = issuer.specs[-1].session_id

    resp = await client.post(f"{API_SESSIONS}/{session_id}/kick", headers=TENANT_HEADERS)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["session_id"] == session_id and data["reason"] == "kick" and data["revoked_at"]

    assert await store.load(session_id, tenant="demo") is None
    assert await store.is_blacklisted(_blacklist_key(session_id)) is True
    assert recorder.events and recorder.events[-1].event == "session.revoked"
    assert recorder.events[-1].session_id == session_id

    detail = await client.get(f"{API_SESSIONS}/{session_id}", headers=TENANT_HEADERS)
    assert detail.json()["data"]["revoked_at"] is not None


@pytest.mark.kiwi_id(2195)
async def test_kick_invalidates_refresh(client: AsyncClient, service_app: FastAPI) -> None:
    """踢出后目标会话 refresh 随即 401（不等 access 自然过期）。"""
    issuer, _store, _recorder = wire_login(service_app)
    assert (await login(client)).status_code == 200
    session_id = issuer.specs[-1].session_id

    assert (await client.post(f"{API_SESSIONS}/{session_id}/kick", headers=TENANT_HEADERS)).status_code == 200
    refreshed = await client.post(API_REFRESH, headers=TENANT_HEADERS)
    assert refreshed.status_code == 401


@pytest.mark.kiwi_id(2195)
async def test_kick_is_idempotent(client: AsyncClient, service_app: FastAPI) -> None:
    """重复踢出已撤销会话 → 20013（幂等，不重复写）。"""
    issuer, _store, _recorder = wire_login(service_app)
    assert (await login(client)).status_code == 200
    session_id = issuer.specs[-1].session_id

    assert (await client.post(f"{API_SESSIONS}/{session_id}/kick", headers=TENANT_HEADERS)).status_code == 200
    again = await client.post(f"{API_SESSIONS}/{session_id}/kick", headers=TENANT_HEADERS)
    assert again.status_code == 200 and again.json()["code"] == 20013


@pytest.mark.kiwi_id(2195)
async def test_kick_not_found(client: AsyncClient, service_app: FastAPI) -> None:
    """踢出不存在的会话 → 20011 / 404。"""
    wire_login(service_app)
    resp = await client.post(f"{API_SESSIONS}/ghost/kick", headers=TENANT_HEADERS)
    assert resp.status_code == 404 and resp.json()["code"] == 20011


@pytest.mark.kiwi_id(2195)
async def test_kick_only_target_session(client: AsyncClient, service_app: FastAPI) -> None:
    """踢出一个会话不影响同用户其余在线会话。"""
    issuer, _store, _recorder = wire_login(service_app)
    assert (await login(client)).status_code == 200
    first = issuer.specs[-1].session_id
    assert (await login(client)).status_code == 200
    second = issuer.specs[-1].session_id

    assert (await client.post(f"{API_SESSIONS}/{first}/kick", headers=TENANT_HEADERS)).status_code == 200
    listing = await client.get(API_SESSIONS, headers=TENANT_HEADERS)
    assert listing.json()["data"]["total"] == 1
    assert listing.json()["data"]["list"][0]["session_id"] == second


@pytest.mark.kiwi_id(2195)
async def test_kick_requires_tenant_context(client: AsyncClient, service_app: FastAPI) -> None:
    """无租户上下文踢出 → 认证错误（20001 / 401）。"""
    issuer, _store, _recorder = wire_login(service_app)
    assert (await login(client)).status_code == 200
    service_app.dependency_overrides[get_tenant] = lambda: None
    resp = await client.post(f"{API_SESSIONS}/{issuer.specs[-1].session_id}/kick")
    assert resp.status_code == 401 and resp.json()["code"] == 20001
