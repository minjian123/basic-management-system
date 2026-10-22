"""租户仓储 / 配额 / 引导补充分支测试（任务 `04_01`；Kiwi 2325）。

覆盖：平台租户注册行查询、注册字段部分更新、配额行幂等补齐与超限、模块重复开通 / 无操作人切换、
模块行消失的兜底、非可勾选模块拒绝、无缓存时跳过键删除、平台租户 `provisioning` 状态补齐、
开通失败清理自身失败不掩盖原始异常。
"""

from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import TenantModuleUnavailableError, TenantProvisionFailedError, TenantQuotaExceededError
from bms_core.models.base import Base
from bms_core.models.tenant.tenant import SysTenant
from bms_core.models.tenant.tenant_database import SysTenantDatabase
from bms_core.models.tenant.tenant_module import SysTenantModule
from bms_core.models.tenant.tenant_quota import SysTenantQuota
from bms_core.outbox.null import NullOutboxStore
from bms_tenant.repositories.tenant_module import TenantModuleRepository
from bms_tenant.repositories.tenant_quota import TenantQuotaRepository
from bms_tenant.repositories.tenant_registry import TenantRegistryRepository
from bms_tenant.schemas.tenant_admin import TenantCreateRequest
from bms_tenant.services import platform_tenant as platform_tenant_module
from bms_tenant.services import provisioning as provisioning_module
from bms_tenant.services.platform_tenant import ensure_platform_tenant_row
from bms_tenant.services.provisioning import TenantProvisionService
from bms_tenant.services.tenant_admin import TenantAdminService
from bms_tenant.services.tenant_module import ModuleCatalog, TenantModuleService
from bms_tenant.services.tenant_quota import TenantQuotaService
from ops.tenant_provisioning import ProvisionOutcome

pytestmark = pytest.mark.kiwi_id(2325)

_TABLES = [
    cast("Table", SysTenant.__table__),
    cast("Table", SysTenantDatabase.__table__),
    cast("Table", SysTenantModule.__table__),
    cast("Table", SysTenantQuota.__table__),
]

_CATALOG = [
    {
        "module_key": "pur",
        "name": "采购",
        "table_prefix": "pur_",
        "errcode_segment": "10",
        "service_group": "product",
        "status": "enabled",
    },
    {
        "module_key": "custom",
        "name": "自定义能力",
        "table_prefix": "custom_",
        "errcode_segment": "99",
        "service_group": "platform",
        "status": "enabled",
    },
]


class _CatalogClient:
    """目录快照替身。"""

    async def call(self, request: object) -> object:
        del request

        class _Response:
            status_code = 200

            @staticmethod
            def payload() -> object:
                return {"code": 0, "data": _CATALOG}

        return _Response()


