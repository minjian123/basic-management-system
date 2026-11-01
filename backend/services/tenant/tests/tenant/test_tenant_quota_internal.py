"""租户配额服务与内部契约端点测试（任务 `04_01`；Kiwi 2325）。

覆盖：默认值播种、校验 / 占用 / 释放、原子超限（82005）、无配额行放行、内部端点（模块状态 / 配额）
与 `require_service` 鉴权。

单库叠加口径（04-6-2）：库用共享平台库（不再建临时库），租户主键按命名空间派生，
配额行 / 模块行全部落在本用例租户上（禁止「tenant_id=1」这类与种子租户重叠的固定值）。
"""

from collections.abc import AsyncIterator
from typing import cast

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.api.deps import get_platform_read_db, get_platform_write_db
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ParamError, TenantQuotaExceededError
from bms_core.models.tenant.tenant import SysTenant
from bms_core.models.tenant.tenant_module import SysTenantModule
from bms_core.models.tenant.tenant_quota import SysTenantQuota
from bms_core.testing.namespace import Namespace
from bms_core.testing.schema import ensure_tables
from bms_tenant.domains.tenant.repositories.tenant_quota import TenantQuotaRepository
from bms_tenant.domains.tenant.schemas.tenant_admin import TenantQuotaUpdateItem
from bms_tenant.domains.tenant.services.tenant_quota import TenantQuotaService, quota_defaults

pytestmark = pytest.mark.kiwi_id(2325)

API = "/api/v1/tenant/internal"
_TABLES = [
    cast("Table", SysTenant.__table__),
    cast("Table", SysTenantModule.__table__),
    cast("Table", SysTenantQuota.__table__),
]


def _quota(ns: Namespace, tenant_id: int, *, quota_key: str = "user_count") -> dict[str, object]:
    """构造内部契约请求体（租户主键按本用例派生）。

    Args:
        ns: 用例命名空间（未使用，保留统一签名）。
        tenant_id: 租户主键。
        quota_key: 配额键。

    Returns:
        dict[str, object]: 请求体。
    """
    del ns
    return {"tenant_id": tenant_id, "quota_key": quota_key}


async def _factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """共享平台库会话工厂（表幂等补齐）。

    Args:
        engine: 共享平台库引擎。

    Returns:
        async_sessionmaker[AsyncSession]: 会话工厂。
    """
    await ensure_tables(engine, list(_TABLES))
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_tenant(factory: async_sessionmaker[AsyncSession], code: str) -> int:
    """写入一个启用租户并返回主键。

    Args:
        factory: 会话工厂。
        code: 租户编码（带命名空间前缀）。

    Returns:
        int: 租户主键。
    """
    async with factory() as session:
        row = SysTenant(code=code, name="Acme", status="active")
        session.add(row)
        await session.flush()
        tenant_id = int(row.id)
        await session.commit()
    return tenant_id


def _override(app: FastAPI, factory: async_sessionmaker[AsyncSession]) -> None:
    async def _session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_platform_read_db] = _session
    app.dependency_overrides[get_platform_write_db] = _session


async def test_quota_service_check_consume_release(shared_platform_engine: AsyncEngine, ns: Namespace) -> None:
    """校验 / 占用 / 释放：无行放行、超限 82005、占用后读取真实值、释放下限 0。"""
    factory = await _factory(shared_platform_engine)
    tenant_id = await _seed_tenant(factory, ns.code("quota"))
    async with factory() as session:
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


async def test_quota_repository_atomic_consume(shared_platform_engine: AsyncEngine, ns: Namespace) -> None:
    """仓储原子占用：超限返回 False 且不落增量；释放无行返回 0。"""
    factory = await _factory(shared_platform_engine)
    tenant_id = await _seed_tenant(factory, ns.code("atomic"))
    async with factory() as session:
        repo = TenantQuotaRepository(session)
        await repo.ensure_default(tenant_id=tenant_id, quota_key="user_count", limit_value=2)
        await session.commit()
        assert await repo.consume(tenant_id=tenant_id, quota_key="user_count", amount=2) is True
        await session.commit()
        assert await repo.consume(tenant_id=tenant_id, quota_key="user_count", amount=1) is False
        await session.commit()
        row = await repo.get(tenant_id, "user_count")
        assert row is not None and row.used_value == 2
        assert await repo.release(tenant_id=tenant_id + 1, quota_key="user_count", amount=1) == 0


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


async def test_internal_endpoints(
    client: AsyncClient, service_app: FastAPI, shared_platform_engine: AsyncEngine, ns: Namespace
) -> None:
    """内部契约：模块状态、配额 check / consume / release、无配额行放行、超限 82005。"""
    factory = await _factory(shared_platform_engine)
    _override(service_app, factory)
    from bms_core.oauth.verify import get_token_verifier

    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()
    tenant_id = await _seed_tenant(factory, ns.code("internal"))
    async with factory() as session:
        session.add(SysTenantQuota(tenant_id=tenant_id, quota_key="user_count", limit_value=1, used_value=0))
        await session.commit()

    headers = {"Authorization": "Bearer stub", "X-Tenant-ID": "demo"}
    status = await client.get(f"{API}/modules/status", params={"tenant_id": tenant_id}, headers=headers)
    assert status.status_code == 200 and status.json()["data"]["enabled"] == []

    check = await client.post(f"{API}/quotas/check", json={**_quota(ns, tenant_id), "amount": 1}, headers=headers)
    assert check.status_code == 200 and check.json()["data"]["allowed"] is True
    consumed = await client.post(f"{API}/quotas/consume", json={**_quota(ns, tenant_id), "amount": 1}, headers=headers)
    assert consumed.json()["data"]["used_value"] == 1
    exceeded = await client.post(f"{API}/quotas/consume", json={**_quota(ns, tenant_id), "amount": 1}, headers=headers)
    assert exceeded.status_code == 409 and exceeded.json()["code"] == 82005
    released = await client.post(f"{API}/quotas/release", json={**_quota(ns, tenant_id), "amount": 1}, headers=headers)
    assert released.json()["data"]["used_value"] == 0
    free = await client.post(
        f"{API}/quotas/check",
        json={**_quota(ns, tenant_id, quota_key="storage_bytes"), "amount": 999},
        headers=headers,
    )
    assert free.json()["data"]["allowed"] is True
