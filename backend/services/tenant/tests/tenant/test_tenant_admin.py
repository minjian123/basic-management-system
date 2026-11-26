"""租户管理面与开通编排测试（任务 `04_01`；Kiwi 2325）。

覆盖：列表 / 详情 / 修改 / 停用启用 / 配额 / 模块开关 / 开通（成功、失败清理、幂等回放、模块校验）。

单库叠加口径（04-6-2）：库用**共享平台库**（基础租户集合已提交，等同业务既有数据）；用例自造
的租户按命名空间编码写入（并发不撞码），列表总数按命名空间前缀收敛，收尾由 `tenant_base` 清理。
"""

from collections.abc import AsyncIterator, Callable
from typing import Any, cast

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.api.deps import get_platform_read_db, get_platform_write_db, get_service_client
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.tenant.provisioning import ProvisionOutcome
from bms_core.testing.namespace import Namespace
from bms_tenant.domains.tenant.services.provisioning import TenantProvisionService
from tests_support.tenant_admin_helpers import Resp as _Resp
from tests_support.tenant_admin_helpers import StubClient as _StubClient
from tests_support.tenant_base import TenantBase

pytestmark = pytest.mark.kiwi_id(2325)

API = "/api/v1/tenants"
_CATALOG = ConcurrentStableList(
    [
        {
            "module_key": "sys",
            "name": "平台地基",
            "table_prefix": "sys_",
            "errcode_segment": "01",
            "service_group": "foundation",
            "status": "enabled",
        },
        {
            "module_key": "tenant",
            "name": "租户服务",
            "table_prefix": "tenant_",
            "errcode_segment": None,
            "service_group": "foundation",
            "status": "enabled",
        },
        {
            "module_key": "pur",
            "name": "采购",
            "table_prefix": "pur_",
            "errcode_segment": "10",
            "service_group": "product",
            "status": "enabled",
        },
        {
            "module_key": "pay",
            "name": "收付款",
            "table_prefix": "pay_",
            "errcode_segment": "11",
            "service_group": "product",
            "status": "planned",
        },
    ]
)


class _MemoryIdempotency:
    """内存幂等存储（单测无 Redis 时验证回放 / 失败重试）。"""

    def __init__(self) -> None:
        self.values: ConcurrentStableDict[str, object] = ConcurrentStableDict()

    async def begin(self, key: str, *, ttl: int = 0) -> bool:
        del ttl
        return key not in self.values

    async def load(self, key: str) -> object | None:
        return self.values.get(key)

    async def save(self, key: str, payload: object, *, ttl: int = 0) -> None:
        del ttl
        self.values[key] = payload


@pytest.fixture
def codes(ns: Namespace) -> Callable[[str], str]:
    """本用例的租户编码生成器（命名空间派生，并发下不与他人撞码）。

    Args:
        ns: 用例命名空间。

    Returns:
        Callable[[str], str]: 编码生成器（`suffix -> {prefix}-{suffix}`）。
    """

    def _code(suffix: str) -> str:
        # 租户编码契约：`^[a-z][a-z0-9_]{1,31}$`（不含连接符），故直接拼前缀
        return f"{ns.prefix}{suffix}"

    return _code


@pytest.fixture
def admin_platform(service_app: FastAPI, tenant_base: TenantBase) -> _StubClient:
    """把平台库读写会话指向共享库会话，并注入服务间客户端替身。

    单库叠加口径（04-6-2）：库用共享平台库（基础租户集合已提交，等同业务既有数据）；
    用例自造的行按命名空间编码写入，收尾由 `tenant_base` 统一清理。

    Args:
        service_app: 应用实例。
        tenant_base: 共享平台库上的基础数据集。

    Returns:
        _StubClient: 服务间客户端替身（断言会话撤销调用次数用）。
    """

    async def _session() -> AsyncIterator[AsyncSession]:
        yield tenant_base.session

    client = _StubClient()
    service_app.dependency_overrides[get_platform_read_db] = _session
    service_app.dependency_overrides[get_platform_write_db] = _session
    service_app.dependency_overrides[get_service_client] = lambda: client
    return client


async def _commit(base: TenantBase) -> None:
    """提交本用例自造的行（共享库上写入需显式提交）。

    Args:
        base: 基础数据集句柄。
    """
    await base.session.commit()


