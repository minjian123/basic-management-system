"""租户注册只读契约端到端测试（05_06）：`active-single` 唯一启用租户三态。"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.api.deps import get_platform_read_db
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.base import Base
from bms_tenant.models.tenant import SysTenant
from bms_tenant.models.tenant_database import SysTenantDatabase

API = "/api/v1/tenant-registry/active-single"


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
