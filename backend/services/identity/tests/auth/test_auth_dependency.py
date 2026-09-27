"""登录态依赖端到端（Kiwi 2196）：受保护接口无 / 无效令牌 401、有效令牌 200、踢出后即时 401。

以 identity 会话端点 `/api/v1/sessions`（挂 `require_auth`）为受保护受测面；会话存储用 `wire_login`
的内存替身，令牌用测试夹具真实签名（`aud=api`）。
"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests_support.auth import issue_access_token

from .session_helpers import API_SESSIONS, TENANT_HEADERS, login, wire_login

pytestmark = pytest.mark.kiwi_id(2196)


async def test_protected_route_requires_valid_login(client: AsyncClient) -> None:
    """有效登录令牌放行 200；无效令牌 401（20001）。"""
    ok = await client.get(API_SESSIONS, headers=TENANT_HEADERS)
    assert ok.status_code == 200

    invalid = await client.get(API_SESSIONS, headers={**TENANT_HEADERS, "Authorization": "Bearer not-a-token"})
    assert invalid.status_code == 401
    assert invalid.json()["code"] == 20001


async def test_kicked_session_rejected_on_next_request(client: AsyncClient, service_app: FastAPI) -> None:
    """踢出即时性：被踢会话的 access 在下一请求即 401（20012，不依赖广播 / 自然过期）。"""
    issuer, _store, _recorder = await wire_login(service_app)
    assert (await login(client, headers=TENANT_HEADERS)).status_code == 200
    session_id = issuer.specs[-1].session_id

    kicked = await client.post(f"{API_SESSIONS}/{session_id}/kick", headers=TENANT_HEADERS)
    assert kicked.status_code == 200

    token = issue_access_token(session_id=session_id, tenant="demo")
    after = await client.get(API_SESSIONS, headers={**TENANT_HEADERS, "Authorization": f"Bearer {token}"})
    assert after.status_code == 401
    assert after.json()["code"] == 20012
