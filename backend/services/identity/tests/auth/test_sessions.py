"""会话列表 / 详情端点测试（Kiwi 2195）：在线过滤、筛选、分页、详情与租户上下文。

单库叠加口径（04-6-2）：会话行落共享租户库，用户主键 / 会话主键按用例命名空间派生，
列表断言一律带 `user_id` 筛选（禁止「全表 total」「list[0]」这类会被他人行命中的断言）。
"""

from datetime import timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.api.deps import get_tenant
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.db.tenant import TenantContext
from bms_core.testing.namespace import Namespace

from .session_helpers import API_SESSIONS, TENANT_HEADERS, login, seed_session, sid, uid, utc_now, wire_login


@pytest.mark.kiwi_id(2195)
async def test_list_active_sessions_and_pagination(client: AsyncClient, service_app: FastAPI, ns: Namespace) -> None:
    """列表仅未撤销未过期会话；分页 total / page / size 正确。"""
    subject = uid(ns)
    issuer, _store, _recorder = await wire_login(service_app, ns=ns)
    assert (await login(client)).status_code == 200
    assert (await login(client, headers=ConcurrentStableDict({"user-agent": "UA-2"}))).status_code == 200
    assert (await login(client)).status_code == 200

    first = await client.get(API_SESSIONS, params={"user_id": subject, "size": 2}, headers=TENANT_HEADERS)
    assert first.status_code == 200
    data = first.json()["data"]
    assert data["total"] == 3 and data["page"] == 1 and data["size"] == 2
    assert len(data["list"]) == 2
    item = data["list"][0]
    assert int(item["user_id"]) == subject and item["revoked_at"] is None
    assert set(item) == {"session_id", "user_id", "device", "ip", "login_at", "expires_at", "revoked_at"}

    second = await client.get(API_SESSIONS, params={"user_id": subject, "size": 2, "page": 2}, headers=TENANT_HEADERS)
    assert len(second.json()["data"]["list"]) == 1
    assert {i["session_id"] for i in data["list"]} <= {s.session_id for s in issuer.specs}


@pytest.mark.kiwi_id(2195)
async def test_list_excludes_revoked_and_expired(client: AsyncClient, service_app: FastAPI, ns: Namespace) -> None:
    """列表排除已撤销（revoked_at 非空）与已过期（expires_at 过去）会话。"""
    subject = uid(ns)
    _issuer, _store, _recorder = await wire_login(service_app, ns=ns)
    now = utc_now()
    await seed_session(service_app, session_id=sid(ns, 1), user_id=subject, revoked_at=now)
    await seed_session(service_app, session_id=sid(ns, 2), user_id=subject, expires_at=now - timedelta(minutes=1))
    await seed_session(service_app, session_id=sid(ns, 3), user_id=subject)

    resp = await client.get(API_SESSIONS, params={"user_id": subject}, headers=TENANT_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 1
    assert resp.json()["data"]["list"][0]["session_id"] == sid(ns, 3)


@pytest.mark.kiwi_id(2195)
async def test_list_filter_user_device_and_time(client: AsyncClient, service_app: FastAPI, ns: Namespace) -> None:
    """列表筛选：user_id 精确、device 模糊、登录时间闭区间。"""
    subject = uid(ns)
    other = uid(ns, 1)
    device = ns.code("ua-beta")
    _issuer, _store, _recorder = await wire_login(service_app, ns=ns)
    assert (await login(client, headers=ConcurrentStableDict({"user-agent": "UA-Alpha"}))).status_code == 200
    await seed_session(service_app, session_id=sid(ns, 1), user_id=other, device=device)

    by_user = await client.get(API_SESSIONS, params={"user_id": other}, headers=TENANT_HEADERS)
    assert by_user.json()["data"]["total"] == 1
    assert by_user.json()["data"]["list"][0]["session_id"] == sid(ns, 1)

    by_device = await client.get(API_SESSIONS, params={"device": device}, headers=TENANT_HEADERS)
    assert by_device.json()["data"]["total"] == 1

    now = utc_now()
    in_range = await client.get(
        API_SESSIONS,
        params={
            "user_id": subject,
            "login_from": (now - timedelta(days=1)).isoformat(),
            "login_to": (now + timedelta(days=1)).isoformat(),
        },
        headers=TENANT_HEADERS,
    )
    assert in_range.json()["data"]["total"] == 1

    future = await client.get(
        API_SESSIONS,
        params={"user_id": subject, "login_from": (now + timedelta(days=1)).isoformat()},
        headers=TENANT_HEADERS,
    )
    assert future.json()["data"]["total"] == 0


@pytest.mark.kiwi_id(2195)
async def test_detail_returns_any_record_including_revoked(
    client: AsyncClient, service_app: FastAPI, ns: Namespace
) -> None:
    """详情返回任意记录（含已撤销），展示 revoked_at。"""
    _issuer, _store, _recorder = await wire_login(service_app, ns=ns)
    now = utc_now()
    session_id = sid(ns)
    await seed_session(
        service_app, session_id=session_id, user_id=uid(ns), revoked_at=now, device="UA-X", ip="10.0.0.9"
    )

    resp = await client.get(f"{API_SESSIONS}/{session_id}", headers=TENANT_HEADERS)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["session_id"] == session_id and data["revoked_at"] is not None
    assert data["device"] == "UA-X" and data["ip"] == "10.0.0.9"


@pytest.mark.kiwi_id(2195)
async def test_detail_not_found(client: AsyncClient, service_app: FastAPI, ns: Namespace) -> None:
    """详情会话不存在 → 20011 / 404。"""
    await wire_login(service_app, ns=ns)
    resp = await client.get(f"{API_SESSIONS}/{sid(ns, 9)}", headers=TENANT_HEADERS)
    assert resp.status_code == 404 and resp.json()["code"] == 20011


@pytest.mark.kiwi_id(2195)
async def test_list_requires_tenant_context(client: AsyncClient, service_app: FastAPI, ns: Namespace) -> None:
    """无租户上下文 → 认证错误（20001 / 401）。"""
    await wire_login(service_app, ns=ns)
    service_app.dependency_overrides[get_tenant] = lambda: None
    resp = await client.get(API_SESSIONS)
    assert resp.status_code == 401 and resp.json()["code"] == 20001


@pytest.mark.kiwi_id(2195)
async def test_list_requires_tenant_primary_key(client: AsyncClient, service_app: FastAPI, ns: Namespace) -> None:
    """上下文租户缺主键（演示兜底口径）→ 认证错误（20001 / 401）。"""
    await wire_login(service_app, ns=ns)
    service_app.dependency_overrides[get_tenant] = lambda: TenantContext(
        code="demo", db_key="tenant_demo", name="演示租户"
    )
    resp = await client.get(API_SESSIONS)
    assert resp.status_code == 401 and resp.json()["code"] == 20001
