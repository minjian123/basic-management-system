"""自助改密端点测试（任务 `04_01`；Kiwi 2325）。

覆盖：旧口令校验、密码策略 / 历史拒绝、成功改密与其它会话失效、账号不存在、缺租户上下文。

单库叠加口径（04-6-2）：改密会按**本用例用户**撤销在线会话，故用户主键与令牌主体均按用例命名空间
派生（固定 `1001` 会在共享库上统计到他人会话，`revoked_sessions` 断言失真）。
"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_core.session.memory import MemorySessionStore
from bms_core.testing.namespace import Namespace
from tests_support.auth import TEST_SESSION_ID, auth_headers

from .helpers import TENANT_ID, FakePlatformClient, FakeUserTokenIssuer, wire_auth
from .session_helpers import TENANT_HEADERS

pytestmark = pytest.mark.kiwi_id(2325)

API = "/api/v1/auth/change-password"


def _uid(ns: Namespace) -> int:
    """本用例的用户主键。

    Args:
        ns: 用例命名空间。

    Returns:
        int: 用户主键。
    """
    return int(ns.prefix[2:], 16) * 100 + 1


def _headers(subject: int) -> ConcurrentStableDict[str, str]:
    """带本用例主体的鉴权头（叠加租户头）。

    Args:
        subject: 用户主键（令牌 `sub`）。

    Returns:
        ConcurrentStableDict[str, str]: 请求头。

    """
    headers: ConcurrentStableDict[str, str] = ConcurrentStableDict(auth_headers(subject=str(subject)))
    headers.update(TENANT_HEADERS.items())
    return headers


async def _wire(service_app: FastAPI, subject: int, *, user: bool = True) -> FakePlatformClient:
    """装配认证链路替身并保存当前会话标记。

    Args:
        service_app: 应用实例。
        subject: 本用例用户主键（platform 侧用户与会话标记同口径）。
        user: 是否登记 platform 侧用户。

    Returns:
        FakePlatformClient: platform 客户端替身。
    """
    client = FakePlatformClient()
    if user:
        client.set_user("admin", password="secret", user_id=subject, name="管理员")
    store = MemorySessionStore()
    await store.save(TEST_SESSION_ID, ConcurrentStableDict({"user_id": subject, "tenant": TENANT_ID}), tenant=TENANT_ID)
    wire_auth(
        service_app,
        issuer=FakeUserTokenIssuer(),
        platform_client=client,
        store=store,
        limiter=MemoryRateLimiter(),
    )
    return client


async def test_change_password_success(client: AsyncClient, service_app: FastAPI, ns: Namespace) -> None:
    """旧口令正确 → 改密成功、platform 更新口令、返回失效会话数。"""
    subject = _uid(ns)
    platform = await _wire(service_app, subject)
    resp = await client.post(
        API,
        json={"old_password": "secret", "new_password": "NewPass@123"},
        headers=_headers(subject),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["changed"] is True and data["revoked_sessions"] == 0
    assert platform.users["admin"]["password"] == "NewPass@123"
    assert "update-password" in platform.calls


async def test_change_password_wrong_old(client: AsyncClient, service_app: FastAPI, ns: Namespace) -> None:
    """旧口令错误 → 401 / 20001，不更新口令。"""
    subject = _uid(ns)
    platform = await _wire(service_app, subject)
    resp = await client.post(
        API,
        json={"old_password": "bad", "new_password": "NewPass@123"},
        headers=_headers(subject),
    )
    assert resp.status_code == 401 and resp.json()["code"] == 20001
    assert platform.users["admin"]["password"] == "secret"


async def test_change_password_policy_and_history(client: AsyncClient, service_app: FastAPI, ns: Namespace) -> None:
    """策略违规 30005 / 历史重复 30006 原样上抛。"""
    subject = _uid(ns)
    await _wire(service_app, subject)
    weak = await client.post(
        API, json={"old_password": "secret", "new_password": "weak"}, headers=_headers(subject)
    )
    assert weak.json()["code"] == 30005
    reused = await client.post(
        API, json={"old_password": "secret", "new_password": "old-pass"}, headers=_headers(subject)
    )
    assert reused.json()["code"] == 30006


async def test_change_password_unknown_user(client: AsyncClient, service_app: FastAPI, ns: Namespace) -> None:
    """platform 侧账号不存在 → 401。"""
    subject = _uid(ns)
    await _wire(service_app, subject, user=False)
    resp = await client.post(
        API,
        json={"old_password": "secret", "new_password": "NewPass@123"},
        headers=_headers(subject),
    )
    assert resp.status_code == 401


async def test_platform_tenant_code_endpoint(client: AsyncClient) -> None:
    """平台租户编码端点：免登录返回配置值。"""
    resp = await client.get("/api/v1/auth/platform-tenant")
    assert resp.status_code == 200
    assert resp.json()["data"]["code"] == "platform"


async def test_change_password_requires_subject(client: AsyncClient, service_app: FastAPI, ns: Namespace) -> None:
    """登录态缺少用户主键 → 401（内部契约异常路径）。"""
    subject = _uid(ns)
    await _wire(service_app, subject)
    from bms_core.api.base import AuthContext, require_auth

    service_app.dependency_overrides[require_auth] = lambda: AuthContext(subject="anonymous", user_id=None)
    resp = await client.post(
        API,
        json={"old_password": "secret", "new_password": "NewPass@123"},
        headers=_headers(subject),
    )
    assert resp.status_code == 401


async def test_change_password_requires_tenant(client: AsyncClient, service_app: FastAPI, ns: Namespace) -> None:
    """缺少租户上下文 → 401。"""
    subject = _uid(ns)
    await _wire(service_app, subject)
    from bms_core.api.deps import get_tenant

    service_app.dependency_overrides[get_tenant] = lambda: None
    resp = await client.post(
        API,
        json={"old_password": "secret", "new_password": "NewPass@123"},
        headers=_headers(subject),
    )
    assert resp.status_code == 401


async def test_change_password_update_failure(client: AsyncClient, service_app: FastAPI, ns: Namespace) -> None:
    """platform 更新口令失败 → 401（不返回成功）。"""
    subject = _uid(ns)
    await _wire(service_app, subject)
    resp = await client.post(
        API,
        json={"old_password": "secret", "new_password": "UpdateFail@1"},
        headers=_headers(subject),
    )
    assert resp.status_code == 401
