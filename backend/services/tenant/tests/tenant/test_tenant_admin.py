"""租户管理面与开通编排测试（任务 `04_01`；Kiwi 2325）。

覆盖：列表 / 详情 / 修改 / 停用启用 / 配额 / 模块开关 / 开通（成功、失败清理、幂等回放、模块校验）。
"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.api.deps import get_platform_read_db, get_platform_write_db, get_service_client
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.models.base import Base
from bms_core.models.outbox import SysOutbox
from bms_tenant.models.tenant import SysTenant
from bms_tenant.models.tenant_database import SysTenantDatabase
from bms_tenant.models.tenant_module import SysTenantModule
from bms_tenant.models.tenant_quota import SysTenantQuota
from bms_tenant.services.provisioning import TenantProvisionService
from ops.tenant_provisioning import ProvisionOutcome

pytestmark = pytest.mark.kiwi_id(2325)

API = "/api/v1/tenants"
_TABLES = [
    cast("Table", SysTenant.__table__),
    cast("Table", SysTenantDatabase.__table__),
    cast("Table", SysTenantModule.__table__),
    cast("Table", SysTenantQuota.__table__),
    cast("Table", SysOutbox.__table__),
]

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


class _Resp:
    """服务间响应替身。"""

    def __init__(self, payload: object, status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload

    def payload(self) -> object:
        return self._payload


class _StubClient:
    """服务间客户端替身：目录快照 / 会话撤销 / 配额。"""

    def __init__(self) -> None:
        self.paths: ConcurrentStableList[str] = ConcurrentStableList()
        self.revoked_calls = 0

    async def call(self, request: object) -> _Resp:
        path = cast("Any", request).path
        self.paths.append(path)
        if path.endswith("/modules/snapshot"):
            return _Resp({"code": 0, "data": list(_CATALOG)})
        if path.endswith("/sessions/revoke-tenant"):
            self.revoked_calls += 1
            return _Resp({"code": 0, "data": {"revoked": 2}})
        return _Resp({"code": 0, "data": {"allowed": True, "used_value": 0, "limit_value": None}})


async def _override_platform(app: FastAPI, url: str) -> _StubClient:
    """覆盖平台库读 / 写会话依赖并返回模板客户端替身。

    Args:
        app: 应用实例。
        url: 临时平台库连接串。

    Returns:
        _StubClient: 服务间客户端替身。
    """
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=_TABLES)
    await engine.dispose()
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(create_async_engine(url), expire_on_commit=False)

    async def _session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    client = _StubClient()
    app.dependency_overrides[get_platform_read_db] = _session
    app.dependency_overrides[get_platform_write_db] = _session
    app.dependency_overrides[get_service_client] = lambda: client
    return client


async def _seed_tenant(
    url: str,
    *,
    code: str,
    name: str = "租户",
    domain: str | None = None,
    kind: str = "business",
    status: str = "active",
    modules: tuple[tuple[str, str], ...] = (),
) -> int:
    """写入租户（含库名对照 / 模块），返回主键。

    Args:
        url: 平台库连接串。
        code: 租户编码。
        name: 租户名称。
        domain: 子域名。
        kind: 租户类型。
        status: 状态。
        modules: 模块（标识 / 状态）。

    Returns:
        int: 租户主键。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all, tables=_TABLES)
        async with factory() as session:
            row = SysTenant(code=code, name=name, domain=domain, kind=kind, status=status)
            session.add(row)
            await session.flush()
            tenant_id = int(row.id)
            session.add(SysTenantDatabase(tenant_id=tenant_id, db_basis=code))
            for module_key, module_status in modules:
                session.add(SysTenantModule(tenant_id=tenant_id, module_key=module_key, status=module_status))
            await session.commit()
            return tenant_id
    finally:
        await engine.dispose()