async def test_list_excludes_platform_tenant_and_filters(
    client: AsyncClient,
    service_app: FastAPI,
    tenant_base: TenantBase,
    admin_platform: _StubClient,
    codes: Callable[[str], str],
) -> None:
    """列表：平台租户排除、code 模糊 / 状态筛选、模块摘要。"""
    acme = codes("acme")
    await tenant_base.seed(
        code=acme, name="Acme", domain=f"{acme}.example.com", modules=ConcurrentStableList((("pur", "enabled"),))
    )
    paused = codes("paused")
    await tenant_base.seed(code=paused, name=f"Paused-{acme}")
    await tenant_base.seed(code=codes("platform"), name="平台管理", kind="platform")
    await _commit(tenant_base)

    all_rows = (await client.get(API, params={"code": codes("")})).json()["data"]
    assert all_rows["total"] == 2
    assert {row["code"] for row in all_rows["list"]} == {acme, paused}
    row_acme = next(row for row in all_rows["list"] if row["code"] == acme)
    assert row_acme["modules"] == ["pur"]

    filtered = (await client.get(API, params={"code": codes("acm"), "status": "active"})).json()["data"]
    assert filtered["total"] == 1 and filtered["list"][0]["code"] == acme
    by_name = (await client.get(API, params={"name": f"Paused-{acme}"})).json()["data"]
    assert by_name["total"] == 1 and by_name["list"][0]["status"] == "active"


async def test_detail_update_and_domain_conflict(
    client: AsyncClient,
    service_app: FastAPI,
    tenant_base: TenantBase,
    admin_platform: _StubClient,
    codes: Callable[[str], str],
) -> None:
    """详情 / 修改（名称 / 域名 / 到期）/ 域名冲突 82004 / 平台租户不可改 82003。"""
    acme = codes("acme")
    other = codes("other")
    tenant_id = await tenant_base.seed(code=acme, name="Acme", domain=f"{acme}.example.com")
    other_id = await tenant_base.seed(code=other, name="Other", domain=f"{other}.example.com")
    platform_id = await tenant_base.seed(code=codes("platform"), name="平台", kind="platform")
    await _commit(tenant_base)

    detail = (await client.get(f"{API}/{tenant_id}")).json()["data"]
    assert detail["code"] == acme and detail["quotas"] == []
    assert [item["module_key"] for item in detail["modules"]] == ["cw", "pay", "pur", "sale", "sup", "wh"]

    updated = await client.put(f"{API}/{tenant_id}", json={"name": "Acme 新", "expire_at": "2027-01-01T00:00:00"})
    assert updated.json()["data"]["name"] == "Acme 新"

    conflict = await client.put(f"{API}/{tenant_id}", json={"domain": f"{other}.example.com"})
    assert conflict.status_code == 409 and conflict.json()["code"] == 82004

    platform_update = await client.put(f"{API}/{platform_id}", json={"name": "改平台"})
    assert platform_update.status_code == 409 and platform_update.json()["code"] == 82003

    not_found = await client.get(f"{API}/{other_id + 999999}")
    assert not_found.status_code == 404 and not_found.json()["code"] == 82002


async def test_suspend_activate_and_platform_guard(
    client: AsyncClient,
    service_app: FastAPI,
    tenant_base: TenantBase,
    admin_platform: _StubClient,
    codes: Callable[[str], str],
) -> None:
    """停用（会话撤销 + 事件）/ 启用 / 状态冲突 82003 / 平台租户禁停。"""
    tenant_id = await tenant_base.seed(code=codes("acme"), name="Acme")
    platform_id = await tenant_base.seed(code=codes("platform"), name="平台", kind="platform")
    await _commit(tenant_base)
    stub = admin_platform

    suspended = await client.post(f"{API}/{tenant_id}/suspend")
    assert suspended.status_code == 200 and suspended.json()["data"]["status"] == "suspended"
    assert stub.revoked_calls == 1

    again = await client.post(f"{API}/{tenant_id}/suspend")
    assert again.status_code == 409 and again.json()["code"] == 82003

    activated = await client.post(f"{API}/{tenant_id}/activate")
    assert activated.status_code == 200 and activated.json()["data"]["status"] == "active"
    assert (await client.post(f"{API}/{tenant_id}/activate")).json()["code"] == 82003

    platform = await client.post(f"{API}/{platform_id}/suspend")
    assert platform.status_code == 409 and platform.json()["code"] == 82003


