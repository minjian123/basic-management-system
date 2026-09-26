"""会话列表 / 详情端点测试（Kiwi 2195）：在线过滤、筛选、分页、详情与租户上下文。"""

from datetime import timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.api.deps import get_tenant

from .session_helpers import API_SESSIONS, TENANT_HEADERS, login, seed_session, utc_now, wire_login


@pytest.mark.kiwi_id(2195)
async def test_list_active_sessions_and_pagination(client: AsyncClient, service_app: FastAPI) -> None:
    """列表仅未撤销未过期会话；分页 total / page / size 正确。"""
    issuer, _store, _recorder = wire_login(service_app)
    assert (await login(client)).status_code == 200
    assert (await login(client, headers={"user-agent": "UA-2"})).status_code == 200
    assert (await login(client)).status_code == 200

    first = await client.get(API_SESSIONS, params={"size": 2}, headers=TENANT_HEADERS)
    assert first.status_code == 200
    data = first.json()["data"]
    assert data["total"] == 3 and data["page"] == 1 and data["size"] == 2
    assert len(data["list"]) == 2
    item = data["list"][0]
    assert int(item["user_id"]) == 1001 and item["revoked_at"] is None
    assert set(item) == {"session_id", "user_id", "device", "ip", "login_at", "expires_at", "revoked_at"}

    second = await client.get(API_SESSIONS, params={"size": 2, "page": 2}, headers=TENANT_HEADERS)
    assert len(second.json()["data"]["list"]) == 1
    assert {i["session_id"] for i in data["list"]} <= {s.session_id for s in issuer.specs}


@pytest.mark.kiwi_id(2195)
async def test_list_excludes_revoked_and_expired(client: AsyncClient, service_app: FastAPI) -> None:
    """列表排除已撤销（revoked_at 非空）与已过期（expires_at 过去）会话。"""
    _issuer, _store, _recorder = wire_login(service_app)
    now = utc_now()
    await seed_session(service_app, session_id="9001", revoked_at=now)
    await seed_session(service_app, session_id="9002", expires_at=now - timedelta(minutes=1))
    await seed_session(service_app, session_id="9003")

    resp = await client.get(API_SESSIONS, headers=TENANT_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 1
    assert resp.json()["data"]["list"][0]["session_id"] == "9003"


@pytest.mark.kiwi_id(2195)
async def test_list_filter_user_device_and_time(client: AsyncClient, service_app: FastAPI) -> None:
    """列表筛选：user_id 精确、device 模糊、登录时间闭区间。"""
    _issuer, _store, _recorder = wire_login(service_app)
    assert (await login(client, headers={"user-agent": "UA-Alpha"})).status_code == 200
    await seed_session(service_app, session_id="9101", user_id=2002, device="UA-Beta")

    by_user = await client.get(API_SESSIONS, params={"user_id": 2002}, headers=TENANT_HEADERS)
    assert by_user.json()["data"]["total"] == 1
    assert by_user.json()["data"]["list"][0]["session_id"] == "9101"

    by_device = await client.get(API_SESSIONS, params={"device": "Alpha"}, headers=TENANT_HEADERS)
    assert by_device.json()["data"]["total"] == 1

    now = utc_now()
    in_range = await client.get(
        API_SESSIONS,
        params={
            "login_from": (now - timedelta(days=1)).isoformat(),
            "login_to": (now + timedelta(days=1)).isoformat(),
        },
        headers=TENANT_HEADERS,
    )
    assert in_range.json()["data"]["total"] == 2

    future = await client.get(
        API_SESSIONS, params={"login_from": (now + timedelta(days=1)).isoformat()}, headers=TENANT_HEADERS
    )
    assert future.json()["data"]["total"] == 0


@pytest.mark.kiwi_id(2195)
async def test_detail_returns_any_record_including_revoked(client: AsyncClient, service_app: FastAPI) -> None:
    """详情返回任意记录（含已撤销），展示 revoked_at。"""
    _issuer, _store, _recorder = wire_login(service_app)
    now = utc_now()
    await seed_session(service_app, session_id="9201", revoked_at=now, device="UA-X", ip="10.0.0.9")

    resp = await client.get(f"{API_SESSIONS}/9201", headers=TENANT_HEADERS)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["session_id"] == "9201" and data["revoked_at"] is not None
    assert data["device"] == "UA-X" and data["ip"] == "10.0.0.9"


@pytest.mark.kiwi_id(2195)
async def test_detail_not_found(client: AsyncClient, service_app: FastAPI) -> None:
    """详情会话不存在 → 20011 / 404。"""
    wire_login(service_app)
    resp = await client.get(f"{API_SESSIONS}/not-exist", headers=TENANT_HEADERS)
    assert resp.status_code == 404 and resp.json()["code"] == 20011


@pytest.mark.kiwi_id(2195)
async def test_list_requires_tenant_context(client: AsyncClient, service_app: FastAPI) -> None:
    """无租户上下文 → 认证错误（20001 / 401）。"""
    wire_login(service_app)
    service_app.dependency_overrides[get_tenant] = lambda: None
    resp = await client.get(API_SESSIONS)
    assert resp.status_code == 401 and resp.json()["code"] == 20001