async def test_list_excludes_platform_tenant_and_filters(
    client: AsyncClient, service_app: FastAPI, tmp_path: Path
) -> None:
    """列表：平台租户排除、code 模糊 / 状态筛选、模块摘要。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'admin.db'}"
    await _seed_tenant(url, code="acme", name="Acme", domain="acme.example.com", modules=(("pur", "enabled"),))
    await _seed_tenant(url, code="paused", name="Paused", status="suspended")
    await _seed_tenant(url, code="platform", name="平台管理", kind="platform")
    await _override_platform(service_app, url)

    all_rows = (await client.get(API)).json()["data"]
    assert all_rows["total"] == 2
    assert {row["code"] for row in all_rows["list"]} == {"acme", "paused"}
    acme = next(row for row in all_rows["list"] if row["code"] == "acme")
    assert acme["modules"] == ["pur"]

    filtered = (await client.get(API, params={"code": "acm", "status": "active"})).json()["data"]
    assert filtered["total"] == 1 and filtered["list"][0]["code"] == "acme"
    by_name = (await client.get(API, params={"name": "Paused"})).json()["data"]
    assert by_name["total"] == 1 and by_name["list"][0]["status"] == "suspended"


async def test_detail_update_and_domain_conflict(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """详情 / 修改（名称 / 域名 / 到期）/ 域名冲突 82004 / 平台租户不可改 82003。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'detail.db'}"
    tenant_id = await _seed_tenant(url, code="acme", name="Acme", domain="acme.example.com")
    other_id = await _seed_tenant(url, code="other", name="Other", domain="other.example.com")
    platform_id = await _seed_tenant(url, code="platform", name="平台", kind="platform")
    await _override_platform(service_app, url)

    detail = (await client.get(f"{API}/{tenant_id}")).json()["data"]
    assert detail["code"] == "acme" and detail["quotas"] == []
    assert [item["module_key"] for item in detail["modules"]] == ["cw", "pay", "pur", "sale", "sup", "wh"]

    updated = await client.put(f"{API}/{tenant_id}", json={"name": "Acme 新", "expire_at": "2027-01-01T00:00:00"})
    assert updated.json()["data"]["name"] == "Acme 新"

    conflict = await client.put(f"{API}/{tenant_id}", json={"domain": "other.example.com"})
    assert conflict.status_code == 409 and conflict.json()["code"] == 82004

    platform_update = await client.put(f"{API}/{platform_id}", json={"name": "改平台"})
    assert platform_update.status_code == 409 and platform_update.json()["code"] == 82003

    not_found = await client.get(f"{API}/{other_id + 999999}")
    assert not_found.status_code == 404 and not_found.json()["code"] == 82002


async def test_suspend_activate_and_platform_guard(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """停用（会话撤销 + 事件）/ 启用 / 状态冲突 82003 / 平台租户禁停。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'life.db'}"
    tenant_id = await _seed_tenant(url, code="acme", name="Acme")
    platform_id = await _seed_tenant(url, code="platform", name="平台", kind="platform")
    stub = await _override_platform(service_app, url)

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


async def test_quotas_read_write_and_invalid_key(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """配额：整组配置、未列出维度保持、非法维度 10001。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'quota.db'}"
    tenant_id = await _seed_tenant(url, code="acme")
    await _override_platform(service_app, url)

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


async def test_modules_list_switch_and_unavailable(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """模块：三态清单、开通 / 停用 / 重新开通、未启用模块 82007、基础能力不可勾选 10001。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'modules.db'}"
    tenant_id = await _seed_tenant(url, code="acme", modules=(("pur", "enabled"),))
    await _override_platform(service_app, url)

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
    client: AsyncClient, service_app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """开通：成功（状态 / 模块 / 配额 / 初始口令）、幂等回放、code / 域名冲突、模块未启用。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'create.db'}"
    await _seed_tenant(url, code="dup", name="Dup", domain="dup.example.com")
    await _override_platform(service_app, url)

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

    monkeypatch.setattr("bms_tenant.services.provisioning.provision_infrastructure", _provision)
    from bms_core.api.deps import get_idempotency_store

    store = _MemoryIdempotency()
    service_app.dependency_overrides[get_idempotency_store] = lambda: store

    body = {"code": "acme", "name": "Acme", "domain": "acme.example.com", "modules": ["pur"]}
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
    assert replay.status_code == 201 and replay.json()["data"]["tenant"]["code"] == "acme"

    dup_code = await client.post(API, json={"code": "dup", "name": "Dup2"})
    assert dup_code.status_code == 409 and dup_code.json()["code"] == 82001
    dup_domain = await client.post(API, json={"code": "new", "name": "New", "domain": "dup.example.com"})
    assert dup_domain.status_code == 409 and dup_domain.json()["code"] == 82004
    bad_module = await client.post(API, json={"code": "new2", "name": "New2", "modules": ["pay"]})
    assert bad_module.status_code == 400 and bad_module.json()["code"] == 82007

    no_key = await client.post(API, json={"code": "nokey", "name": "NoKey"})
    assert no_key.status_code == 201 and no_key.json()["data"]["tenant"]["code"] == "nokey"