async def test_quotas_read_write_and_invalid_key(
    client: AsyncClient,
    service_app: FastAPI,
    tenant_base: TenantBase,
    admin_platform: _StubClient,
    codes: Callable[[str], str],
) -> None:
    """配额：整组配置、未列出维度保持、非法维度 10001。"""
    tenant_id = await tenant_base.seed(code=codes("acme"))
    await _commit(tenant_base)

    assert (await client.get(f"{API}/{tenant_id}/quotas")).json()["data"]["items"] == []
    updated = await client.put(
        f"{API}/{tenant_id}/quotas",
        json={
            "items": [
                {"quota_key": "user_count", "limit_value": 10},
                {"quota_key": "storage_bytes", "limit_value": 1024},
            ]
        },
    )
    items = {item["quota_key"]: item for item in updated.json()["data"]["items"]}
    assert items["user_count"]["limit_value"] == 10 and items["storage_bytes"]["limit_value"] == 1024

    keep = await client.put(
        f"{API}/{tenant_id}/quotas", json={"items": [{"quota_key": "user_count", "limit_value": 20}]}
    )
    kept = {item["quota_key"]: item for item in keep.json()["data"]["items"]}
    assert kept["user_count"]["limit_value"] == 20 and kept["storage_bytes"]["limit_value"] == 1024

    invalid = await client.put(f"{API}/{tenant_id}/quotas", json={"items": [{"quota_key": "bogus", "limit_value": 1}]})
    assert invalid.json()["code"] == 10001


async def test_modules_list_switch_and_unavailable(
    client: AsyncClient,
    service_app: FastAPI,
    tenant_base: TenantBase,
    admin_platform: _StubClient,
    codes: Callable[[str], str],
) -> None:
    """模块：三态清单、开通 / 停用 / 重新开通、未启用模块 82007、基础能力不可勾选 10001。"""
    tenant_id = await tenant_base.seed(code=codes("acme"), modules=ConcurrentStableList((("pur", "enabled"),)))
    await _commit(tenant_base)

    options = (await client.get(f"{API}/module-options")).json()["data"]["items"]
    pur = next(item for item in options if item["module_key"] == "pur")
    assert pur["optional"] is True
    pay = next(item for item in options if item["module_key"] == "pay")
    assert pay["optional"] is False

    listed = {
        item["module_key"]: item["status"]
        for item in (await client.get(f"{API}/{tenant_id}/modules")).json()["data"]["items"]
    }
    assert listed["pur"] == "enabled" and listed["pay"] == "not_opened"

    disabled = await client.put(f"{API}/{tenant_id}/modules/pur", json={"status": "disabled"})
    assert {item["module_key"]: item["status"] for item in disabled.json()["data"]["items"]}["pur"] == "disabled"
    enabled = await client.put(f"{API}/{tenant_id}/modules/pur", json={"status": "enabled"})
    assert {item["module_key"]: item["status"] for item in enabled.json()["data"]["items"]}["pur"] == "enabled"

    unavailable = await client.put(f"{API}/{tenant_id}/modules/pay", json={"status": "enabled"})
    assert unavailable.status_code == 400 and unavailable.json()["code"] == 82007
    base = await client.put(f"{API}/{tenant_id}/modules/sys", json={"status": "enabled"})
    assert base.json()["code"] == 10001


