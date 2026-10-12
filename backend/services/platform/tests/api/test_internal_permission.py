"""平台内部权限失效端点测试（`02_04`）：服务 JWT 白名单鉴权 + 版本递增。

覆盖 `POST /api/v1/platform/internal/permissions/invalidate`（`require_service("org")`）：
仅放行 `sub=org` 服务票据；`user_ids` 非空 / 为空两条入参路径均返回递增后的版本号。
"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.core.exceptions import AuthError
from bms_core.oauth.verify import VerifiedToken, get_token_verifier

API = "/api/v1/platform/internal/permissions/invalidate"


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
            AuthError: 未知令牌（20001/401）。
        """
        del audience
        if token == "org":
            return VerifiedToken(subject="org", service="org", token_type="service")
        if token == "gateway":
            return VerifiedToken(subject="gateway", service="gateway", token_type="service")
        raise AuthError("invalid")


@pytest.mark.kiwi_id(2269)
async def test_invalidate_endpoint_requires_org_service(client: AsyncClient, service_app: FastAPI) -> None:
    """端点：仅放行 `sub=org` 服务票据；网关 / 未知 / 无票据一律拒（401）。"""
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()

    ok = await client.post(API, json={}, headers={"Authorization": "Bearer org"})
    assert ok.status_code == 200
    assert ok.json()["data"]["version"] == 1

    for token in ("gateway", "bogus"):
        denied = await client.post(API, json={}, headers={"Authorization": f"Bearer {token}"})
        assert denied.status_code == 401

    anonymous = await client.post(API, json={})
    assert anonymous.status_code == 401


@pytest.mark.kiwi_id(2269)
async def test_invalidate_endpoint_scopes_users(client: AsyncClient, service_app: FastAPI) -> None:
    """端点：`user_ids` 非空按用户清理旧版本键、为空只做全租户版本 +1（均返回递增版本）。"""
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()

    scoped = await client.post(API, json={"user_ids": [7, 8]}, headers={"Authorization": "Bearer org"})
    assert scoped.status_code == 200
    assert scoped.json()["data"]["version"] == 1

    whole_tenant = await client.post(API, json={}, headers={"Authorization": "Bearer org"})
    assert whole_tenant.json()["data"]["version"] == 2