async def test_create_tenant_failure_cleans_registry(
    client: AsyncClient, service_app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """开通失败：注册行清理（不留半开通租户）+ 82006；失败幂等键可重试。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'fail.db'}"
    await _override_platform(service_app, url)
    calls = {"count": 0}

    async def _fail(**kwargs: object) -> ProvisionOutcome:
        del kwargs
        calls["count"] += 1
        raise RuntimeError("db down")

    monkeypatch.setattr("bms_tenant.services.provisioning.provision_infrastructure", _fail)
    from bms_core.api.deps import get_idempotency_store

    store = _MemoryIdempotency()
    service_app.dependency_overrides[get_idempotency_store] = lambda: store
    resp = await client.post(API, json={"code": "bad", "name": "Bad"}, headers={"Idempotency-Key": "k2"})
    assert resp.status_code == 500 and resp.json()["code"] == 82006
    assert (await client.get(API)).json()["data"]["total"] == 0

    async def _ok(**kwargs: object) -> ProvisionOutcome:
        del kwargs
        return ProvisionOutcome(db_basis="bad", admin_username="admin", initial_password="p")

    monkeypatch.setattr("bms_tenant.services.provisioning.provision_infrastructure", _ok)
    retry = await client.post(API, json={"code": "bad", "name": "Bad"}, headers={"Idempotency-Key": "k2"})
    assert retry.status_code == 201
    assert calls["count"] == 1


async def test_create_tenant_in_progress_returns_82003(
    client: AsyncClient, service_app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """幂等键已被占用但无结果（进行中）→ 82003。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'busy.db'}"
    await _override_platform(service_app, url)

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
    resp = await client.post(API, json={"code": "busy", "name": "Busy"}, headers={"Idempotency-Key": "k3"})
    assert resp.status_code == 409 and resp.json()["code"] == 82003


async def test_provision_service_skips_duplicate_and_seeds(tmp_path: Path) -> None:
    """开通服务：已存在 code / 域名占用前置拒绝（不进入库侧编排）。"""
    from bms_core.core.config import get_settings
    from bms_core.core.exceptions import TenantCodeExistsError, TenantDomainConflictError
    from bms_core.outbox.null import NullOutboxStore
    from bms_tenant.schemas.tenant_admin import TenantCreateRequest
    from bms_tenant.services.tenant_admin import TenantAdminService
    from bms_tenant.services.tenant_module import ModuleCatalog, TenantModuleService
    from bms_tenant.services.tenant_quota import TenantQuotaService

    url = f"sqlite+aiosqlite:///{tmp_path / 'svc.db'}"
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = SysTenant(code="acme", name="Acme", domain="acme.example.com", status="active")
            session.add(row)
            await session.commit()
            settings = get_settings()
            modules = TenantModuleService(
                session=session, catalog=ModuleCatalog(client=cast("Any", _StubClient()), cache=None)
            )
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
                await service.create(TenantCreateRequest(code="acme", name="Acme2"))
            with pytest.raises(TenantDomainConflictError):
                await service.create(TenantCreateRequest(code="other", name="Other", domain="acme.example.com"))
    finally:
        await engine.dispose()


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
    client: AsyncClient, service_app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """会话撤销不可达 / 非 2xx / 非法载荷：停用仍成功（仅告警）。"""

    def _degraded(mode: str) -> _DegradedClient:
        return _DegradedClient(mode)

    def _override_client(mode: str) -> None:
        service_app.dependency_overrides[get_service_client] = lambda: _degraded(mode)

    for mode in ("raise", "http", "bad"):
        url = f"sqlite+aiosqlite:///{tmp_path / f'deg-{mode}.db'}"
        tenant_id = await _seed_tenant(url, code=f"t-{mode}")
        await _override_platform(service_app, url)
        _override_client(mode)
        resp = await client.post(f"{API}/{tenant_id}/suspend")
        assert resp.status_code == 200 and resp.json()["data"]["status"] == "suspended"


async def test_suspend_invalidates_with_callable_source(
    client: AsyncClient, service_app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """租户源具备 invalidate / bump_version：停用与修改均调用（缓存失效）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'invalidate.db'}"
    tenant_id = await _seed_tenant(url, code="acme")
    await _override_platform(service_app, url)
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
    assert "acme:None" in calls and "bump" in calls
