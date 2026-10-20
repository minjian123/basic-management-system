"""identity 内部端点用例（Kiwi 2325）：按租户撤销全部会话（任务 `04_01`）。

覆盖：服务白名单（platform / tenant）、目标租户解析、参数透传与条数返回；会话撤销服务语义由
阶段六 / `SessionService` 专项用例覆盖，本文件只校验端点接线。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import ClassVar

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

import bms_identity.api.internal_sessions as module
from bms_core.api.deps import get_tenant_source, get_token_verifier
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import AuthError, TenantNotFoundError
from bms_core.db.tenant import TenantContext
from bms_core.oauth.verify import VerifiedToken

pytestmark = pytest.mark.kiwi_id(2325)

API = "/api/v1/identity/internal/sessions/revoke-tenant"
TENANT_ID = "1001"
TENANT = TenantContext(code="demo", db_key="tenant_demo", name="演示租户", tenant_id=int(TENANT_ID))


class _StubVerifier:
    """按令牌串返回服务身份（无签名）。"""

    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        del audience
        if token in {"platform", "tenant"}:
            return VerifiedToken(subject=token, service=token, token_type="service", tenant_id=TENANT_ID)
        if token in {"identity", "gateway"}:
            return VerifiedToken(subject=token, service=token, token_type="service")
        raise AuthError("invalid")


class _StubSource:
    """租户源替身：按编码返回演示租户。"""

    async def by_code(self, code: str) -> TenantContext:
        if code != "demo":
            raise TenantNotFoundError("未知租户")
        return TENANT

    async def by_domain(self, domain: str) -> TenantContext:
        del domain
        raise TenantNotFoundError("未实现")

    async def by_id(self, tenant_id: str) -> TenantContext:
        del tenant_id
        raise TenantNotFoundError("未实现")

    async def single_active(self) -> TenantContext | None:
        return TENANT


class _RecordingSessionService:
    """记录按租户撤销调用并返回固定条数。"""

    calls: ClassVar[ConcurrentStableList[tuple[str, str]]] = ConcurrentStableList()

    def __init__(self, **kwargs: object) -> None:
        del kwargs

    async def revoke_tenant_sessions(self, *, tenant: str | None, reason: str) -> ConcurrentStableList[str]:
        _RecordingSessionService.calls.add((str(tenant), reason))
        return ConcurrentStableList(["s-1", "s-2"])


@asynccontextmanager
async def _fake_scope(*args: object, **kwargs: object) -> AsyncGenerator[object]:
    del args, kwargs
    yield None


@pytest.fixture(autouse=True)
def patch_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """替换端点内构造的服务与库会话（只测端点接线）。"""
    _RecordingSessionService.calls = ConcurrentStableList()
    monkeypatch.setattr(module, "SessionService", _RecordingSessionService)
    monkeypatch.setattr(module, "session_scope", _fake_scope)


async def test_revoke_tenant_sessions_requires_service(client: AsyncClient, service_app: FastAPI) -> None:
    """鉴权：platform / tenant 放行；其他服务票据 / 无票据 401。"""
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    service_app.dependency_overrides[get_tenant_source] = lambda: _StubSource()

    payload = {"tenant_code": "demo"}
    for token in ("identity", "gateway", "bogus"):
        denied = await client.post(API, json=payload, headers={"Authorization": f"Bearer {token}"})
        assert denied.status_code == 401, token
    assert (await client.post(API, json=payload)).status_code == 401

    ok = await client.post(API, json=payload, headers={"Authorization": "Bearer tenant"})
    assert ok.status_code == 200
    assert ok.json()["data"] == {"revoked": 2}
    assert list(_RecordingSessionService.calls) == [(TENANT_ID, "tenant_suspended")]


async def test_revoke_tenant_sessions_unknown_tenant(client: AsyncClient, service_app: FastAPI) -> None:
    """目标租户不存在 → 80001 / 404。"""
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    service_app.dependency_overrides[get_tenant_source] = lambda: _StubSource()
    resp = await client.post(API, json={"tenant_code": "ghost"}, headers={"Authorization": "Bearer tenant"})
    assert resp.status_code == 404 and resp.json()["code"] == 80001


async def test_revoke_tenant_sessions_rejects_missing_code(client: AsyncClient, service_app: FastAPI) -> None:
    """入参：`tenant_code` 缺失 → 10001，不触发撤销。"""
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    service_app.dependency_overrides[get_tenant_source] = lambda: _StubSource()
    resp = await client.post(API, json={}, headers={"Authorization": "Bearer tenant"})
    assert resp.json()["code"] == 10001
    assert list(_RecordingSessionService.calls) == []


class _NoIdSource(_StubSource):
    """租户源替身：目标租户缺少主键标识。"""

    async def by_code(self, code: str) -> TenantContext:
        return TenantContext(code=code, db_key="tenant_demo", name="演示租户", tenant_id=None)


async def test_revoke_tenant_sessions_requires_tenant_id(client: AsyncClient, service_app: FastAPI) -> None:
    """目标租户缺少主键 → 401（不进入会话撤销）。"""
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    service_app.dependency_overrides[get_tenant_source] = lambda: _NoIdSource()
    resp = await client.post(API, json={"tenant_code": "demo"}, headers={"Authorization": "Bearer tenant"})
    assert resp.status_code == 401
    assert list(_RecordingSessionService.calls) == []
