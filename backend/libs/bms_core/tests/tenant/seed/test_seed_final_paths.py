"""覆盖率收尾用例（07B `02_03`）：剩余更新分支与声明校验分支。

**Kiwi 编号**：本批新增用例暂不标 `kiwi_id`，统一归 `05_01` 回填。

**覆盖面**：表归属的「已存在且需更新」分支（入口与单步两条）、菜单单步成功路径、
平台授权真实写入（有权限码时）、种子声明 `service` / `db_key` / 前缀校验分支。
"""

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.models.base import Base
from bms_core.models.ownership import SysTableOwnership
from bms_core.models.platform.menu_form import SysForm, SysMenu
from bms_core.models.platform.permission_meta import SysAction, SysBusiness, SysPermission
from bms_core.models.platform.role import SysRole, SysRolePermission
from bms_core.registry.products import ProductManifest, _check_seed_declaration  # pyright: ignore[reportPrivateUsage]
from bms_core.services.module_registry import SeedRecord
from bms_core.tenant.seed import menu as menu_seed
from bms_core.tenant.seed import platform as platform_seed
from bms_core.tenant.seed import tables as tables_seed

# ---- 表归属：已存在且需更新（单步 seed_tables）----


def test_seed_tables_updates_existing_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`seed_tables` 单步：已存在的登记行值不同 → 走更新分支（`updated > 0`）。"""
    from bms_core.services.table_registry import table_ownership_view

    url = f"sqlite+aiosqlite:///{tmp_path / 'upd.db'}"
    first = table_ownership_view()[0]
    engine = create_async_engine(url)

    async def _prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(conn, tables=[cast("Table", SysTableOwnership.__table__)])
            )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            session.add(
                SysTableOwnership(
                    table_name=first.table_name,
                    owner="stale_owner",
                    domain=first.domain,
                    datasource=first.datasource,
                    status=first.status,
                )
            )
            await session.commit()

    asyncio.run(_prepare())
    asyncio.run(engine.dispose())
    monkeypatch.setenv("BMS_MIGRATION_URL", url)
    _created, updated, _retired = asyncio.run(tables_seed.seed_tables(url))
    assert updated >= 1


# ---- 表归属入口：已存在且需更新（分支入口）----


async def test_seed_tables_entry_updates_existing_rows(tmp_path: Path) -> None:
    """`seed_tables_entry`：已存在行值不同 → 走更新分支。"""
    from bms_core.services.table_registry import table_ownership_view

    url = f"sqlite+aiosqlite:///{tmp_path / 'upd2.db'}"
    first = table_ownership_view()[0]
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(conn, tables=[cast("Table", SysTableOwnership.__table__)])
            )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            session.add(
                SysTableOwnership(
                    table_name=first.table_name,
                    owner="stale_owner",
                    domain=first.domain,
                    datasource=first.datasource,
                    status=first.status,
                )
            )
            await session.commit()
            await tables_seed.seed_tables_entry(session, ConcurrentStableDict())
            await session.commit()
            row = (
                await session.execute(select(SysTableOwnership).where(SysTableOwnership.table_name == first.table_name))
            ).scalar_one()
            assert row.owner == first.owner
    finally:
        await engine.dispose()


# ---- 菜单单步成功路径 ----


def test_seed_menu_main_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`seed_menu.main` 正常路径：建表 + 播种 + 打印计数与一致性校验行。"""
    monkeypatch.setenv("BMS_MIGRATION_URL", f"sqlite+aiosqlite:///{tmp_path / 'menu.db'}")
    assert menu_seed.main(ConcurrentStableList([])) == 0
    out = capsys.readouterr().out
    assert "新增" in out
    assert "一致性校验通过" in out


# ---- 平台授权：有权限码时真实写入 ----


