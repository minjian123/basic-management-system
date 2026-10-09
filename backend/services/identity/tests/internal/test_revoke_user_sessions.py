"""identity 内部端点用例（Kiwi 2270）：按用户撤销全部会话。

覆盖任务 `02_01` 的 identity 侧切片——`POST /api/v1/identity/internal/sessions/revoke-user`
（`require_service("platform")`）：服务白名单、租户解析、参数透传与条数返回。
会话撤销服务本身的语义（refresh 吊销 / 标记清理 / 广播）由阶段六用例覆盖，本文件只校验端点接线。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import ClassVar

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

import bms_identity.api.internal_sessions as module
from bms_core.api.deps import get_tenant, get_token_verifier
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import AuthError
from bms_core.db.tenant import TenantContext
from bms_core.oauth.verify import VerifiedToken

API = "/api/v1/identity/internal/sessions/revoke-user"
TENANT_ID = "1001"
TENANT = TenantContext(code="demo", db_key="tenant_demo", name="演示租户", tenant_id=int(TENANT_ID))


class _StubVerifier:
    """测试替身：按令牌串返回服务身份（无签名）。"""

    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        """按令牌串返回固定身份声明。

        Args:
            token: 令牌串。
            audience: 期望受众（未使用）。

        Returns:
            VerifiedToken: 身份声明。

        Raises:
            AuthError: 未知令牌（20001 / 401）。
        """
        del audience
        if token == "platform":
            return VerifiedToken(subject="platform", service="platform", token_type="service", tenant_id=TENANT_ID)
        if token in {"identity", "gateway"}:
            return VerifiedToken(subject=token, service=token, token_type="service")
        raise AuthError("invalid")


class _RecordingSessionService:
    """测试替身：记录撤销调用并返回固定条数。"""

    calls: ClassVar[ConcurrentStableList[tuple[int, str, str]]] = ConcurrentStableList()

    def __init__(self, **kwargs: object) -> None:
        """初始化（忽略构造参数）。

        Args:
            **kwargs: 真实服务的构造参数（会话 / 工作单元 / 安全原语等）。
        """
        del kwargs

    async def revoke_user_sessions(self, user_id: int, *, tenant: str | None, reason: str) -> ConcurrentStableList[str]:
        """记录调用并返回两个会话 id。

        Args:
            user_id: 用户 ID。
            tenant: 租户主键。
            reason: 撤销原因。

        Returns:
            ConcurrentStableList[str]: 被撤销的会话 id。
        """
        _RecordingSessionService.calls.add((user_id, str(tenant), reason))
        return ConcurrentStableList(["s-1", "s-2"])


@asynccontextmanager
async def _fake_scope(*args: object, **kwargs: object) -> AsyncGenerator[object]:
    """测试替身：跳过真实库会话。

    Args:
        *args: 位置参数（忽略）。
        **kwargs: 关键字参数（忽略）。

    Yields:
        object: 空会话占位。
    """
    del args, kwargs
    yield None


@pytest.fixture(autouse=True)
def patch_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """替换端点内构造的服务与库会话（只测端点接线）。

    Args:
        monkeypatch: pytest 环境变量覆盖夹具。
    """
    _RecordingSessionService.calls = ConcurrentStableList()
    monkeypatch.setattr(module, "SessionService", _RecordingSessionService)
    monkeypatch.setattr(module, "session_scope", _fake_scope)


@pytest.mark.kiwi_id(2270)
async def test_revoke_user_sessions_requires_platform_service(client: AsyncClient, service_app: FastAPI) -> None:
    """鉴权：仅放行 `sub=platform` 服务票据；其他服务 / 无票据一律 401。"""
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    service_app.dependency_overrides[get_tenant] = lambda: TENANT

    payload = {"user_id": 42, "reason": "user_deleted"}
    for token in ("identity", "gateway", "bogus"):
        denied = await client.post(API, json=payload, headers={"Authorization": f"Bearer {token}"})
        assert denied.status_code == 401, token

    anonymous = await client.post(API, json=payload)
    assert anonymous.status_code == 401

    ok = await client.post(API, json=payload, headers={"Authorization": "Bearer platform"})
    assert ok.status_code == 200
    assert ok.json()["data"] == {"revoked": 2}
    assert list(_RecordingSessionService.calls) == [(42, TENANT_ID, "user_deleted")]


@pytest.mark.kiwi_id(2270)
async def test_revoke_user_sessions_rejects_invalid_reason(client: AsyncClient, service_app: FastAPI) -> None:
    """入参：`reason` 缺失 / 超长按参数校验错误拒绝（10001），不触发撤销。"""
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    service_app.dependency_overrides[get_tenant] = lambda: TENANT

    invalid = await client.post(API, json={"user_id": 42}, headers={"Authorization": "Bearer platform"})
    assert invalid.json()["code"] == 10001
    assert list(_RecordingSessionService.calls) == []