async def _session(tmp_path: Path) -> tuple[async_sessionmaker[AsyncSession], str]:
    """建临时 SQLite 库并返回会话工厂。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        tuple[async_sessionmaker[AsyncSession], str]: （会话工厂, 连接串）。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'branches.db'}"
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=_TABLES)
    await engine.dispose()
    return async_sessionmaker(create_async_engine(url), expire_on_commit=False), url


async def test_registry_platform_row_and_partial_update(tmp_path: Path) -> None:
    """注册仓储：平台租户行查询；名称 / 域名 / 到期时间按 None 跳过。"""
    factory, _url = await _session(tmp_path)
    async with factory() as session:
        repo = TenantRegistryRepository(session)
        platform = SysTenant(code="platform", name="平台", kind="platform", status="active")
        business = SysTenant(code="acme", name="Acme", status="active")
        session.add_all([platform, business])
        await session.commit()

        assert (await repo.platform_row()) is platform
        await repo.update_fields(business, domain="acme.example.com")
        assert business.name == "Acme" and business.domain == "acme.example.com"
        await repo.update_fields(business, name="Acme 2")
        assert business.name == "Acme 2" and business.domain == "acme.example.com"
        await repo.update_fields(business, expire_at=datetime(2030, 1, 1))
        assert business.expire_at == datetime(2030, 1, 1)


async def test_quota_repository_idempotent_and_service_branches(tmp_path: Path) -> None:
    """配额：行补齐幂等、无行放行、校验 / 原子占用超限 82005。"""
    factory, _url = await _session(tmp_path)
    async with factory() as session:
        session.add(SysTenant(code="acme", name="Acme", status="active"))
        await session.commit()
        repo = TenantQuotaRepository(session)
        first = await repo.ensure_default(tenant_id=1, quota_key="user_count", limit_value=3)
        second = await repo.ensure_default(tenant_id=1, quota_key="user_count", limit_value=3)
        assert first is second

        service = TenantQuotaService(session, get_settings())
        assert (await service.check(1, "storage_bytes", 1)).allowed is True
        assert (await service.consume(1, "storage_bytes", 1)).allowed is True
        assert (await service.release(1, "storage_bytes", 1)).allowed is True

        await repo.update_limit(first, 1)
        await repo.consume(tenant_id=1, quota_key="user_count", amount=1)
        with pytest.raises(TenantQuotaExceededError):
            await service.check(1, "user_count", 1)
        with pytest.raises(TenantQuotaExceededError):
            await service.consume(1, "user_count", 1)
        assert (await repo.consume(tenant_id=1, quota_key="missing", amount=1)) is False


async def test_module_repository_reopen_enabled_and_no_operator(tmp_path: Path) -> None:
    """模块仓储：已启用重复开通为空操作；启用时不传操作人保留原值。"""
    factory, _url = await _session(tmp_path)
    async with factory() as session:
        repo = TenantModuleRepository(session)
        await repo.open(tenant_id=1, module_keys=ConcurrentStableList(["pur"]), opened_by=5)
        await session.commit()
        await repo.open(tenant_id=1, module_keys=ConcurrentStableList(["pur"]), opened_by=9)
        await session.commit()
        row = await repo.get(1, "pur")
        assert row is not None and row.opened_by == 5
        await repo.set_status(row, "enabled")
        await session.commit()
        assert (await repo.get(1, "pur")).opened_by == 5  # type: ignore[union-attr]


class _VanishingRepo:
    """模块仓储替身：开通后仍取不到行（模拟并发删除 / 数据异常）。"""

    async def get(self, tenant_id: int, module_key: str) -> None:
        del tenant_id, module_key
        return None

    async def open(self, **_kwargs: object) -> None:
        return None

    async def set_status(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("行不存在时不应切换状态")


async def test_module_switch_row_vanishes_and_no_cache(tmp_path: Path) -> None:
    """开关：开通后行消失不报错；无缓存域时跳过键删除。"""
    factory, _url = await _session(tmp_path)
    async with factory() as session:
        service = TenantModuleService(
            session=cast("Any", session),
            catalog=ModuleCatalog(client=cast("Any", _CatalogClient()), cache=None),
            cache=None,
        )
        service._repo = cast("Any", _VanishingRepo())  # pyright: ignore[reportPrivateUsage]
        await service.switch(1, "pur", "enabled")


async def test_validate_optional_rejects_non_optional_module(tmp_path: Path) -> None:
    """目录已启用但不在可勾选清单：拒绝（82007）。"""
    factory, _url = await _session(tmp_path)
    async with factory() as session:
        service = TenantModuleService(
            session=cast("Any", session),
            catalog=ModuleCatalog(client=cast("Any", _CatalogClient()), cache=None),
        )
        with pytest.raises(TenantModuleUnavailableError):
            await service.validate_optional(ConcurrentStableList(["custom"]))


async def test_platform_tenant_provisioning_row_completed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """既有平台租户处于 `provisioning`：直接走库侧编排完成，不改状态前置。"""
    factory, _url = await _session(tmp_path)
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    async def _ok(**kwargs: object) -> ProvisionOutcome:
        del kwargs
        calls.append("provision")
        return ProvisionOutcome(db_basis="platform", admin_username="admin", initial_password="p")

    monkeypatch.setattr(platform_tenant_module, "provision_infrastructure", _ok)
    async with factory() as session:
        session.add(
            SysTenant(code=get_settings().platform_tenant.code, name="平台", kind="platform", status="provisioning")
        )
        await session.commit()
        modules = TenantModuleService(
            session=cast("Any", session),
            catalog=ModuleCatalog(client=cast("Any", _CatalogClient()), cache=None),
        )
        admin = TenantAdminService(
            session=cast("Any", session),
            modules=modules,
            quotas=TenantQuotaService(cast("Any", session), get_settings()),
            outbox=NullOutboxStore(),
        )
        created = await ensure_platform_tenant_row(
            session=cast("Any", session),
            settings=get_settings(),
            modules=modules,
            admin=admin,
            outbox=NullOutboxStore(),
        )
        assert created is True
        assert list(calls) == ["provision"]


async def test_provision_cleanup_failure_keeps_original_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """开通失败且清理自身失败：仍上抛 82006（不掩盖原始失败）。"""
    factory, _url = await _session(tmp_path)

    async def _fail(**kwargs: object) -> ProvisionOutcome:
        del kwargs
        raise RuntimeError("db down")

    monkeypatch.setattr(provisioning_module, "provision_infrastructure", _fail)

    async def _explode(self: object, tenant_id: int) -> None:
        del self, tenant_id
        raise RuntimeError("cleanup down")

    monkeypatch.setattr(TenantRegistryRepository, "delete_provisioning", _explode)
    async with factory() as session:
        service = TenantProvisionService(
            session=cast("Any", session),
            settings=get_settings(),
            modules=cast(
                "Any",
                TenantModuleService(
                    session=cast("Any", session),
                    catalog=ModuleCatalog(client=cast("Any", _CatalogClient()), cache=None),
                ),
            ),
            quotas=TenantQuotaService(cast("Any", session), get_settings()),
            outbox=NullOutboxStore(),
            admin=cast("Any", None),
        )
        with pytest.raises(TenantProvisionFailedError):
            await service.create(TenantCreateRequest(code="bad", name="Bad"))
