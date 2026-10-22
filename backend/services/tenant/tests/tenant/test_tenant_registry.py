"""租户注册只读契约端到端测试（05_06）：`active-single` 唯一启用租户三态 + 三选一查询与写路径仓储。"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.api.deps import get_platform_read_db
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.base import Base
from bms_core.models.tenant.tenant import SysTenant
from bms_core.models.tenant.tenant_database import SysTenantDatabase
from bms_tenant.repositories.tenant_registry import TenantRegistryRepository

API = "/api/v1/tenant-registry/active-single"
REGISTRY_API = "/api/v1/tenant-registry"
_TABLES = [cast("Table", SysTenant.__table__), cast("Table", SysTenantDatabase.__table__)]


async def _seed(url: str, tenants: ConcurrentStableList[tuple[str, str]]) -> None:
    """建表并写入启用租户（`code` / `name`）。

    Args:
        url: 平台库连接串。
        tenants: 启用租户（编码 / 名称）清单。
    """
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[cast("Table", SysTenant.__table__), cast("Table", SysTenantDatabase.__table__)],
        )
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all([SysTenant(code=code, name=name, status="active") for code, name in tenants])
        await session.commit()
    await engine.dispose()


def _override_read_db(app: FastAPI, url: str) -> None:
    """把平台只读会话依赖覆盖为临时库会话。

    Args:
        app: 应用实例。
        url: 临时平台库连接串。
    """

    async def _session() -> AsyncIterator[AsyncSession]:
        engine = create_async_engine(url)
        factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            yield session
        await engine.dispose()

    app.dependency_overrides[get_platform_read_db] = _session


@pytest.mark.kiwi_id(2239)
async def test_active_single_returns_snapshot(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """恰 1 个启用租户 → 200 + 注册快照（含编码 / 主键 / 库名基回落）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    await _seed(url, ConcurrentStableList([("solo", "唯一租户")]))
    _override_read_db(service_app, url)

    resp = await client.get(API)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["code"] == "solo" and data["name"] == "唯一租户"
    assert data["tenant_id"] is not None and data["db_basis"] == "solo"


@pytest.mark.kiwi_id(2239)
async def test_active_single_multiple_conflict(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """≥ 2 个启用租户 → 409 + `80004`（不返回清单）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    await _seed(url, ConcurrentStableList([("a", "租户A"), ("b", "租户B")]))
    _override_read_db(service_app, url)

    resp = await client.get(API)
    assert resp.status_code == 409
    assert resp.json()["code"] == 80004 and resp.json()["data"] is None


@pytest.mark.kiwi_id(2239)
async def test_active_single_none_not_found(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """0 个启用租户 → 404 + `80001`（沿用既有失败语义）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    await _seed(url, ConcurrentStableList())
    _override_read_db(service_app, url)

    resp = await client.get(API)
    assert resp.status_code == 404
    assert resp.json()["code"] == 80001


async def _seed_registry(url: str, *, code: str, db_basis: str | None, status: str = "active") -> int:
    """建表并写入租户（可选对照表行），返回租户主键。

    Args:
        url: 平台库连接串。
        code: 租户编码。
        db_basis: 库名基（None = 不写对照表行）。
        status: 状态。

    Returns:
        int: 租户主键。
    """
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        row = SysTenant(code=code, name=f"{code}-名称", domain=f"{code}.example.com", status=status)
        session.add(row)
        await session.flush()
        tenant_id = row.id
        if db_basis is not None:
            session.add(SysTenantDatabase(tenant_id=tenant_id, db_basis=db_basis))
        await session.commit()
    await engine.dispose()
    return tenant_id


async def test_registry_by_code_domain_and_id(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """三选一查询：编码 / 域名 / 主键各命中一次，快照含对照表库名基。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    tenant_id = await _seed_registry(url, code="acme", db_basis="acme_db")
    _override_read_db(service_app, url)

    by_code = await client.get(REGISTRY_API, params={"code": "acme"})
    assert by_code.status_code == 200
    assert by_code.json()["data"]["db_basis"] == "acme_db"

    by_domain = await client.get(REGISTRY_API, params={"domain": "acme.example.com"})
    assert by_domain.json()["data"]["code"] == "acme"

    by_id = await client.get(REGISTRY_API, params={"tenant_id": str(tenant_id)})
    assert by_id.json()["data"]["tenant_id"] == str(tenant_id)


async def test_registry_rejects_invalid_query_forms(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """查询形态校验：未提供 / 多于一个来源 / `tenant_id` 非十进制字符串 → 10001。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    await _seed_registry(url, code="acme", db_basis=None)
    _override_read_db(service_app, url)

    assert (await client.get(REGISTRY_API)).json()["code"] == 10001
    both = await client.get(REGISTRY_API, params={"code": "acme", "domain": "acme.example.com"})
    assert both.json()["code"] == 10001
    bad_id = await client.get(REGISTRY_API, params={"tenant_id": "not-a-number"})
    assert bad_id.json()["code"] == 10001


async def test_registry_unknown_and_suspended(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """未知租户 → 404 / 80001；已停用 → 403 / 80002；缺对照行回落编码（记告警）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    await _seed_registry(url, code="paused", db_basis=None, status="suspended")
    _override_read_db(service_app, url)

    unknown = await client.get(REGISTRY_API, params={"code": "ghost"})
    assert unknown.status_code == 404
    assert unknown.json()["code"] == 80001

    suspended = await client.get(REGISTRY_API, params={"code": "paused"})
    assert suspended.status_code == 403
    assert suspended.json()["code"] == 80002


async def test_registry_falls_back_to_code_without_database_row(
    client: AsyncClient, service_app: FastAPI, tmp_path: Path
) -> None:
    """缺对照表行：库名基回落当前编码（记告警不阻断）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    await _seed_registry(url, code="legacy", db_basis=None)
    _override_read_db(service_app, url)

    resp = await client.get(REGISTRY_API, params={"code": "legacy"})
    assert resp.status_code == 200
    assert resp.json()["data"]["db_basis"] == "legacy"


async def test_active_single_with_database_row(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """唯一启用租户且对照表有行：库名基取对照值（不触发回落告警）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    await _seed_registry(url, code="solo", db_basis="solo_db")
    _override_read_db(service_app, url)

    resp = await client.get(API)
    assert resp.status_code == 200
    assert resp.json()["data"]["db_basis"] == "solo_db"


async def test_registry_repository_reads_writes_and_status(tmp_path: Path) -> None:
    """仓储读写：登记同事务写对照表、按三键取行、状态变更后不再计入启用行。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'repo.db'}"
    engine: AsyncEngine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            repository = TenantRegistryRepository(cast("Any", session))
            row = await repository.create(code="acme", name="ACME", domain="acme.example.com", db_basis="acme_db")
            await session.commit()
            tenant_id = row.id

            assert (await repository.by_code("acme")) is not None
            assert (await repository.by_domain("acme.example.com")) is not None
            assert (await repository.by_id(tenant_id)) is not None
            assert await repository.db_basis(tenant_id) == "acme_db"
            assert [item.code for item in await repository.active_rows()] == ["acme"]

            await repository.update_status(row, "suspended")
            await session.commit()
            reloaded = await repository.by_id(tenant_id)
            assert reloaded is not None and reloaded.status == "suspended"
            assert list(await repository.active_rows()) == []
    finally:
        await engine.dispose()
