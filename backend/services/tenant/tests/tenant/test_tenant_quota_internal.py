"""租户配额服务与内部契约端点测试（任务 `04_01`；Kiwi 2325）。

覆盖：默认值播种、校验 / 占用 / 释放、原子超限（82005）、无配额行放行、内部端点（模块状态 / 配额）
与 `require_service` 鉴权。
"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.api.deps import get_platform_read_db, get_platform_write_db
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ParamError, TenantQuotaExceededError
from bms_core.models.base import Base
from bms_tenant.models.tenant import SysTenant
from bms_tenant.models.tenant_module import SysTenantModule
from bms_tenant.models.tenant_quota import SysTenantQuota
from bms_tenant.repositories.tenant_quota import TenantQuotaRepository
from bms_tenant.schemas.tenant_admin import TenantQuotaUpdateItem
from bms_tenant.services.tenant_quota import TenantQuotaService, quota_defaults

pytestmark = pytest.mark.kiwi_id(2325)

_QUOTA = {"tenant_id": 1, "quota_key": "user_count"}

API = "/api/v1/tenant/internal"
_TABLES = [
    cast("Table", SysTenant.__table__),
    cast("Table", SysTenantModule.__table__),
    cast("Table", SysTenantQuota.__table__),
]


async def _db(tmp_path: Path) -> tuple[str, async_sessionmaker[AsyncSession]]:
    url = f"sqlite+aiosqlite:///{tmp_path / 'quota.db'}"
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=_TABLES)
    await engine.dispose()
    return url, async_sessionmaker(create_async_engine(url), expire_on_commit=False)


def _override(app: FastAPI, factory: async_sessionmaker[AsyncSession]) -> None:
    async def _session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_platform_read_db] = _session
    app.dependency_overrides[get_platform_write_db] = _session


async def test_quota_service_check_consume_release(tmp_path: Path) -> None:
    """校验 / 占用 / 释放：无行放行、超限 82005、占用后读取真实值、释放下限 0。"""
    _url, factory = await _db(tmp_path)
    async with factory() as session:
        session.add(SysTenant(code="acme", name="Acme", status="active"))
        await session.commit()
        tenant_id = 1
        service = TenantQuotaService(session, get_settings())
        assert (await service.check(tenant_id, "user_count", 1)).allowed is True
        await service.seed_defaults(tenant_id)
        await session.commit()
        defaults = quota_defaults(get_settings())
        assert defaults["user_count"] == 500

        await service.consume(tenant_id, "user_count", 3)
        await session.commit()
        items = {item.quota_key: item for item in await service.list_items(tenant_id)}
        assert items["user_count"].used_value == 3

        with pytest.raises(TenantQuotaExceededError):
            await service.consume(tenant_id, "user_count", 10_000)

        released = await service.release(tenant_id, "user_count", 100)
        assert released.used_value == 0
        with pytest.raises(ParamError):
            await service.update_limits(
                tenant_id, ConcurrentStableList([TenantQuotaUpdateItem(quota_key="bad", limit_value=1)])
            )


async def test_quota_repository_atomic_consume(tmp_path: Path) -> None:
    """仓储原子占用：超限返回 False 且不落增量；释放无行返回 0。"""
    _url, factory = await _db(tmp_path)
    async with factory() as session:
        repo = TenantQuotaRepository(session)
        await repo.ensure_default(tenant_id=1, quota_key="user_count", limit_value=2)
        await session.commit()
        assert await repo.consume(tenant_id=1, quota_key="user_count", amount=2) is True
        await session.commit()
        assert await repo.consume(tenant_id=1, quota_key="user_count", amount=1) is False
        await session.commit()
        row = await repo.get(1, "user_count")
        assert row is not None and row.used_value == 2
        assert await repo.release(tenant_id=2, quota_key="user_count", amount=1) == 0


class _StubVerifier:
    """服务身份校验替身（恒定通过）。"""

    async def verify(self, token: str, *, audience: str) -> object:
        del token, audience

        class _Verified:
            service = "platform"
            tenant_id = None
            subject = "platform"
            scopes: ConcurrentStableList[str] = ConcurrentStableList(())

        return _Verified()


async def test_internal_endpoints(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """内部契约：模块状态、配额 check / consume / release、无配额行放行、超限 82005。"""
    url, factory = await _db(tmp_path)
    _override(service_app, factory)
    from bms_core.oauth.verify import get_token_verifier

    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    async with factory() as session:
        session.add(SysTenant(code="acme", name="Acme", status="active"))
        await session.commit()
        session.add(SysTenantQuota(tenant_id=1, quota_key="user_count", limit_value=1, used_value=0))
        await session.commit()

    headers = {"Authorization": "Bearer stub", "X-Tenant-ID": "demo"}
    status = await client.get(f"{API}/modules/status", params={"tenant_id": 1}, headers=headers)
    assert status.status_code == 200 and status.json()["data"]["enabled"] == []

    check = await client.post(f"{API}/quotas/check", json={**_QUOTA, "amount": 1}, headers=headers)
    assert check.status_code == 200 and check.json()["data"]["allowed"] is True
    consumed = await client.post(f"{API}/quotas/consume", json={**_QUOTA, "amount": 1}, headers=headers)
    assert consumed.json()["data"]["used_value"] == 1
    exceeded = await client.post(f"{API}/quotas/consume", json={**_QUOTA, "amount": 1}, headers=headers)
    assert exceeded.status_code == 409 and exceeded.json()["code"] == 82005
    released = await client.post(f"{API}/quotas/release", json={**_QUOTA, "amount": 1}, headers=headers)
    assert released.json()["data"]["used_value"] == 0
    free = await client.post(
        f"{API}/quotas/check", json={**_QUOTA, "quota_key": "storage_bytes", "amount": 999}, headers=headers
    )
    assert free.json()["data"]["allowed"] is True
    del url
