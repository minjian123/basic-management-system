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
from bms_core.testing.namespace import Namespace
from bms_tenant.domains.tenant.repositories.tenant_membership import TenantMembershipRepository
from bms_tenant.domains.tenant.services.membership import TenantMembershipService
from bms_tenant.domains.tenant.sources.membership import LocalTenantMembershipStore
from tests_support.tenant_sql import membership_status_source

API = "/api/v1/tenant/internal/memberships"
DEMO_TENANT_ID = 1001
ACME_TENANT_ID = 2002


def _uid(ns: Namespace, salt: str) -> int:
    """按命名空间派生用户主键（同文件多用例、多 worker 之间互不干扰）。

    单库叠加下同文件多个用例可能被分到不同 worker 并行执行，共用固定用户会让
    「回收后清单为空」「对账缺行」这类断言互相污染。

    Args:
        ns: 用例命名空间。
        salt: 同用例内的主体变体。

    Returns:
        int: 用户主键。
    """
    return int(ns.prefix[2:], 16) * 10 + sum(ord(char) for char in salt)


def _missing_tenant(ns: Namespace) -> int:
    """本用例专属的「不存在」租户主键。

    Args:
        ns: 用例命名空间。

    Returns:
        int: 不存在的主键。
    """
    return int(ns.prefix[2:], 16) + 7_000_000


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
async def test_local_store_ensure_idempotent_and_reactivate(service_app: FastAPI, ns: Namespace) -> None:
    """本地数据源：ensure 幂等建（首次落来源）、重复幂等、回收后可复活。"""
    store = _store(service_app)
    user = _uid(ns, "ensure")

    created = await store.ensure(
        tenant_id=DEMO_TENANT_ID, user_id=user, target_tenant_id=ACME_TENANT_ID, source="admin_create"
    )
    assert created.tenant_id == ACME_TENANT_ID
    assert created.code == "acme"
    assert created.status == "active"

    again = await store.ensure(tenant_id=DEMO_TENANT_ID, user_id=user, target_tenant_id=ACME_TENANT_ID, source="import")
    assert again.status == "active"
    targets = await store.list_targets(tenant_id=DEMO_TENANT_ID, user_id=user)
    assert [item.tenant_id for item in targets] == [ACME_TENANT_ID]

    await store.revoke(tenant_id=DEMO_TENANT_ID, user_id=user, target_tenant_id=ACME_TENANT_ID)
    await store.revoke(tenant_id=DEMO_TENANT_ID, user_id=user, target_tenant_id=ACME_TENANT_ID)  # 幂等
    assert await store.list_targets(tenant_id=DEMO_TENANT_ID, user_id=user) == []
    all_rows = await store.list_targets(tenant_id=DEMO_TENANT_ID, user_id=user, include_disabled=True)
    assert [item.status for item in all_rows] == ["disabled"]

    revived = await store.ensure(
        tenant_id=DEMO_TENANT_ID, user_id=user, target_tenant_id=ACME_TENANT_ID, source="import"
    )
    assert revived.status == "active"
    rows = await store.list_targets(tenant_id=DEMO_TENANT_ID, user_id=user)
    assert [item.tenant_id for item in rows] == [ACME_TENANT_ID]


@pytest.mark.kiwi_id(891)
async def test_local_store_revoke_all_and_source_validation(service_app: FastAPI, ns: Namespace) -> None:
    """本地数据源：回收全部（幂等）+ 来源取值校验 + 目标租户不存在。"""
    store = _store(service_app)
    user = _uid(ns, "revoke-all")

    await store.ensure(tenant_id=DEMO_TENANT_ID, user_id=user, target_tenant_id=DEMO_TENANT_ID, source="sso_jit")
    await store.ensure(tenant_id=DEMO_TENANT_ID, user_id=user, target_tenant_id=ACME_TENANT_ID, source="sso_jit")
    await store.revoke_all(tenant_id=DEMO_TENANT_ID, user_id=user)
    await store.revoke_all(tenant_id=DEMO_TENANT_ID, user_id=user)  # 幂等
    assert await store.list_targets(tenant_id=DEMO_TENANT_ID, user_id=user) == []

    with pytest.raises(ParamError):
        await store.ensure(tenant_id=DEMO_TENANT_ID, user_id=user, target_tenant_id=DEMO_TENANT_ID, source="bogus")

    with pytest.raises(TenantNotFoundError):
        await store.ensure(
            tenant_id=DEMO_TENANT_ID,
            user_id=user,
            target_tenant_id=_missing_tenant(ns),
            source="admin_create",
        )


