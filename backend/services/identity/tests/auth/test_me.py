"""当前用户概要端点测试（Kiwi 2229）：成功、改密标记、三类失败分支与下游不可达。

以 `/api/v1/auth/me`（`require_auth` + org 内部用户概要）为受测面；令牌用测试夹具真实签名
（`aud=api`），会话标记用内存替身，org 用户概要经 `FakeOrgClient` 的 `profile` 动作提供。
"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_core.servicecall.base import ServiceRequest, ServiceResponse
from bms_core.session.memory import MemorySessionStore
from tests_support.auth import TEST_SESSION_ID

from .helpers import TENANT_ID, FakeOrgClient, FakeUserTokenIssuer, wire_auth
from .session_helpers import TENANT_HEADERS

pytestmark = pytest.mark.kiwi_id(2229)

API_ME = "/api/v1/auth/me"


class _DownOrgClient(FakeOrgClient):
    """测试替身：下游不可达（非 2xx）的 org 客户端。"""

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """一律返回 503（模拟 org 不可达）。

        Args:
            request: 服务间调用请求（未使用）。

        Returns:
            ServiceResponse: 503 响应。
        """
        del request
        return ServiceResponse(status_code=503, content=b"{}")


async def _wire(
    app: FastAPI,
    *,
    user_id: int = 1001,
    status: str = "enabled",
    pwd_reset_required: bool = False,
    org: FakeOrgClient | None = None,
) -> None:
    """装配认证链路替身（签发者 / org / 会话标记 / 限流）。

    Args:
        app: 应用实例。
        user_id: org 侧登记的用户主键（与令牌 `sub` 不一致即覆盖「用户不存在」分支）。
        status: 账号状态。
        pwd_reset_required: 是否需强制改密。
        org: org 客户端替身（None 用标准替身）。
    """
    issuer: FakeUserTokenIssuer = FakeUserTokenIssuer()
    client = org if org is not None else FakeOrgClient()
    store = MemorySessionStore()
    if not isinstance(client, _DownOrgClient):
        client.set_user(
            "admin",
            password="secret",
            user_id=user_id,
            name="管理员",
            status=status,
            pwd_reset_required=pwd_reset_required,
        )
    await store.save(TEST_SESSION_ID, ConcurrentStableDict({"user_id": 1001, "tenant": TENANT_ID}), tenant=TENANT_ID)
    wire_auth(app, issuer=issuer, org=client, store=store, limiter=MemoryRateLimiter())


async def test_me_returns_summary_consistent_with_login(client: AsyncClient, service_app: FastAPI) -> None:
    """有效登录态：200 且概要字段与登录响应同口径（本任务用户无强制改密）。"""
    await _wire(service_app)

    resp = await client.get(API_ME, headers=TENANT_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["data"] == {
        "id": "1001",
        "username": "admin",
        "name": "管理员",
        "tenant": "demo",
        "locale": None,
        "timezone": None,
        "must_change_password": False,
    }


async def test_me_maps_password_reset_required(client: AsyncClient, service_app: FastAPI) -> None:
    """强制改密标记与 org 概要同源：超期用户返回真值。"""
    await _wire(service_app, pwd_reset_required=True)

    resp = await client.get(API_ME, headers=TENANT_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["data"]["must_change_password"] is True


async def test_me_rejects_unknown_user_and_disabled_account(client: AsyncClient, service_app: FastAPI) -> None:
    """用户不存在 / 账号停用 → 401（按登录态失效处理）。"""
    await _wire(service_app, user_id=2002)
    missing = await client.get(API_ME, headers=TENANT_HEADERS)
    assert missing.status_code == 401
    assert missing.json()["code"] == 20001

    await _wire(service_app, status="disabled")
    disabled = await client.get(API_ME, headers=TENANT_HEADERS)
    assert disabled.status_code == 401
    assert disabled.json()["code"] == 20004


async def test_me_rejects_invalid_token(client: AsyncClient, service_app: FastAPI) -> None:
    """令牌无效 → 401（20001，由 `require_auth` 拦截）。"""
    await _wire(service_app)

    resp = await client.get(API_ME, headers={**TENANT_HEADERS, "Authorization": "Bearer not-a-token"})
    assert resp.status_code == 401
    assert resp.json()["code"] == 20001


async def test_me_fails_closed_when_org_unavailable(client: AsyncClient, service_app: FastAPI) -> None:
    """org 不可达 → 503（10007，fail-closed，不降级为 401）。"""
    await _wire(service_app, org=_DownOrgClient())

    resp = await client.get(API_ME, headers=TENANT_HEADERS)
    assert resp.status_code == 503
    assert resp.json()["code"] == 10007
