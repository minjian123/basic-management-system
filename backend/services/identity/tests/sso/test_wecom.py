"""企业微信免登适配端点测试（Kiwi 2200）：authorize-url 契约 + 端到端（含 JIT）+ 失败分支。

以 `WecomMock`（`httpx.MockTransport`）模拟 `gettoken` / `getuserinfo`；授权跳转不发出站请求。
"""

from __future__ import annotations

from typing import cast
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict
from bms_identity.models.user_identity import SysUserIdentity

from .conftest import WECOM_REDIRECT_URI, SsoHarness
from .helpers import TENANT, TENANT_HEADERS, TENANT_ID, WECOM_AGENT_ID, WECOM_CORP_ID, WECOM_IDP_KEY

AUTHORIZE_URL = f"/api/v1/auth/sso/{WECOM_IDP_KEY}/authorize-url"
AUTHORIZE = f"/api/v1/auth/sso/{WECOM_IDP_KEY}/authorize"
CALLBACK = f"/api/v1/auth/sso/{WECOM_IDP_KEY}/callback"


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


@pytest.mark.kiwi_id(2200)
async def test_wecom_authorize_url_and_302_and_end_to_end(client: AsyncClient, sso: SsoHarness) -> None:
    """authorize-url 契约 + 302 回归 + 端到端：code 换身份 → JIT 建号 + 映射 + 会话。"""
    await sso.seed_provider(idp_key=WECOM_IDP_KEY, type="wecom", config=sso.wecom_provider_config(jit_enabled=True))

    response = await client.get(AUTHORIZE_URL, headers=TENANT_HEADERS)
    assert response.status_code == 200 and response.json()["code"] == 0
    data = response.json()["data"]
    assert data["expires_in"] > 0
    query = parse_qs(urlparse(cast("str", data["authorize_url"])).query)
    assert query["appid"] == [WECOM_CORP_ID]
    assert query["agentid"] == [WECOM_AGENT_ID]
    assert query["state"] == [data["state"]]
    state = cast("str", data["state"])

    redirect = await client.get(AUTHORIZE, headers=TENANT_HEADERS)
    assert redirect.status_code == 302
    assert "login.work.weixin.qq.com" in redirect.headers["location"]

    callback = await client.get(f"{CALLBACK}?state={state}&code=code-1", headers=TENANT_HEADERS)
    assert callback.status_code == 200 and callback.json()["data"]["tenant"] == TENANT

    async with sso.platform_scope() as session:
        rows = (await session.execute(select(SysUserIdentity))).scalars().all()
    assert [(row.idp_key, row.external_id, row.tenant_id) for row in rows] == [
        (f"{TENANT_ID}:{WECOM_IDP_KEY}", "wecom-alice", int(TENANT_ID))
    ]
    assert [event.event_type for event in sso.outbox.events] == ["identity.user.jit_created"]


@pytest.mark.kiwi_id(2200)
async def test_wecom_config_missing_returns_20057(client: AsyncClient, sso: SsoHarness) -> None:
    """凭据缺失：行配置无 corp_id / agent_id / secret_ref → 20057（入口不可用、提示明确）。"""
    await sso.seed_provider(
        idp_key=WECOM_IDP_KEY, type="wecom", config=ConcurrentStableDict({"redirect_uri": WECOM_REDIRECT_URI})
    )

    response = await client.get(AUTHORIZE_URL, headers=TENANT_HEADERS)
    assert response.status_code == 503 and response.json()["code"] == 20057


@pytest.mark.kiwi_id(2200)
async def test_wecom_failure_branches(client: AsyncClient, sso: SsoHarness) -> None:
    """失败分支：凭据类 gettoken → 20057；不可达 → 20059；授权失败 → 20058；未匹配 → 20054。"""
    await sso.seed_provider(idp_key=WECOM_IDP_KEY, type="wecom", config=sso.wecom_provider_config())

    sso.wecom.token_errcode = 40001
    state = await _start(client)
    credential = await client.get(f"{CALLBACK}?state={state}&code=c", headers=TENANT_HEADERS)
    assert credential.status_code == 503 and credential.json()["code"] == 20057

    sso.wecom.token_errcode = 0
    sso.wecom.token_status = 500
    state = await _start(client)
    unavailable = await client.get(f"{CALLBACK}?state={state}&code=c", headers=TENANT_HEADERS)
    assert unavailable.status_code == 503 and unavailable.json()["code"] == 20059

    sso.wecom.token_status = 200
    sso.wecom.user_errcode = 40029
    state = await _start(client)
    rejected = await client.get(f"{CALLBACK}?state={state}&code=bad", headers=TENANT_HEADERS)
    assert rejected.status_code == 400 and rejected.json()["code"] == 20058

    sso.wecom.user_errcode = 0
    state = await _start(client)
    unmatched = await client.get(f"{CALLBACK}?state={state}&code=c", headers=TENANT_HEADERS)
    assert unmatched.status_code == 403 and unmatched.json()["code"] == 20054
