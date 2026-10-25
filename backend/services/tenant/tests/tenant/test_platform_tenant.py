"""默认平台租户引导测试（任务 `04_01`；Kiwi 2325）。

覆盖：首次创建（kind=platform + 基础模块 + 事件）、已就绪跳过、业务租户占用编码拒启、失败清理。
"""

from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.config import get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.models.base import Base
from bms_core.models.outbox import SysOutbox
from bms_core.models.tenant.tenant import TENANT_KIND_PLATFORM, SysTenant
from bms_core.models.tenant.tenant_database import SysTenantDatabase
from bms_core.models.tenant.tenant_module import SysTenantModule
from bms_core.outbox.null import NullOutboxStore
from bms_core.tenant.provisioning import ProvisionOutcome
from bms_tenant.domains.tenant.repositories.tenant_registry import TenantRegistryRepository
from bms_tenant.domains.tenant.services.platform_tenant import ensure_platform_tenant_row
from bms_tenant.domains.tenant.services.tenant_admin import TenantAdminService
from bms_tenant.domains.tenant.services.tenant_module import TenantModuleService
from bms_tenant.domains.tenant.services.tenant_quota import TenantQuotaService

pytestmark = pytest.mark.kiwi_id(2325)

_TABLES = [
    cast("Table", SysTenant.__table__),
    cast("Table", SysTenantDatabase.__table__),
    cast("Table", SysTenantModule.__table__),
    cast("Table", SysOutbox.__table__),
]


class _StubModules:
    """模块服务替身：记录基础模块开通次数。"""

    def __init__(self) -> None:
        self.opened = 0

    async def open_base_modules(self, tenant_id: int, *, opened_by: int | None = None) -> None:
        del tenant_id, opened_by
        self.opened += 1


async def _factory(tmp_path: Path) -> async_sessionmaker[AsyncSession]:
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=_TABLES)
    await engine.dispose()
    return async_sessionmaker(create_async_engine(url), expire_on_commit=False)


def _admin(session: AsyncSession, modules: _StubModules) -> TenantAdminService:
    settings = get_settings()
    return TenantAdminService(
        session=cast("object", session),  # type: ignore[arg-type]
        modules=cast("TenantModuleService", modules),
        quotas=TenantQuotaService(cast("object", session), settings),  # type: ignore[arg-type]
        outbox=NullOutboxStore(),
    )


async def _run(
    factory: async_sessionmaker[AsyncSession], modules: _StubModules, *, bootstrap: bool
) -> tuple[bool, bool]:
    async with factory() as session:
        created = await ensure_platform_tenant_row(
            session=cast("object", session),  # type: ignore[arg-type]
            settings=get_settings(),
            modules=cast("TenantModuleService", modules),
            admin=_admin(session, modules),
            outbox=NullOutboxStore(),
        )
        return created, bootstrap


async def test_platform_tenant_created_and_reused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """首次创建 → kind=platform + active + 基础模块；再次调用跳过。"""
    factory = await _factory(tmp_path)

    async def _ok(**kwargs: object) -> ProvisionOutcome:
        del kwargs
        return ProvisionOutcome(db_basis="platform", admin_username="admin", initial_password="p")

    monkeypatch.setattr("bms_tenant.domains.tenant.services.platform_tenant.provision_infrastructure", _ok)
    modules = _StubModules()
    created, _ = await _run(factory, modules, bootstrap=True)
    assert created is True and modules.opened == 1
    async with factory() as session:
        row = await TenantRegistryRepository(session).by_code(get_settings().platform_tenant.code)
        assert row is not None and row.kind == TENANT_KIND_PLATFORM and row.status == "active"
    created_again, _ = await _run(factory, modules, bootstrap=True)
    assert created_again is False and modules.opened == 2


async def test_platform_tenant_code_occupied_by_business(tmp_path: Path) -> None:
    """平台租户编码被业务租户占用 → ConfigError（拒启）。"""
    factory = await _factory(tmp_path)
    async with factory() as session:
        session.add(SysTenant(code=get_settings().platform_tenant.code, name="业务租户", status="active"))
        await session.commit()
    with pytest.raises(ConfigError):
        await _run(factory, _StubModules(), bootstrap=True)


async def test_platform_tenant_provision_failure_cleans(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """库侧编排失败 → 注册行清理 + 返回 False（不阻断启动）。"""
    factory = await _factory(tmp_path)

    async def _fail(**kwargs: object) -> ProvisionOutcome:
        del kwargs
        raise RuntimeError("db down")

    monkeypatch.setattr("bms_tenant.domains.tenant.services.platform_tenant.provision_infrastructure", _fail)
    created, _ = await _run(factory, _StubModules(), bootstrap=True)
    assert created is False
    async with factory() as session:
        assert await TenantRegistryRepository(session).by_code(get_settings().platform_tenant.code) is None