@pytest.mark.kiwi_id(891)
async def test_reconcile_reports_missing_and_dangling(service_app: FastAPI, ns: Namespace) -> None:
    """对账巡检：缺行（清单中无自有关系）/ 悬空行（关系表有行但不在清单）均可检出；无差异为空。"""
    registry = cast("EngineRegistry", service_app.state.engine_registry)
    async with session_scope(registry, db_key=PLATFORM_DB_KEY) as session:
        service = TenantMembershipService(TenantMembershipRepository(session), DbUnitOfWork(session))
        recon_user = _uid(ns, "recon")
        recon_other = _uid(ns, "recon-other")
        recon_absent = _uid(ns, "recon-absent")
        for user in (recon_user, recon_other):
            await service.ensure(
                tenant_id=DEMO_TENANT_ID, user_id=user, target_tenant_id=DEMO_TENANT_ID, source="sso_jit"
            )
        await service.ensure(
            tenant_id=DEMO_TENANT_ID, user_id=recon_other, target_tenant_id=ACME_TENANT_ID, source="import"
        )

        clean = await service.reconcile(
            tenant_id=DEMO_TENANT_ID, user_ids=ConcurrentStableList([recon_user, recon_other])
        )
        assert clean.missing == []

        report = await service.reconcile(
            tenant_id=DEMO_TENANT_ID, user_ids=ConcurrentStableList([recon_user, recon_absent])
        )
        assert recon_absent in report.missing
        assert recon_other in report.dangling


@pytest.mark.kiwi_id(891)
async def test_membership_store_dependency_export(service_app: FastAPI) -> None:
    """依赖出口与登记名：应用装配件经 `get_tenant_membership_store` 可取，登记名 `local`。"""
    request = cast("Request", _RequestStub(service_app))
    assert isinstance(get_tenant_membership_store(request), LocalTenantMembershipStore)
    assert LOCAL_TENANT_MEMBERSHIP_STORE == "local"


@pytest.mark.kiwi_id(891)
async def test_internal_endpoints_read_write(
    client: AsyncClient, service_app: FastAPI, platform_db_url: str, ns: Namespace
) -> None:
    """内部端点：POST 建关系 → GET 读 → DELETE 回收（含 include_disabled 与全部回收）。"""
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    headers = {"Authorization": "Bearer org"}
    user = _uid(ns, "internal")

    created = await client.post(
        API,
        json={
            "owner_tenant_id": DEMO_TENANT_ID,
            "user_id": user,
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
            platform_db_url, tenant_id=DEMO_TENANT_ID, user_id=user, target_tenant_id=ACME_TENANT_ID
        )
        == "active|admin_create"
    )

    listed = await client.get(
        API,
        params={"owner_tenant_id": DEMO_TENANT_ID, "user_id": user},
        headers=headers,
    )
    assert listed.status_code == 200
    assert [item["tenant_id"] for item in listed.json()["data"]["targets"]] == [str(ACME_TENANT_ID)]

    revoked = await client.delete(
        API,
        params={"owner_tenant_id": DEMO_TENANT_ID, "user_id": user, "target_tenant_id": ACME_TENANT_ID},
        headers=headers,
    )
    assert revoked.status_code == 200
    assert revoked.json()["data"]["targets"] == []

    with_disabled = await client.get(
        API,
        params={"owner_tenant_id": DEMO_TENANT_ID, "user_id": user, "include_disabled": True},
        headers=headers,
    )
    assert [item["status"] for item in with_disabled.json()["data"]["targets"]] == ["disabled"]

    revoked_all = await client.delete(API, params={"owner_tenant_id": DEMO_TENANT_ID, "user_id": user}, headers=headers)
    assert revoked_all.status_code == 200
    assert revoked_all.json()["data"]["targets"] == []


@pytest.mark.kiwi_id(891)
async def test_internal_endpoint_auth_and_validation(client: AsyncClient, service_app: FastAPI, ns: Namespace) -> None:
    """内部端点：鉴权白名单（org / identity）、网关票据与匿名拒、参数校验与来源校验。"""
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    user = _uid(ns, "auth")

    identity_headers = {"Authorization": "Bearer identity"}
    ok = await client.get(API, params={"owner_tenant_id": DEMO_TENANT_ID, "user_id": user}, headers=identity_headers)
    assert ok.status_code == 200

    gateway = await client.get(
        API,
        params={"owner_tenant_id": DEMO_TENANT_ID, "user_id": user},
        headers={"Authorization": "Bearer gateway"},
    )
    assert gateway.status_code == 401

    anonymous = await client.get(API, params={"owner_tenant_id": DEMO_TENANT_ID, "user_id": user})
    assert anonymous.status_code == 401

    # 缺参：统一校验处理器收口为参数错误（10001 / HTTP 200，`BizError` 语义）
    missing = await client.get(API, params={"owner_tenant_id": DEMO_TENANT_ID}, headers=identity_headers)
    assert missing.json()["code"] == 10001

    bad_source = await client.post(
        API,
        json={
            "owner_tenant_id": DEMO_TENANT_ID,
            "user_id": user,
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
            "user_id": user,
            "target_tenant_id": _missing_tenant(ns),
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
