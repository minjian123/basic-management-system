"""SSO 身份绑定查看端点测试（Kiwi 2198）：按本地用户反查平台库映射。"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.db.registry import PLATFORM_DB_KEY
from bms_core.db.session import session_scope
from bms_identity.models.user_identity import SysUserIdentity

from .helpers import IDP_KEY, TENANT, TENANT_HEADERS

API = "/api/v1/users/1001/identities"


async def _seed(app: FastAPI, *, user_id: int = 1001) -> None:
    """播种平台库身份映射。

    Args:
        app: 应用实例。
        user_id: 本地用户主键。
    """
    async with session_scope(
        app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=app.state.session_factory
    ) as session:
        session.add(
            SysUserIdentity(
                idp_key=f"{TENANT}:{IDP_KEY}",
                external_id="sub-1",
                tenant_id=TENANT,
                user_id=user_id,
            )
        )
        await session.commit()


@pytest.mark.kiwi_id(2198)
async def test_list_identities_returns_bindings(client: AsyncClient, service_app: FastAPI) -> None:
    """命中：返回该用户全部绑定（含映射键 / 外部主体 / 租户）。"""
    await _seed(service_app)
    response = await client.get(API, headers=TENANT_HEADERS)
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert items == [{"idp_key": f"{TENANT}:{IDP_KEY}", "external_id": "sub-1", "tenant_id": TENANT}]


@pytest.mark.kiwi_id(2198)
async def test_list_identities_empty_and_requires_auth(client: AsyncClient, service_app: FastAPI) -> None:
    """无绑定返回空列表；缺登录态 401。"""
    empty = await client.get(API, headers=TENANT_HEADERS)
    assert empty.status_code == 200 and empty.json()["data"]["items"] == []

    async with AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as anonymous:
        denied = await anonymous.get(API, headers={"X-Tenant-ID": TENANT})
    assert denied.status_code == 401
