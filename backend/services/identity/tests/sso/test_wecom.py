"""企业微信免登适配端点测试（Kiwi 2200）：authorize-url 契约 + 端到端（含 JIT）+ 失败分支。

以 `WecomMock`（`httpx.MockTransport`）模拟 `gettoken` / `getuserinfo`；授权跳转不发出站请求。

单库叠加口径（04-6-2）：企微提供方标识按用例命名空间派生（`sso.wecom_key`），映射断言按 `idp_key` 过滤。
"""

from __future__ import annotations

from typing import cast
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.models.identity.user_identity import SysUserIdentity

from .conftest import SsoHarness
from .helpers import TENANT, TENANT_HEADERS, TENANT_ID, WECOM_AGENT_ID, WECOM_CORP_ID


def _urls(sso: SsoHarness) -> tuple[str, str, str]:
    """本用例企微三端点地址。

    Args:
        sso: 装配套件。

    Returns:
        tuple[str, str, str]: (authorize-url, authorize, callback)。
    """
    base = f"/api/v1/auth/sso/{sso.wecom_key}"
    return f"{base}/authorize-url", f"{base}/authorize", f"{base}/callback"


async def _start(client: AsyncClient, sso: SsoHarness) -> str:
    """发起 authorize-url 并返回流程状态。

    Args:
        client: 测试客户端。
        sso: 装配套件。

    Returns:
        str: 流程状态。
    """
    authorize_url, _, _ = _urls(sso)
    response = await client.get(authorize_url, headers=TENANT_HEADERS)
    assert response.status_code == 200 and response.json()["code"] == 0
    return cast("str", response.json()["data"]["state"])


@pytest.mark.kiwi_id(2200)
async def test_wecom_authorize_url_and_302_and_end_to_end(client: AsyncClient, sso: SsoHarness) -> None:
    """authorize-url 契约 + 302 回归 + 端到端：code 换身份 → JIT 建号 + 映射 + 会话。"""
    await sso.seed_provider(
        idp_key=sso.wecom_key, type="wecom", config=sso.wecom_provider_config(jit_enabled=True)
    )
    authorize_url, authorize, callback_url = _urls(sso)

    response = await client.get(authorize_url, headers=TENANT_HEADERS)
    assert response.status_code == 200 and response.json()["code"] == 0
    data = response.json()["data"]
    assert data["expires_in"] > 0
    query = parse_qs(urlparse(cast("str", data["authorize_url"])).query)
    assert query["appid"] == [WECOM_CORP_ID]
    assert query["agentid"] == [WECOM_AGENT_ID]
    assert query["state"] == [data["state"]]
    state = cast("str", data["state"])

    redirect = await client.get(authorize, headers=TENANT_HEADERS)
    assert redirect.status_code == 302
    assert "login.work.weixin.qq.com" in redirect.headers["location"]

    callback = await client.get(f"{callback_url}?state={state}&code=code-1", headers=TENANT_HEADERS)
    assert callback.status_code == 200 and callback.json()["data"]["tenant"] == TENANT

    async with sso.platform_scope() as session:
        rows = (
            (
                await session.execute(
                    select(SysUserIdentity).where(SysUserIdentity.idp_key == f"{TENANT_ID}:{sso.wecom_key}")
                )
            )
            .scalars()
            .all()
        )
    assert [(row.idp_key, row.external_id, row.tenant_id) for row in rows] == [
        (f"{TENANT_ID}:{sso.wecom_key}", "wecom-alice", int(TENANT_ID))
    ]
    assert [event.event_type for event in sso.outbox.events] == ["identity.user.jit_created"]


@pytest.mark.kiwi_id(2200)
async def test_wecom_config_missing_returns_20057(client: AsyncClient, sso: SsoHarness) -> None:
    """凭据缺失：行配置无 corp_id / agent_id / secret_ref → 20057（入口不可用、提示明确）。"""
    authorize_url, _, _ = _urls(sso)
    await sso.seed_provider(
        idp_key=sso.wecom_key,
        type="wecom",
        config=ConcurrentStableDict({"redirect_uri": sso.wecom_redirect_uri}),
    )

    response = await client.get(authorize_url, headers=TENANT_HEADERS)
    assert response.status_code == 503 and response.json()["code"] == 20057


@pytest.mark.kiwi_id(2200)
async def test_wecom_failure_branches(client: AsyncClient, sso: SsoHarness) -> None:
    """失败分支：凭据类 gettoken → 20057；不可达 → 20059；授权失败 → 20058；未匹配 → 20054。"""
    await sso.seed_provider(idp_key=sso.wecom_key, type="wecom", config=sso.wecom_provider_config())
    _, _, callback_url = _urls(sso)

    sso.wecom.token_errcode = 40001
    state = await _start(client, sso)
    credential = await client.get(f"{callback_url}?state={state}&code=c", headers=TENANT_HEADERS)
    assert credential.status_code == 503 and credential.json()["code"] == 20057

    sso.wecom.token_errcode = 0
    sso.wecom.token_status = 500
    state = await _start(client, sso)
    unavailable = await client.get(f"{callback_url}?state={state}&code=c", headers=TENANT_HEADERS)
    assert unavailable.status_code == 503 and unavailable.json()["code"] == 20059

    sso.wecom.token_status = 200
    sso.wecom.user_errcode = 40029
    state = await _start(client, sso)
    rejected = await client.get(f"{callback_url}?state={state}&code=bad", headers=TENANT_HEADERS)
    assert rejected.status_code == 400 and rejected.json()["code"] == 20058

    sso.wecom.user_errcode = 0
    state = await _start(client, sso)
    unmatched = await client.get(f"{callback_url}?state={state}&code=c", headers=TENANT_HEADERS)
    assert unmatched.status_code == 403 and unmatched.json()["code"] == 20054
