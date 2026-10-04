"""用户↔租户可达关系测试（11_01）：本地数据源 / 服务 / 仓储 + 内部读写端点。

覆盖：`ensure` 幂等与复活、`revoke` / `revoke_all` 回收、`list_targets` 有效与含 `disabled`、
来源取值校验、目标租户不存在、内部端点鉴权与资源式读写（GET / POST / DELETE）。
"""

from typing import cast

import pytest
from fastapi import FastAPI, Request
from httpx import AsyncClient

from bms_core.api.deps import get_tenant_membership_store
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import AuthError, ParamError, TenantNotFoundError
from bms_core.db.registry import PLATFORM_DB_KEY, EngineRegistry
from bms_core.db.session import session_scope
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.oauth.verify import VerifiedToken, get_token_verifier
from bms_core.tenant.membership import LOCAL_TENANT_MEMBERSHIP_STORE
from bms_tenant.repositories.tenant_membership import TenantMembershipRepository
from bms_tenant.services.membership import TenantMembershipService
from bms_tenant.sources.membership import LocalTenantMembershipStore
from tests_support.tenant_sql import membership_status_source

API = "/api/v1/tenant/internal/memberships"
DEMO_TENANT_ID = 1001
ACME_TENANT_ID = 2002
_UNKNOWN_TENANT_ID = 9999

_USER = 9301
_OTHER_USER = 9302

_RECON_USER = 9401
"""对账巡检用例用户（专用，避免其他用例状态耦合）。"""

_RECON_OTHER = 9402
"""对账巡检用例另一用户（带额外目标租户关系）。"""

_RECON_ABSENT = 9499
"""对账巡检用例「清单中无自有关系」用户。"""


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
        if token in ("org", "identity"):
            return VerifiedToken(subject=token, service=token, token_type="service")
        if token == "gateway":
            return VerifiedToken(subject="gateway", service="gateway", token_type="service")
        raise AuthError("invalid")


def _store(app: FastAPI) -> LocalTenantMembershipStore:
    """取应用装配的关系数据源（租户服务为 `local` 实现）。

    Args:
        app: 应用实例。

    Returns:
        LocalTenantMembershipStore: 本地关系数据源。
    """
    store = cast("LocalTenantMembershipStore", app.state.tenant_membership)
    assert isinstance(store, LocalTenantMembershipStore)
    return store


@pytest.mark.kiwi_id(891)
async def test_local_store_ensure_idempotent_and_reactivate(service_app: FastAPI) -> None:
    """本地数据源：ensure 幂等建（首次落来源）、重复幂等、回收后可复活。"""
    store = _store(service_app)

    created = await store.ensure(
        tenant_id=DEMO_TENANT_ID, user_id=_USER, target_tenant_id=ACME_TENANT_ID, source="admin_create"
    )
    assert created.tenant_id == ACME_TENANT_ID
    assert created.code == "acme"
    assert created.status == "active"

    again = await store.ensure(
        tenant_id=DEMO_TENANT_ID, user_id=_USER, target_tenant_id=ACME_TENANT_ID, source="import"
    )
    assert again.status == "active"
    targets = await store.list_targets(tenant_id=DEMO_TENANT_ID, user_id=_USER)
    assert [item.tenant_id for item in targets] == [ACME_TENANT_ID]

    await store.revoke(tenant_id=DEMO_TENANT_ID, user_id=_USER, target_tenant_id=ACME_TENANT_ID)
    await store.revoke(tenant_id=DEMO_TENANT_ID, user_id=_USER, target_tenant_id=ACME_TENANT_ID)  # 幂等
    assert await store.list_targets(tenant_id=DEMO_TENANT_ID, user_id=_USER) == []
    all_rows = await store.list_targets(tenant_id=DEMO_TENANT_ID, user_id=_USER, include_disabled=True)
    assert [item.status for item in all_rows] == ["disabled"]

    revived = await store.ensure(
        tenant_id=DEMO_TENANT_ID, user_id=_USER, target_tenant_id=ACME_TENANT_ID, source="import"
    )
    assert revived.status == "active"
    rows = await store.list_targets(tenant_id=DEMO_TENANT_ID, user_id=_USER)
    assert [item.tenant_id for item in rows] == [ACME_TENANT_ID]


