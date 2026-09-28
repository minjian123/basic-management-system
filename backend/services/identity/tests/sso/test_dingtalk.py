"""钉钉免登适配端点测试（Kiwi 2201）：authorize-url 契约 + 端到端（含 JIT）+ 失败分支。

以 `DingtalkMock`（`httpx.MockTransport`）模拟 `userAccessToken` / `contact/users/me`；授权跳转不发出站请求。
"""

from __future__ import annotations

from typing import cast
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from bms_identity.models.user_identity import SysUserIdentity

from .conftest import SsoHarness
from .helpers import DINGTALK_CLIENT_ID, DINGTALK_IDP_KEY, TENANT, TENANT_HEADERS

AUTHORIZE_URL = f"/api/v1/auth/sso/{DINGTALK_IDP_KEY}/authorize-url"
CALLBACK = f"/api/v1/auth/sso/{DINGTALK_IDP_KEY}/callback"


async def _start(client: AsyncClient) -> str:
    """发起 authorize-url 并返回流程状态。

    Args:
        client: 测试客户端。

    Returns:
        str: 流程状态。
    """
    response = await client.get(AUTHORIZE_URL, headers=TENANT_HEADERS)
    assert response.status_code == 200 and response.json()["code"] == 0
    return cast("str", response.json()["data"]["state"])


@pytest.mark.kiwi_id(2201)
async def test_dingtalk_authorize_url_and_end_to_end(client: AsyncClient, sso: SsoHarness) -> None:
    """authorize-url 契约 + providers 含 dingtalk + 端到端：新版 OAuth2 换令牌取信息 → JIT + 会话。"""
    await sso.seed_provider(
        idp_key=DINGTALK_IDP_KEY, type="dingtalk", config=sso.dingtalk_provider_config(jit_enabled=True)
    )

    providers = await client.get("/api/v1/auth/sso/providers", headers=TENANT_HEADERS)
    assert DINGTALK_IDP_KEY in [item["idp_key"] for item in providers.json()["data"]["items"]]
    assert "dingtalk" in [item["type"] for item in providers.json()["data"]["items"]]

    response = await client.get(AUTHORIZE_URL, headers=TENANT_HEADERS)
    assert response.status_code == 200 and response.json()["code"] == 0
    data = response.json()["data"]
    assert data["expires_in"] > 0
    query = parse_qs(urlparse(cast("str", data["authorize_url"])).query)
    assert query["client_id"] == [DINGTALK_CLIENT_ID]
    assert query["state"] == [data["state"]]

    callback = await client.get(f"{CALLBACK}?state={data['state']}&code=code-1", headers=TENANT_HEADERS)
    assert callback.status_code == 200 and callback.json()["data"]["tenant_code"] == TENANT

    async with sso.platform_scope() as session:
        rows = (await session.execute(select(SysUserIdentity))).scalars().all()
    assert [(row.idp_key, row.external_id, row.tenant_id) for row in rows] == [
        (f"{TENANT}:{DINGTALK_IDP_KEY}", "dingtalk-union", TENANT)
    ]
    assert [event.event_type for event in sso.outbox.events] == ["identity.user.jit_created"]


@pytest.mark.kiwi_id(2201)
async def test_dingtalk_failure_branches(client: AsyncClient, sso: SsoHarness) -> None:
    """失败分支：换码 4xx → 20061；5xx（换码 / 用户信息）→ 20062；未匹配 → 20054。"""
    await sso.seed_provider(idp_key=DINGTALK_IDP_KEY, type="dingtalk", config=sso.dingtalk_provider_config())

    sso.dingtalk.token_status = 400
    state = await _start(client)
    rejected = await client.get(f"{CALLBACK}?state={state}&code=bad", headers=TENANT_HEADERS)
    assert rejected.status_code == 400 and rejected.json()["code"] == 20061

    sso.dingtalk.token_status = 503
    state = await _start(client)
    unavailable = await client.get(f"{CALLBACK}?state={state}&code=c", headers=TENANT_HEADERS)
    assert unavailable.status_code == 503 and unavailable.json()["code"] == 20062

    sso.dingtalk.token_status = 200
    sso.dingtalk.user_status = 500
    state = await _start(client)
    user_unavailable = await client.get(f"{CALLBACK}?state={state}&code=c", headers=TENANT_HEADERS)
    assert user_unavailable.status_code == 503 and user_unavailable.json()["code"] == 20062

    sso.dingtalk.user_status = 200
    state = await _start(client)
    unmatched = await client.get(f"{CALLBACK}?state={state}&code=c", headers=TENANT_HEADERS)
    assert unmatched.status_code == 403 and unmatched.json()["code"] == 20054