async def test_create_tenant_success_idempotency_and_validation(
    client: AsyncClient,
    service_app: FastAPI,
    tenant_base: TenantBase,
    admin_platform: _StubClient,
    codes: Callable[[str], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """开通：成功（状态 / 模块 / 配额 / 初始口令）、幂等回放、code / 域名冲突、模块未启用。"""
    dup = codes("dup")
    await tenant_base.seed(code=dup, name="Dup", domain=f"{dup}.example.com")
    await _commit(tenant_base)

    async def _provision(**kwargs: object) -> ProvisionOutcome:
        del kwargs
        return ProvisionOutcome(
            db_basis="acme",
            services=ConcurrentStableList(["platform"]),
            created_databases=ConcurrentStableList(["platform"]),
            seeded=3,
            roles_created=3,
            admin_username="admin",
            initial_password="Bms1@secret",
        )

    monkeypatch.setattr("bms_tenant.domains.tenant.services.provisioning.provision_infrastructure", _provision)
    from bms_core.api.deps import get_idempotency_store

    store = _MemoryIdempotency()
    service_app.dependency_overrides[get_idempotency_store] = lambda: store

    acme = codes("acme")
    body = {"code": acme, "name": "Acme", "domain": f"{acme}.example.com", "modules": ["pur"]}
    created = await client.post(API, json=body, headers={"Idempotency-Key": "k1"})
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["initial_password"] == "Bms1@secret"
    assert data["tenant"]["status"] == "active"
    modules = {item["module_key"]: item["status"] for item in data["tenant"]["modules"]}
    assert modules["pur"] == "enabled" and modules["pay"] == "not_opened"
    quotas = {item["quota_key"]: item["limit_value"] for item in data["tenant"]["quotas"]}
    assert quotas["user_count"] == 500 and quotas["storage_bytes"] == 107374182400

    replay = await client.post(API, json=body, headers={"Idempotency-Key": "k1"})
    assert replay.status_code == 201 and replay.json()["data"]["tenant"]["code"] == acme

    dup_code = await client.post(API, json={"code": dup, "name": "Dup2"})
    assert dup_code.status_code == 409 and dup_code.json()["code"] == 82001
    dup_domain = await client.post(API, json={"code": codes("new"), "name": "New", "domain": f"{dup}.example.com"})
    assert dup_domain.status_code == 409 and dup_domain.json()["code"] == 82004
    bad_module = await client.post(API, json={"code": codes("new2"), "name": "New2", "modules": ["pay"]})
    assert bad_module.status_code == 400 and bad_module.json()["code"] == 82007

    nokey = codes("nokey")
    no_key = await client.post(API, json={"code": nokey, "name": "NoKey"})
    assert no_key.status_code == 201 and no_key.json()["data"]["tenant"]["code"] == nokey


async def test_create_tenant_failure_cleans_registry(
    client: AsyncClient,
    service_app: FastAPI,
    tenant_base: TenantBase,
    admin_platform: _StubClient,
    codes: Callable[[str], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """开通失败：注册行清理（不留半开通租户）+ 82006；失败幂等键可重试。"""
    calls = {"count": 0}

    async def _fail(**kwargs: object) -> ProvisionOutcome:
        del kwargs
        calls["count"] += 1
        raise RuntimeError("db down")

    monkeypatch.setattr("bms_tenant.domains.tenant.services.provisioning.provision_infrastructure", _fail)
    from bms_core.api.deps import get_idempotency_store

    store = _MemoryIdempotency()
    service_app.dependency_overrides[get_idempotency_store] = lambda: store
    bad = codes("bad")
    resp = await client.post(API, json={"code": bad, "name": "Bad"}, headers={"Idempotency-Key": "k2"})
    assert resp.status_code == 500 and resp.json()["code"] == 82006
    cleaned = (await client.get(API, params={"code": codes("")})).json()["data"]
    assert cleaned["total"] == 0

    async def _ok(**kwargs: object) -> ProvisionOutcome:
        del kwargs
        return ProvisionOutcome(db_basis="bad", admin_username="admin", initial_password="p")

    monkeypatch.setattr("bms_tenant.domains.tenant.services.provisioning.provision_infrastructure", _ok)
    retry = await client.post(API, json={"code": bad, "name": "Bad"}, headers={"Idempotency-Key": "k2"})
    assert retry.status_code == 201
    assert calls["count"] == 1


async def test_create_tenant_in_progress_returns_82003(
    client: AsyncClient,
    service_app: FastAPI,
    tenant_base: TenantBase,
    admin_platform: _StubClient,
    codes: Callable[[str], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """幂等键已被占用但无结果（进行中）→ 82003。"""

    class _BusyStore:
        async def begin(self, key: str, *, ttl: int = 0) -> bool:
            del key, ttl
            return False

        async def load(self, key: str) -> object | None:
            del key
            return None

        async def save(self, key: str, payload: object, *, ttl: int = 0) -> None:
            del key, payload, ttl

    from bms_core.api.deps import get_idempotency_store

    service_app.dependency_overrides[get_idempotency_store] = lambda: _BusyStore()
    resp = await client.post(API, json={"code": codes("busy"), "name": "Busy"}, headers={"Idempotency-Key": "k3"})
    assert resp.status_code == 409 and resp.json()["code"] == 82003


async def test_provision_service_skips_duplicate_and_seeds(
    tenant_base: TenantBase, codes: Callable[[str], str]
) -> None:
    """开通服务：已存在 code / 域名占用前置拒绝（不进入库侧编排）。"""
    from bms_core.core.config import get_settings
    from bms_core.core.exceptions import TenantCodeExistsError, TenantDomainConflictError
    from bms_core.outbox.null import NullOutboxStore
    from bms_tenant.domains.tenant.schemas.tenant_admin import TenantCreateRequest
    from bms_tenant.domains.tenant.services.tenant_admin import TenantAdminService
    from bms_tenant.domains.tenant.services.tenant_module import ModuleCatalog, TenantModuleService
    from bms_tenant.domains.tenant.services.tenant_quota import TenantQuotaService

    acme = codes("acme")
    session = tenant_base.session
    await tenant_base.seed(code=acme, name="Acme", domain=f"{acme}.example.com")
    await _commit(tenant_base)

    settings = get_settings()
    modules = TenantModuleService(session=session, catalog=ModuleCatalog(client=cast("Any", _StubClient()), cache=None))
    admin = TenantAdminService(
        session=session,
        modules=modules,
        quotas=TenantQuotaService(session, settings),
        outbox=NullOutboxStore(),
    )
    service = TenantProvisionService(
        session=session,
        settings=settings,
        modules=modules,
        quotas=TenantQuotaService(session, settings),
        outbox=NullOutboxStore(),
        admin=admin,
    )
    with pytest.raises(TenantCodeExistsError):
        await service.create(TenantCreateRequest(code=acme, name="Acme2"))
    with pytest.raises(TenantDomainConflictError):
        await service.create(TenantCreateRequest(code=codes("other"), name="Other", domain=f"{acme}.example.com"))


class _DegradedClient(_StubClient):
    """会话撤销降级替身：按模式抛异常 / 非 2xx / 非法 data。"""

    def __init__(self, mode: str) -> None:
        super().__init__()
        self.mode = mode

    async def call(self, request: object) -> _Resp:
        if cast("Any", request).path.endswith("/sessions/revoke-tenant"):
            if self.mode == "raise":
                raise RuntimeError("identity down")
            if self.mode == "http":
                return _Resp({"code": 0, "data": {}}, status_code=500)
            return _Resp({"code": 0, "data": []})
        return await super().call(request)


async def test_suspend_revoke_degraded(
    client: AsyncClient,
    service_app: FastAPI,
    tenant_base: TenantBase,
    admin_platform: _StubClient,
    codes: Callable[[str], str],
) -> None:
    """会话撤销不可达 / 非 2xx / 非法载荷：停用仍成功（仅告警）。"""

    def _degraded(mode: str) -> _DegradedClient:
        return _DegradedClient(mode)

    def _override_client(mode: str) -> None:
        service_app.dependency_overrides[get_service_client] = lambda: _degraded(mode)

    for mode in ("raise", "http", "bad"):
        tenant_id = await tenant_base.seed(code=codes(mode))
        await _commit(tenant_base)
        _override_client(mode)
        resp = await client.post(f"{API}/{tenant_id}/suspend")
        assert resp.status_code == 200 and resp.json()["data"]["status"] == "suspended"


async def test_suspend_invalidates_with_callable_source(
    client: AsyncClient,
    service_app: FastAPI,
    tenant_base: TenantBase,
    admin_platform: _StubClient,
    codes: Callable[[str], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """租户源具备 invalidate / bump_version：停用与修改均调用（缓存失效）。"""
    acme = codes("acme")
    tenant_id = await tenant_base.seed(code=acme)
    await _commit(tenant_base)
    calls: ConcurrentStableList[str] = ConcurrentStableList()
    source = service_app.state.tenant_source

    def _invalidate(code: str | None = None, *, domain: str | None = None) -> None:
        calls.append(f"{code}:{domain}")

    def _bump() -> None:
        calls.append("bump")

    monkeypatch.setattr(source, "invalidate", _invalidate, raising=False)
    monkeypatch.setattr(source, "bump_version", _bump, raising=False)
    await client.post(f"{API}/{tenant_id}/suspend")
    await client.put(f"{API}/{tenant_id}", json={"name": "新名称"})
    assert f"{acme}:None" in calls and "bump" in calls