@pytest.mark.kiwi_id(891)
async def test_local_store_revoke_all_and_source_validation(service_app: FastAPI) -> None:
    """本地数据源：回收全部（幂等）+ 来源取值校验 + 目标租户不存在。"""
    store = _store(service_app)

    await store.ensure(tenant_id=DEMO_TENANT_ID, user_id=_OTHER_USER, target_tenant_id=DEMO_TENANT_ID, source="sso_jit")
    await store.ensure(tenant_id=DEMO_TENANT_ID, user_id=_OTHER_USER, target_tenant_id=ACME_TENANT_ID, source="sso_jit")
    await store.revoke_all(tenant_id=DEMO_TENANT_ID, user_id=_OTHER_USER)
    await store.revoke_all(tenant_id=DEMO_TENANT_ID, user_id=_OTHER_USER)  # 幂等
    assert await store.list_targets(tenant_id=DEMO_TENANT_ID, user_id=_OTHER_USER) == []

    with pytest.raises(ParamError):
        await store.ensure(
            tenant_id=DEMO_TENANT_ID, user_id=_OTHER_USER, target_tenant_id=DEMO_TENANT_ID, source="bogus"
        )

    with pytest.raises(TenantNotFoundError):
        await store.ensure(
            tenant_id=DEMO_TENANT_ID,
            user_id=_OTHER_USER,
            target_tenant_id=_UNKNOWN_TENANT_ID,
            source="admin_create",
        )


@pytest.mark.kiwi_id(891)
async def test_reconcile_reports_missing_and_dangling(service_app: FastAPI) -> None:
    """对账巡检：缺行（清单中无自有关系）/ 悬空行（关系表有行但不在清单）均可检出；无差异为空。"""
    registry = cast("EngineRegistry", service_app.state.engine_registry)
    async with session_scope(registry, db_key=PLATFORM_DB_KEY) as session:
        service = TenantMembershipService(TenantMembershipRepository(session), DbUnitOfWork(session))
        for user in (_RECON_USER, _RECON_OTHER):
            await service.ensure(
                tenant_id=DEMO_TENANT_ID, user_id=user, target_tenant_id=DEMO_TENANT_ID, source="sso_jit"
            )
        await service.ensure(
            tenant_id=DEMO_TENANT_ID, user_id=_RECON_OTHER, target_tenant_id=ACME_TENANT_ID, source="import"
        )

        clean = await service.reconcile(
            tenant_id=DEMO_TENANT_ID, user_ids=ConcurrentStableList([_RECON_USER, _RECON_OTHER])
        )
        assert clean.missing == []

        report = await service.reconcile(
            tenant_id=DEMO_TENANT_ID, user_ids=ConcurrentStableList([_RECON_USER, _RECON_ABSENT])
        )
        assert _RECON_ABSENT in report.missing
        assert _RECON_OTHER in report.dangling


@pytest.mark.kiwi_id(891)
async def test_membership_store_dependency_export(service_app: FastAPI) -> None:
    """依赖出口与登记名：应用装配件经 `get_tenant_membership_store` 可取，登记名 `local`。"""
    request = cast("Request", _RequestStub(service_app))
    assert isinstance(get_tenant_membership_store(request), LocalTenantMembershipStore)
    assert LOCAL_TENANT_MEMBERSHIP_STORE == "local"


