"""CAS 兼容适配端点测试（Kiwi 2199）：端到端登录（含 JIT）+ 失败分支 + service 一致性。

以 MockIdP 夹具的 `CasMock`（`httpx.MockTransport`）模拟 CAS `serviceValidate`；授权跳转不发出站请求。
"""

from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableSet
from bms_identity.models.user_identity import SysUserIdentity

from .conftest import CAS_REDIRECT_URI, SsoHarness
from .helpers import CAS_IDP_KEY, TENANT, TENANT_HEADERS, TENANT_ID

CALLBACK = f"/api/v1/auth/sso/{CAS_IDP_KEY}/callback"


def _expected_service(state: str) -> str:
    """登录 / 校验一致的 service 串。

    Args:
        state: 流程状态。

    Returns:
        str: `{redirect_uri}?state={state}`。
    """
    return f"{CAS_REDIRECT_URI}?state={state}"


async def _start_cas_flow(client: AsyncClient, sso: SsoHarness) -> str:
    """发起 CAS 授权跳转并返回 state（state 嵌于登录 URL 的 `service` 查询串内）。

    Args:
        client: 测试客户端。
        sso: 装配套件。

    Returns:
        str: 流程状态。
    """
    response = await client.get(f"/api/v1/auth/sso/{CAS_IDP_KEY}/authorize", headers=TENANT_HEADERS)
    assert response.status_code == 302
    service = parse_qs(urlparse(response.headers["location"]).query)["service"][0]
    return parse_qs(urlparse(service).query)["state"][0]


@pytest.mark.kiwi_id(2199)
async def test_cas_end_to_end_jit_creates_user_and_session(client: AsyncClient, sso: SsoHarness) -> None:
    """CAS 端到端：授权跳转 service 含 state → 票据校验 → JIT 建号 + 映射 + 会话 + 302/JSON。"""
    await sso.seed_provider(idp_key=CAS_IDP_KEY, type="cas", config=sso.cas_provider_config(jit_enabled=True))

    state = await _start_cas_flow(client, sso)
    sso.cas.allowed_services = ConcurrentStableSet({_expected_service(state)})

    response = await client.get(f"{CALLBACK}?state={state}&ticket=ST-ok", headers=TENANT_HEADERS)
    assert response.status_code == 200 and response.json()["code"] == 0
    assert response.json()["data"]["tenant"] == TENANT

    # 校验 service 与登录时完全一致（同一 state）
    assert sso.cas.services == [_expected_service(state)]
    assert sso.cas.tickets == ["ST-ok"]

    # 身份映射写入平台库（映射键 {tenant}:{provider_key}；主体取 CAS principal）
    async with sso.platform_scope() as session:
        rows = (await session.execute(select(SysUserIdentity))).scalars().all()
    assert [(row.idp_key, row.external_id, row.tenant_id) for row in rows] == [
        (f"{TENANT_ID}:{CAS_IDP_KEY}", "cas-alice", int(TENANT_ID))
    ]

    # 首登发一次 JIT 事件
    assert [event.event_type for event in sso.outbox.events] == ["identity.user.jit_created"]


@pytest.mark.kiwi_id(2199)
async def test_cas_existing_mapping_logs_in_without_jit(client: AsyncClient, sso: SsoHarness) -> None:
    """已绑定身份：命中映射直接登录，不建号、不发事件（复用 02_01 路径）。"""
    sso.platform_client.set_user(1001, username="cas-alice")
    await sso.seed_provider(idp_key=CAS_IDP_KEY, type="cas")
    await sso.seed_mapping(idp_key=CAS_IDP_KEY, external_id="cas-alice", user_id=1001)

    state = await _start_cas_flow(client, sso)
    sso.cas.allowed_services = ConcurrentStableSet({_expected_service(state)})
    response = await client.get(f"{CALLBACK}?state={state}&ticket=ST-ok", headers=TENANT_HEADERS)

    assert response.status_code == 200 and response.json()["data"]["tenant"] == TENANT
    assert sso.outbox.events == []


@pytest.mark.kiwi_id(2199)
async def test_cas_invalid_ticket_and_service_rejected(client: AsyncClient, sso: SsoHarness) -> None:
    """票据无效 / 服务未注册：CAS `authenticationFailure` 翻译为 20052。"""
    await sso.seed_provider(idp_key=CAS_IDP_KEY, type="cas")

    state = await _start_cas_flow(client, sso)
    sso.cas.failure_code = "INVALID_TICKET"
    invalid = await client.get(f"{CALLBACK}?state={state}&ticket=ST-bad", headers=TENANT_HEADERS)
    assert invalid.status_code == 400 and invalid.json()["code"] == 20052

    state = await _start_cas_flow(client, sso)
    sso.cas.failure_code = None
    sso.cas.allowed_services = ConcurrentStableSet({"http://other/callback"})  # service 不匹配 → INVALID_SERVICE
    mismatched = await client.get(f"{CALLBACK}?state={state}&ticket=ST-ok", headers=TENANT_HEADERS)
    assert mismatched.status_code == 400 and mismatched.json()["code"] == 20052


@pytest.mark.kiwi_id(2199)
async def test_cas_unavailable_and_unmatched(client: AsyncClient, sso: SsoHarness) -> None:
    """IdP 不可达 → 20053；映射未命中且 JIT 关闭 → 20054。"""
    await sso.seed_provider(idp_key=CAS_IDP_KEY, type="cas")

    state = await _start_cas_flow(client, sso)
    sso.cas.status = 500
    unavailable = await client.get(f"{CALLBACK}?state={state}&ticket=ST-ok", headers=TENANT_HEADERS)
    assert unavailable.status_code == 503 and unavailable.json()["code"] == 20053

    state = await _start_cas_flow(client, sso)
    sso.cas.status = 200
    unmatched = await client.get(f"{CALLBACK}?state={state}&ticket=ST-ok", headers=TENANT_HEADERS)
    assert unmatched.status_code == 403 and unmatched.json()["code"] == 20054
