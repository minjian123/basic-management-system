"""SSO 身份绑定查看端点测试（Kiwi 2198）：按本地用户反查平台库映射。

单库叠加口径（04-6-2）：本地用户主键按用例命名空间派生，查询与断言只认本用例的行
（本文件不依赖 `sso` 装配套件：绑定查看只需登录态，不覆盖会话存储）。
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.db.registry import PLATFORM_DB_KEY
from bms_core.db.session import session_scope
from bms_core.models.identity.user_identity import SysUserIdentity
from bms_core.testing.namespace import Namespace

from .helpers import TENANT, TENANT_HEADERS, TENANT_ID


def _subject(ns: Namespace) -> int:
    """本用例的本地用户主键。

    Args:
        ns: 用例命名空间。

    Returns:
        int: 用户主键。
    """
    return int(ns.prefix[2:], 16) * 100


async def _seed(app: FastAPI, *, user_id: int, idp_key: str) -> None:
    """播种平台库身份映射。

    Args:
        app: 应用实例。
        user_id: 本地用户主键。
        idp_key: 身份源标识。
    """
    async with session_scope(
        app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=app.state.session_factory
    ) as session:
        session.add(
            SysUserIdentity(
                idp_key=f"{TENANT_ID}:{idp_key}",
                external_id="sub-1",
                tenant_id=int(TENANT_ID),
                user_id=user_id,
            )
        )
        await session.commit()


@pytest.mark.kiwi_id(2198)
async def test_list_identities_returns_bindings(client: AsyncClient, service_app: FastAPI, ns: Namespace) -> None:
    """命中：返回该用户全部绑定（含映射键 / 外部主体 / 租户）。"""
    subject = _subject(ns)
    await _seed(service_app, user_id=subject, idp_key=ns.code("keycloak"))
    response = await client.get(f"/api/v1/users/{subject}/identities", headers=TENANT_HEADERS)
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert items == [{"idp_key": f"{TENANT_ID}:{ns.code('keycloak')}", "external_id": "sub-1", "tenant_id": TENANT_ID}]


@pytest.mark.kiwi_id(2198)
async def test_list_identities_empty_and_requires_auth(
    client: AsyncClient, service_app: FastAPI, ns: Namespace
) -> None:
    """无绑定返回空列表；缺登录态 401。"""
    api = f"/api/v1/users/{_subject(ns)}/identities"
    empty = await client.get(api, headers=TENANT_HEADERS)
    assert empty.status_code == 200 and empty.json()["data"]["items"] == []

    async with AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as anonymous:
        denied = await anonymous.get(api, headers={"X-Tenant-ID": TENANT})
    assert denied.status_code == 401
