"""租户注册库解析用例（Kiwi 2343）：`bms_core/tenant/registry.py`。

覆盖：`tenant_refs` 读 `sys_tenant` 左联 `sys_tenant_database` 取库名基、缺对照行回落编码、
软删租户不返回、达梦同步分支走 `tenant_refs_sync`。
"""

from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.tenant.tenant import SysTenant
from bms_core.models.tenant.tenant_database import SysTenantDatabase
from bms_core.tenant import registry


async def _prepare(url: str) -> None:
    """建租户注册两表并写入样例数据（含软删租户与缺对照行的租户）。

    Args:
        url: 租户注册库连接串。
    """
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(cast("Table", SysTenant.__table__).create, checkfirst=True)
            await connection.run_sync(cast("Table", SysTenantDatabase.__table__).create, checkfirst=True)
        async with factory() as session:
            demo = SysTenant(code="demo", name="演示租户", domain="demo.bms.example.com")
            acme = SysTenant(code="acme", name="示例租户", domain="acme.bms.example.com")
            gone = SysTenant(code="gone", name="已删租户", domain="gone.bms.example.com")
            session.add_all([demo, acme, gone])
            await session.flush()
            session.add(SysTenantDatabase(tenant_id=demo.id, db_basis="demo_frozen"))
            session.add(SysTenantDatabase(tenant_id=gone.id, db_basis="gone_frozen"))
            gone.deleted_at = demo.created_at
            await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2343)
async def test_tenant_refs_reads_db_basis_and_falls_back_to_code(tmp_path: Path) -> None:
    """有对照行取库名基；无对照行回落编码；软删租户不返回。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'registry.db'}"
    await _prepare(url)
    refs = await registry.tenant_refs(url)
    mapping = {ref.code: ref.db_basis for ref in refs}
    assert mapping == {"demo": "demo_frozen", "acme": "acme"}
    assert "gone" not in mapping


@pytest.mark.kiwi_id(2343)
async def test_tenant_refs_uses_sync_branch_for_dm(monkeypatch: pytest.MonkeyPatch) -> None:
    """达梦（同步驱动）走 `tenant_refs_sync`（`asyncio.to_thread`）。"""
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    def _sync(url: str) -> ConcurrentStableList[registry.TenantRef]:
        calls.add(url)
        return ConcurrentStableList([registry.TenantRef(code="dm_tenant", db_basis="dm_basis")])

    def _fake_make_url(_url: str) -> Any:
        return _DmUrl()

    monkeypatch.setattr(registry, "tenant_refs_sync", _sync)
    monkeypatch.setattr(registry, "make_url", _fake_make_url)
    refs = await registry.tenant_refs("dm+dmPython://SYSDBA:pass@host:5236")
    assert [ref.code for ref in refs] == ["dm_tenant"]
    assert list(calls) == ["dm+dmPython://SYSDBA:pass@host:5236"]


class _DmUrl:
    """假 URL 对象：后端名为达梦（驱动同步分支）。"""

    def get_backend_name(self) -> str:
        """取后端名。

        Returns:
            str: 固定 `dm`。
        """
        return "dm"


@pytest.mark.kiwi_id(2343)
def test_tenant_refs_sync_reads_rows(tmp_path: Path) -> None:
    """同步实现与异步实现同口径（同一库读出相同结果）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'registry.db'}"
    import asyncio

    asyncio.run(_prepare(url))
    sync_url = url.replace("sqlite+aiosqlite", "sqlite")
    refs = registry.tenant_refs_sync(sync_url)
    mapping = {ref.code: ref.db_basis for ref in refs}
    assert mapping == {"demo": "demo_frozen", "acme": "acme"}


@pytest.mark.kiwi_id(2343)
def test_ref_falls_back_when_db_basis_empty() -> None:
    """行值为空 / 非字符串时库名基回落编码。"""
    assert registry._ref("demo", None).db_basis == "demo"  # pyright: ignore[reportPrivateUsage]
    assert registry._ref("demo", "").db_basis == "demo"  # pyright: ignore[reportPrivateUsage]
    assert registry._ref("demo", 123).db_basis == "demo"  # pyright: ignore[reportPrivateUsage]
    assert registry._ref("demo", "basis").db_basis == "basis"  # pyright: ignore[reportPrivateUsage]