@pytest.mark.kiwi_id(891)
async def test_internal_endpoints_read_write(client: AsyncClient, service_app: FastAPI, platform_db_url: str) -> None:
    """内部端点：POST 建关系 → GET 读 → DELETE 回收（含 include_disabled 与全部回收）。"""
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    headers = {"Authorization": "Bearer org"}

    created = await client.post(
        API,
        json={
            "owner_tenant_id": DEMO_TENANT_ID,
            "user_id": _USER,
            "target_tenant_id": ACME_TENANT_ID,
            "source": "admin_create",
        },
        headers=headers,
    )
    assert created.status_code == 200
    data = created.json()["data"]
    assert [item["code"] for item in data["targets"]] == ["acme"]
    assert (
        await membership_status_source(
            platform_db_url, tenant_id=DEMO_TENANT_ID, user_id=_USER, target_tenant_id=ACME_TENANT_ID
        )
        == "active|admin_create"
    )

    listed = await client.get(
        API,
        params={"owner_tenant_id": DEMO_TENANT_ID, "user_id": _USER},
        headers=headers,
    )
    assert listed.status_code == 200
    assert [item["tenant_id"] for item in listed.json()["data"]["targets"]] == [str(ACME_TENANT_ID)]

    revoked = await client.delete(
        API,
        params={"owner_tenant_id": DEMO_TENANT_ID, "user_id": _USER, "target_tenant_id": ACME_TENANT_ID},
        headers=headers,
    )
    assert revoked.status_code == 200
    assert revoked.json()["data"]["targets"] == []

    with_disabled = await client.get(
        API,
        params={"owner_tenant_id": DEMO_TENANT_ID, "user_id": _USER, "include_disabled": True},
        headers=headers,
    )
    assert [item["status"] for item in with_disabled.json()["data"]["targets"]] == ["disabled"]

    revoked_all = await client.delete(
        API, params={"owner_tenant_id": DEMO_TENANT_ID, "user_id": _USER}, headers=headers
    )
    assert revoked_all.status_code == 200
    assert revoked_all.json()["data"]["targets"] == []


@pytest.mark.kiwi_id(891)
async def test_internal_endpoint_auth_and_validation(client: AsyncClient, service_app: FastAPI) -> None:
    """内部端点：鉴权白名单（org / identity）、网关票据与匿名拒、参数校验与来源校验。"""
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()

    identity_headers = {"Authorization": "Bearer identity"}
    ok = await client.get(
        API, params={"owner_tenant_id": DEMO_TENANT_ID, "user_id": _OTHER_USER}, headers=identity_headers
    )
    assert ok.status_code == 200

    gateway = await client.get(
        API,
        params={"owner_tenant_id": DEMO_TENANT_ID, "user_id": _OTHER_USER},
        headers={"Authorization": "Bearer gateway"},
    )
    assert gateway.status_code == 401

    anonymous = await client.get(API, params={"owner_tenant_id": DEMO_TENANT_ID, "user_id": _OTHER_USER})
    assert anonymous.status_code == 401

    # 缺参：统一校验处理器收口为参数错误（10001 / HTTP 200，`BizError` 语义）
    missing = await client.get(API, params={"owner_tenant_id": DEMO_TENANT_ID}, headers=identity_headers)
    assert missing.json()["code"] == 10001

    bad_source = await client.post(
        API,
        json={
            "owner_tenant_id": DEMO_TENANT_ID,
            "user_id": _OTHER_USER,
            "target_tenant_id": DEMO_TENANT_ID,
            "source": "bogus",
        },
        headers=identity_headers,
    )
    assert bad_source.json()["code"] == 10001

    bad_target = await client.post(
        API,
        json={
            "owner_tenant_id": DEMO_TENANT_ID,
            "user_id": _OTHER_USER,
            "target_tenant_id": _UNKNOWN_TENANT_ID,
            "source": "admin_create",
        },
        headers=identity_headers,
    )
    assert bad_target.status_code == 404
    assert bad_target.json()["code"] == 80001


class _RequestStub:
    """请求替身：仅提供依赖出口所需的应用 state。"""

    def __init__(self, app: FastAPI) -> None:
        """初始化。

        Args:
            app: 应用实例。
        """
        self.app = app