async def test_seed_platform_grants_entry_writes_rows_when_codes_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`seed_platform_grants_entry`：平台库有权限码 / 菜单 / 表单时写授权行。"""
    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'pg_tenant.db'}"
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'pg_platform.db'}"
    tables = [
        SysBusiness.__table__,
        SysAction.__table__,
        SysPermission.__table__,
        SysMenu.__table__,
        SysForm.__table__,
        SysRole.__table__,
        SysRolePermission.__table__,
    ]
    engine = create_async_engine(platform_url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(conn, tables=cast("Sequence[Table]", tables))
            )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            business = SysBusiness(code="sys", name="平台运维总控")
            action = SysAction(code="query", name="查询")
            session.add_all([business, action])
            await session.flush()
            session.add(SysPermission(business_id=int(business.id), action_id=int(action.id)))
            await session.commit()
    finally:
        await engine.dispose()

    monkeypatch.setattr(platform_seed, "_urls", lambda _code: (tenant_url, platform_url))  # type: ignore[reportUnknownLambdaType]
    tenant_engine = create_async_engine(tenant_url)
    try:
        async with tenant_engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(conn, tables=cast("Sequence[Table]", tables))
            )
        factory = async_sessionmaker(tenant_engine, expire_on_commit=False)
        async with factory() as session:
            await platform_seed.seed_platform_roles_entry(session, ConcurrentStableDict())
            await session.commit()
            await platform_seed.seed_platform_grants_entry(session, ConcurrentStableDict())
            await session.commit()
            grants = (await session.execute(select(SysRolePermission))).scalars().all()
            assert len(grants) > 0
    finally:
        await tenant_engine.dispose()


# ---- 种子声明校验分支 ----


def _manifest(product_key: str = "platform") -> ProductManifest:
    """构造最小清单（只用于声明校验）。

    Args:
        product_key: 清单归属产品。

    Returns:
        ProductManifest: 清单。
    """

    return ProductManifest(
        product_key=product_key,
        products=ConcurrentStableFrozenList(),
        services=ConcurrentStableFrozenList(),
        product_routes=ConcurrentStableFrozenList(),
        data_sources=ConcurrentStableFrozenList(),
        collaborations=ConcurrentStableFrozenList(),
        seeds=ConcurrentStableFrozenList(),
        error_codes=ConcurrentStableFrozenList(),
    )


def _record(**kwargs: Any) -> SeedRecord:
    """构造种子记录。

    Args:
        **kwargs: 覆盖字段。

    Returns:
        SeedRecord: 记录。
    """

    base: ConcurrentStableDict[str, Any] = ConcurrentStableDict()
    base.set("name", "seed-x")
    base.set("module", "ops.seed_menu")
    base.set("entry", "seed_menu_entry")
    base.set("service", "platform")
    base.set("db_key", "platform_platform")
    base.set("after", ConcurrentStableFrozenList())
    base.set("source", "platform")
    for key, value in kwargs.items():
        base.set(key, value)
    return SeedRecord(**dict(base))


def test_check_seed_declaration_reports_missing_service() -> None:  # pyright: ignore[reportPrivateUsage]
    """缺 `service` → 错误（声明校验分支）。"""
    errors = _check_seed_declaration(_record(service=""), manifest=_manifest(), label="m")  # pyright: ignore[reportPrivateUsage]
    assert any("缺少执行服务声明" in error for error in errors)


def test_check_seed_declaration_reports_missing_db_key() -> None:  # pyright: ignore[reportPrivateUsage]
    """缺 `db_key` → 错误。"""
    errors = _check_seed_declaration(_record(db_key=""), manifest=_manifest(), label="m")  # pyright: ignore[reportPrivateUsage]
    assert any("缺少分支目标库声明" in error for error in errors)


def test_check_seed_declaration_reports_bad_db_key_shape() -> None:  # pyright: ignore[reportPrivateUsage]
    """`db_key` 形态非法（不以 platform_ / tenant_ 开头）→ 错误。"""
    errors = _check_seed_declaration(_record(db_key="other_db"), manifest=_manifest(), label="m")  # pyright: ignore[reportPrivateUsage]
    assert any("db_key 形态非法" in error for error in errors)


def test_check_seed_declaration_reports_prefix_violation() -> None:  # pyright: ignore[reportPrivateUsage]
    """产品种子名不以 `<product_key>-` 开头 → 错误。"""
    errors = _check_seed_declaration(_record(name="wrong-name"), manifest=_manifest("demo"), label="m")  # pyright: ignore[reportPrivateUsage]
    assert any("产品种子名须以" in error for error in errors)


def test_check_seed_declaration_accepts_valid_record() -> None:  # pyright: ignore[reportPrivateUsage]
    """合法声明无错误。"""
    assert list(_check_seed_declaration(_record(), manifest=_manifest(), label="m")) == []  # pyright: ignore[reportPrivateUsage]
