"""租户服务补充分支测试（任务 `04_01`；Kiwi 2325）。

覆盖：模块目录缓存与错误分支、模块仓储重开通 / 状态切换、平台租户引导包装与失败分支、
停用时会话撤销降级、租户源缓存失效钩子。
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ConfigError, ParamError, ServiceUnavailableError, TenantModuleUnavailableError
from bms_core.core.serialization import stable_json_dumps
from bms_core.models.base import Base
from bms_core.models.tenant.tenant import SysTenant
from bms_core.models.tenant.tenant_database import SysTenantDatabase
from bms_core.models.tenant.tenant_module import SysTenantModule
from bms_core.outbox.null import NullOutboxStore
from bms_core.servicecall.base import BaseServiceClient, ServiceResponse
from bms_core.tenant.provisioning import ProvisionOutcome
from bms_tenant.domains.tenant.repositories.tenant_module import TenantModuleRepository
from bms_tenant.domains.tenant.services import platform_tenant as platform_tenant_module
from bms_tenant.domains.tenant.services.platform_tenant import ensure_platform_tenant, ensure_platform_tenant_row
from bms_tenant.domains.tenant.services.tenant_admin import TenantAdminService
from bms_tenant.domains.tenant.services.tenant_module import (
    ModuleCatalog,
    TenantModuleService,
    _catalog_rows,  # pyright: ignore[reportPrivateUsage]
)
from bms_tenant.domains.tenant.services.tenant_quota import TenantQuotaService

pytestmark = pytest.mark.kiwi_id(2325)

_TABLES = [
    cast("Table", SysTenant.__table__),
    cast("Table", SysTenantDatabase.__table__),
    cast("Table", SysTenantModule.__table__),
]


class _Resp:
    def __init__(self, payload: object, status: int = 200) -> None:
        self.status_code = status
        self._payload = payload

    def payload(self) -> object:
        return self._payload


def _response(payload: object, *, status: int = 200) -> ServiceResponse:
    """构造统一响应体（负数用例直接断言解析分支）。

    Args:
        payload: JSON 可序列化载荷。
        status: HTTP 状态码。

    Returns:
        ServiceResponse: 服务间响应。
    """
    return ServiceResponse(status_code=status, content=stable_json_dumps(payload).encode())


class _Client:
    def __init__(self, payload: object = None, status: int = 200) -> None:
        self.payload_value = payload
        self.status = status
        self.calls = 0

    async def call(self, request: object) -> _Resp:
        del request
        self.calls += 1
        return _Resp(self.payload_value, self.status)


_CATALOG = [
    {
        "module_key": "pur",
        "name": "采购",
        "table_prefix": "pur_",
        "errcode_segment": "10",
        "service_group": "product",
        "status": "enabled",
    }
]


class _Cache:
    def __init__(self) -> None:
        self.data: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        self.deleted: ConcurrentStableList[str] = ConcurrentStableList()

    def get(self, key: str) -> object | None:
        return self.data.get(key)

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        self.data[key] = value

    def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.data.pop(key, None)

    def build_key(self, business_key: str, *, tenant: str | None = None) -> str:
        return f"bms:{tenant or 'global'}:generic:{business_key}"


async def _session(tmp_path: Path) -> tuple[async_sessionmaker[AsyncSession], str]:
    url = f"sqlite+aiosqlite:///{tmp_path / 'extra.db'}"
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=_TABLES)
    await engine.dispose()
    return async_sessionmaker(create_async_engine(url), expire_on_commit=False), url


async def test_module_catalog_cache_and_errors() -> None:
    """目录快照：缓存命中不重复回源、错误响应转 10007、非法行拒绝。"""
    cache = _Cache()
    client = _Client({"code": 0, "data": _CATALOG})
    catalog = ModuleCatalog(client=cast("BaseServiceClient", client), cache=cast("Any", cache))
    assert (await catalog.modules())[0].module_key == "pur"
    assert (await catalog.modules())[0].module_key == "pur"
    assert client.calls == 1
    assert "bms:global:generic:module_catalog" in cache.data

    with pytest.raises(ServiceUnavailableError):
        _catalog_rows(_response({"code": 0, "data": _CATALOG}, status=500))
    with pytest.raises(ServiceUnavailableError):
        _catalog_rows(_response([]))
    with pytest.raises(ServiceUnavailableError):
        _catalog_rows(_response({"code": 1}))
    with pytest.raises(ServiceUnavailableError):
        _catalog_rows(_response({"code": 0, "data": {}}))
    with pytest.raises(ServiceUnavailableError):
        _catalog_rows(_response({"code": 0, "data": ["bad"]}))


async def test_module_service_switch_absent_reopen_and_cache(tmp_path: Path) -> None:
    """开关：未开通即开通、停用后重开通、缓存键删除；基础模块勾选拒绝、不可开通模块 82007。"""
    factory, _url = await _session(tmp_path)
    cache = _Cache()
    async with factory() as session:
        session.add(SysTenant(code="acme", name="Acme", status="active"))
        await session.commit()
        service = TenantModuleService(
            session=cast("Any", session),
            catalog=ModuleCatalog(client=cast("BaseServiceClient", _Client({"code": 0, "data": _CATALOG})), cache=None),
        )
        service._cache = cast("Any", cache)  # pyright: ignore[reportPrivateUsage]
        await service.switch(1, "pur", "enabled", opened_by=7)
        await session.commit()
        row = await TenantModuleRepository(session).get(1, "pur")
        assert row is not None and row.status == "enabled"
        await service.switch(1, "pur", "disabled")
        await session.commit()
        assert cache.deleted
        await service.switch(1, "pur", "enabled", opened_by=8)
        await session.commit()
        row = await TenantModuleRepository(session).get(1, "pur")
        assert row is not None and row.opened_by == 8
        with pytest.raises(ParamError):
            await service.validate_optional(ConcurrentStableList(["sys"]))
        with pytest.raises(TenantModuleUnavailableError):
            await service.validate_optional(ConcurrentStableList(["unknown"]))


async def test_module_repository_open_reopen_status_map(tmp_path: Path) -> None:
    """仓储：status_map、重开通（停用 → 启用）与带操作人的状态切换。"""
    factory, _url = await _session(tmp_path)
    async with factory() as session:
        repo = TenantModuleRepository(session)
        await repo.open(tenant_id=1, module_keys=ConcurrentStableList(["pur"]), opened_by=1)
        await session.commit()
        assert (await repo.status_map(1))["pur"] == "enabled"
        row = await repo.get(1, "pur")
        assert row is not None
        await repo.set_status(row, "disabled")
        await session.commit()
        await repo.open(tenant_id=1, module_keys=ConcurrentStableList(["pur"]), opened_by=2)
        await session.commit()
        assert (await repo.get(1, "pur")).status == "enabled"  # type: ignore[union-attr]
        row = await repo.get(1, "pur")
        assert row is not None
        await repo.set_status(row, "enabled", opened_by=3)
        await session.commit()
        assert (await repo.get(1, "pur")).opened_by == 3  # type: ignore[union-attr]


async def test_platform_tenant_suspended_reprovision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """既有平台租户被停用：重新置 provisioning 并走库侧编排补齐。"""
    factory, _url = await _session(tmp_path)

    async def _ok(**kwargs: object) -> ProvisionOutcome:
        del kwargs
        return ProvisionOutcome(db_basis="platform", admin_username="admin", initial_password="p")

    monkeypatch.setattr(platform_tenant_module, "provision_infrastructure", _ok)
    async with factory() as session:
        session.add(
            SysTenant(code=get_settings().platform_tenant.code, name="平台", kind="platform", status="suspended")
        )
        await session.commit()
        modules = SimpleNamespace(open_base_modules=_noop_open)
        admin = TenantAdminService(
            session=cast("Any", session),
            modules=cast("Any", modules),
            quotas=TenantQuotaService(cast("Any", session), get_settings()),
            outbox=NullOutboxStore(),
        )
        created = await ensure_platform_tenant_row(
            session=cast("Any", session),
            settings=get_settings(),
            modules=cast("Any", modules),
            admin=admin,
            outbox=NullOutboxStore(),
        )
        assert created is True


async def _noop_open(tenant_id: int, *, opened_by: int | None = None) -> None:
    del tenant_id, opened_by


async def test_platform_tenant_base_modules_failure_tolerated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """基础模块开通失败仅告警（不阻断）。"""
    factory, _url = await _session(tmp_path)

    async def _ok(**kwargs: object) -> ProvisionOutcome:
        del kwargs
        return ProvisionOutcome(db_basis="platform", admin_username="admin", initial_password="p")

    async def _fail_open(tenant_id: int, *, opened_by: int | None = None) -> None:
        del tenant_id, opened_by
        raise RuntimeError("catalog down")

    monkeypatch.setattr(platform_tenant_module, "provision_infrastructure", _ok)
    async with factory() as session:
        modules = SimpleNamespace(open_base_modules=_fail_open)
        admin = TenantAdminService(
            session=cast("Any", session),
            modules=cast("Any", modules),
            quotas=TenantQuotaService(cast("Any", session), get_settings()),
            outbox=NullOutboxStore(),
        )
        created = await ensure_platform_tenant_row(
            session=cast("Any", session),
            settings=get_settings(),
            modules=cast("Any", modules),
            admin=admin,
            outbox=NullOutboxStore(),
        )
        assert created is True


async def test_platform_tenant_cleanup_failure_tolerated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """库侧失败 + 清理失败：仅告警并返回 False。"""
    factory, _url = await _session(tmp_path)

    async def _fail(**kwargs: object) -> ProvisionOutcome:
        del kwargs
        raise RuntimeError("db down")

    monkeypatch.setattr(platform_tenant_module, "provision_infrastructure", _fail)

    async def _explode(tenant_id: int) -> None:
        del tenant_id
        raise RuntimeError("cleanup down")

    monkeypatch.setattr(platform_tenant_module.TenantRegistryRepository, "delete_provisioning", _explode)
    async with factory() as session:
        modules = SimpleNamespace(open_base_modules=_noop_open)
        admin = TenantAdminService(
            session=cast("Any", session),
            modules=cast("Any", modules),
            quotas=TenantQuotaService(cast("Any", session), get_settings()),
            outbox=NullOutboxStore(),
        )
        created = await ensure_platform_tenant_row(
            session=cast("Any", session),
            settings=get_settings(),
            modules=cast("Any", modules),
            admin=admin,
            outbox=NullOutboxStore(),
        )
        assert created is False


async def test_ensure_platform_tenant_app_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    """启动包装：成功失效缓存 / ConfigError 上抛 / 其他异常吞掉；未开启直接返回。"""
    settings = get_settings()
    settings.platform_tenant.auto_bootstrap = True
    events: ConcurrentStableList[str] = ConcurrentStableList()

    class _Source:
        def invalidate(self, code: str) -> None:
            events.append(f"invalidate:{code}")

        def bump_version(self) -> None:
            events.append("bump")

    session = SimpleNamespace()

    class _Scope:
        async def __aenter__(self) -> Any:
            return session

        async def __aexit__(self, *exc: object) -> None:
            del exc

    def _scope(*args: object, **kwargs: object) -> _Scope:
        del args, kwargs
        return _Scope()

    app = SimpleNamespace(
        state=SimpleNamespace(
            settings=settings,
            engine_registry=object(),
            session_factory=object(),
            service_client=object(),
            cache=None,
            outbox_store=NullOutboxStore(),
            tenant_source=_Source(),
        )
    )

    def _make_modules(**kwargs: object) -> SimpleNamespace:
        del kwargs
        return SimpleNamespace()

    def _make_quota(*args: object, **kwargs: object) -> SimpleNamespace:
        del args, kwargs
        return SimpleNamespace()

    monkeypatch.setattr(platform_tenant_module, "session_scope", _scope)
    monkeypatch.setattr(platform_tenant_module, "TenantModuleService", _make_modules)
    monkeypatch.setattr(platform_tenant_module, "TenantAdminService", _make_modules)
    monkeypatch.setattr(platform_tenant_module, "TenantQuotaService", _make_quota)

    async def _created(**kwargs: object) -> bool:
        del kwargs
        return True

    monkeypatch.setattr(platform_tenant_module, "ensure_platform_tenant_row", _created)
    await ensure_platform_tenant(cast("Any", app))
    assert events == [f"invalidate:{settings.platform_tenant.code}", "bump"]

    async def _conflict(**kwargs: object) -> bool:
        del kwargs
        raise ConfigError("occupied")

    monkeypatch.setattr(platform_tenant_module, "ensure_platform_tenant_row", _conflict)
    with pytest.raises(ConfigError):
        await ensure_platform_tenant(cast("Any", app))

    async def _boom(**kwargs: object) -> bool:
        del kwargs
        raise RuntimeError("boom")

    monkeypatch.setattr(platform_tenant_module, "ensure_platform_tenant_row", _boom)
    await ensure_platform_tenant(cast("Any", app))

    async def _existing(**kwargs: object) -> bool:
        del kwargs
        return False

    monkeypatch.setattr(platform_tenant_module, "ensure_platform_tenant_row", _existing)
    app.state.tenant_source = object()
    await ensure_platform_tenant(cast("Any", app))

    async def _created_without_hooks(**kwargs: object) -> bool:
        del kwargs
        return True

    monkeypatch.setattr(platform_tenant_module, "ensure_platform_tenant_row", _created_without_hooks)
    await ensure_platform_tenant(cast("Any", app))

    settings.platform_tenant.auto_bootstrap = False
    await ensure_platform_tenant(cast("Any", app))
