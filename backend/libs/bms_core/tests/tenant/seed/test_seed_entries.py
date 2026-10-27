"""种子分支入口与单步命令成功路径用例（07B `02_03`；详设 §3.9 契约）。

**Kiwi 编号**：本批新增用例暂不标 `kiwi_id`，统一归 `05_01` 回填。

**覆盖面**：9 个 `*_entry` 在真实会话内实际写入（幂等 + 二次执行跳过）、
`seed_platform_rbac` / `seed_rbac` / `seed_tables` / `seed_modules` / `seed_tenants` 的成功路径与
`main()` 输出分支（覆盖率补齐）。
"""

import asyncio
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.config.models import SysConfig
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.models.base import Base
from bms_core.models.platform.catalog import SysModule, SysProduct
from bms_core.models.platform.menu_form import SysButton, SysField, SysForm, SysMenu, SysMenuForm, SysMenuI18n
from bms_core.models.platform.permission_meta import (
    SysAction,
    SysActionI18n,
    SysBusiness,
    SysBusinessI18n,
    SysPermission,
)
from bms_core.models.platform.role import SysRole, SysRolePermission
from bms_core.models.tenant.tenant import SysTenant
from bms_core.models.tenant.tenant_database import SysTenantDatabase
from bms_core.tenant.seed import config as config_seed
from bms_core.tenant.seed import module as module_seed
from bms_core.tenant.seed import platform as platform_seed
from bms_core.tenant.seed import rbac as rbac_seed
from bms_core.tenant.seed import tables as tables_seed
from bms_core.tenant.seed import tenant as tenant_seed

_TABLES: ConcurrentStableList[Table] = ConcurrentStableList(Base.metadata.sorted_tables)
"""建表清单：全量元数据表（种子入口会连带读写多张元数据表，逐表列举易漏）。"""

_UNUSED_EXPLICIT = [
    cast("Table", SysModule.__table__),
    cast("Table", SysProduct.__table__),
    cast("Table", SysBusiness.__table__),
    cast("Table", SysAction.__table__),
    cast("Table", SysPermission.__table__),
    cast("Table", SysMenu.__table__),
    cast("Table", SysMenuI18n.__table__),
    cast("Table", SysForm.__table__),
    cast("Table", SysMenuForm.__table__),
    cast("Table", SysButton.__table__),
    cast("Table", SysField.__table__),
    cast("Table", SysBusinessI18n.__table__),
    cast("Table", SysActionI18n.__table__),
    cast("Table", SysRole.__table__),
    cast("Table", SysRolePermission.__table__),
    cast("Table", SysTenant.__table__),
    cast("Table", SysTenantDatabase.__table__),
    cast("Table", SysConfig.__table__),
]


async def _session(url: str) -> AsyncSession:
    """建库并返回会话（调用方负责关闭引擎）。

    Args:
        url: 连接串。

    Returns:
        AsyncSession: 会话（引擎挂在 `session.bind`）。
    """
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        # 种子入口会连带读写多张元数据表（业务码 / 动作 / 菜单 / 表单 / 按钮 / 字段及其 i18n 附表），
        # 逐表列举易漏，故按元数据**全量建表**（临时库，成本可忽略）。
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=_TABLES))
    return async_sessionmaker(engine, expire_on_commit=False)()


async def _count(session: AsyncSession, model: object) -> int:
    """统计表行数。

    Args:
        session: 会话。
        model: ORM 模型。

    Returns:
        int: 行数。
    """
    table = cast("Table", model.__table__)  # type: ignore[attr-defined]
    return len((await session.execute(select(table))).all())


# ---- seed-module 入口 ----


async def test_seed_modules_entry_writes_and_is_idempotent(tmp_path: Path) -> None:
    """`seed_modules_entry` 写入服务目录 + 产品档案；重复执行幂等。"""
    session = await _session(f"sqlite+aiosqlite:///{tmp_path / 'm.db'}")
    try:
        await module_seed.seed_modules_entry(session, ConcurrentStableDict())
        await session.commit()
        modules = await _count(session, SysModule)
        assert modules > 0
        await module_seed.seed_modules_entry(session, ConcurrentStableDict())
        await session.commit()
        assert await _count(session, SysModule) == modules
    finally:
        await session.close()


# ---- seed-tables 入口 ----


async def test_seed_tables_entry_writes_and_retires(tmp_path: Path) -> None:
    """`seed_tables_entry` 写入归属登记并清退清单外行（幂等）。"""
    from bms_core.models.ownership import SysTableOwnership

    url = f"sqlite+aiosqlite:///{tmp_path / 't.db'}"
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(conn, tables=[cast("Table", SysTableOwnership.__table__)])
            )
        session = async_sessionmaker(engine, expire_on_commit=False)()
        try:
            # 预置一条「清单外」登记行，验证清退
            session.add(
                SysTableOwnership(table_name="retired_probe", owner="platform", datasource="platform", status="enabled")
            )
            await session.commit()
            await tables_seed.seed_tables_entry(session, ConcurrentStableDict())
            await session.commit()
            rows = (await session.execute(select(SysTableOwnership))).scalars().all()
            assert all(row.table_name != "retired_probe" or row.deleted_at is not None for row in rows)
        finally:
            await session.close()
    finally:
        await engine.dispose()


# ---- seed-tenant 入口 ----


async def test_seed_tenants_entry_writes_seed_tenants(tmp_path: Path) -> None:
    """`seed_tenants_entry` 写入种子租户与对照行；重复执行幂等。"""
    session = await _session(f"sqlite+aiosqlite:///{tmp_path / 'ten.db'}")
    try:
        await tenant_seed.seed_tenants_entry(session, ConcurrentStableDict())
        await session.commit()
        tenants = await _count(session, SysTenant)
        assert tenants == len(tenant_seed.TENANT_SEEDS)
        await tenant_seed.seed_tenants_entry(session, ConcurrentStableDict())
        await session.commit()
        assert await _count(session, SysTenant) == tenants
    finally:
        await session.close()


# ---- seed-config 入口 ----


async def test_seed_configs_entry_writes_defaults(tmp_path: Path) -> None:
    """`seed_configs_entry` 写入系统参数默认值（重复执行幂等）。"""
    from bms_core.config.models import SysConfig

    session = await _session(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    try:
        await config_seed.seed_configs_entry(session, ConcurrentStableDict())
        first = await _count(session, SysConfig)
        assert first == len(config_seed.PLATFORM_CONFIG_DEFAULTS)
        await config_seed.seed_configs_entry(session, ConcurrentStableDict())
        assert await _count(session, SysConfig) == first
    finally:
        await session.close()


# ---- seed-platform-role / grant 入口 ----


async def test_seed_platform_roles_entry_writes_two_roles(tmp_path: Path) -> None:
    """`seed_platform_roles_entry` 写两个平台角色（重复执行幂等）。"""
    session = await _session(f"sqlite+aiosqlite:///{tmp_path / 'pr.db'}")
    try:
        await platform_seed.seed_platform_roles_entry(session, ConcurrentStableDict())
        await session.commit()
        assert await _count(session, SysRole) == 2
        await platform_seed.seed_platform_roles_entry(session, ConcurrentStableDict())
        await session.commit()
        assert await _count(session, SysRole) == 2
    finally:
        await session.close()


async def test_seed_platform_grants_entry_requires_roles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`seed_platform_grants_entry`：角色不存在时抛 `ParamError`（须先跑 role 种子）。

    该入口先从平台库读权限码（只读、不经分支连接），故须先把平台库指向临时库。
    """
    from bms_core.core.exceptions import ParamError

    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'pg.db'}"
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'pg_platform.db'}"
    await _prepare_platform_db(platform_url)
    # 平台库路径由 `_urls` 按配置派生（不受 BMS_MIGRATION_URL 影响），故直接替换解析结果
    monkeypatch.setattr(platform_seed, "_urls", lambda _code: (tenant_url, platform_url))  # type: ignore[reportUnknownLambdaType]
    session = await _session(tenant_url)
    try:
        with pytest.raises(ParamError, match="角色不存在"):
            await platform_seed.seed_platform_grants_entry(session, ConcurrentStableDict())
    finally:
        await session.close()


async def _prepare_platform_db(url: str) -> None:
    """建平台库（`_urls` 解析的平台库目标）。

    Args:
        url: 平台库连接串。
    """
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=_TABLES))
    finally:
        await engine.dispose()


# ---- seed-rbac-role / grant 入口 ----


async def test_seed_rbac_roles_entry_writes_three_roles(tmp_path: Path) -> None:
    """`seed_rbac_roles_entry` 写三类内置管理员角色（重复执行幂等）。"""
    session = await _session(f"sqlite+aiosqlite:///{tmp_path / 'rr.db'}")
    try:
        await rbac_seed.seed_rbac_roles_entry(session, ConcurrentStableDict())
        await session.commit()
        assert await _count(session, SysRole) == len(rbac_seed.BUILTIN_ADMIN_ROLES)
        await rbac_seed.seed_rbac_roles_entry(session, ConcurrentStableDict())
        await session.commit()
        assert await _count(session, SysRole) == len(rbac_seed.BUILTIN_ADMIN_ROLES)
    finally:
        await session.close()


# ---- seed-menu 入口 ----


async def test_seed_menu_entry_writes_metadata(tmp_path: Path) -> None:
    """`seed_menu_entry` 写入业务码 / 动作码 / 菜单（重复执行幂等）。"""
    from bms_core.tenant.seed import menu as menu_seed

    session = await _session(f"sqlite+aiosqlite:///{tmp_path / 'menu.db'}")
    try:
        await menu_seed.seed_menu_entry(session, ConcurrentStableDict())
        await session.commit()
        businesses = await _count(session, SysBusiness)
        assert businesses > 0
        await menu_seed.seed_menu_entry(session, ConcurrentStableDict())
        await session.commit()
        assert await _count(session, SysBusiness) == businesses
    finally:
        await session.close()


# ---- 单步命令成功路径 ----


def test_seed_module_main_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`seed_module.main` 应急写库路径（`--write`）：建表 + 播种 + 打印计数。"""
    monkeypatch.setenv("BMS_MIGRATION_URL", f"sqlite+aiosqlite:///{tmp_path / 'mm.db'}")
    assert module_seed.main(ConcurrentStableList(["--write"])) == 0
    out = capsys.readouterr().out
    assert "应急写库" in out


def test_seed_tables_main_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`seed_tables.main` 正常路径：建表 + upsert + 打印计数。"""
    monkeypatch.setenv("BMS_MIGRATION_URL", f"sqlite+aiosqlite:///{tmp_path / 'tt.db'}")
    assert tables_seed.main(ConcurrentStableList([])) == 0
    out = capsys.readouterr().out
    assert "新增" in out and "清退" in out


def test_seed_tenant_main_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`seed_tenant.main` 正常路径：建表 + 写租户 + 打印计数。"""
    monkeypatch.setenv("BMS_MIGRATION_URL", f"sqlite+aiosqlite:///{tmp_path / 'tn.db'}")
    assert tenant_seed.main(ConcurrentStableList([])) == 0
    assert "新增" in capsys.readouterr().out


def test_seed_config_main_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`seed_config.main` 正常路径：写参数 + 打印计数。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'cc.db'}"
    from bms_core.config.models import SysConfig

    engine = create_async_engine(url)

    async def _prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(conn, tables=[cast("Table", SysConfig.__table__)])
            )

    asyncio.run(_prepare())
    asyncio.run(engine.dispose())
    monkeypatch.setenv("BMS_MIGRATION_URL", url)
    assert config_seed.main(ConcurrentStableList([])) == 0
    assert "新增" in capsys.readouterr().out


# ---- rbac-grant 入口（真实授权写入）----


async def test_seed_rbac_grants_entry_writes_grants(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`seed_rbac_grants_entry`：角色就绪后写入授权（缺码计入 missing_codes 而不中断）。"""
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'rg_platform.db'}"
    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'rg.db'}"
    await _prepare_platform_db(platform_url)
    monkeypatch.setattr(rbac_seed, "_resolve_platform_url", lambda _url, *, service: platform_url)  # type: ignore[reportUnknownLambdaType]
    session = await _session(tenant_url)
    try:
        # 先建角色，再写授权
        await rbac_seed.seed_rbac_roles_entry(session, ConcurrentStableDict())
        await session.commit()
        await rbac_seed.seed_rbac_grants_entry(session, ConcurrentStableDict())
        await session.commit()
        # 平台库无权限码 ⇒ 全部计入缺码、授权行数为 0，但流程不中断
        assert await _count(session, SysRole) == len(rbac_seed.BUILTIN_ADMIN_ROLES)
    finally:
        await session.close()


async def test_seed_rbac_grants_entry_requires_roles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`seed_rbac_grants_entry`：角色不存在 → `ParamError`。"""
    from bms_core.core.exceptions import ParamError

    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'rg2_platform.db'}"
    await _prepare_platform_db(platform_url)
    monkeypatch.setattr(rbac_seed, "_resolve_platform_url", lambda _url, *, service: platform_url)  # type: ignore[reportUnknownLambdaType]
    session = await _session(f"sqlite+aiosqlite:///{tmp_path / 'rg2.db'}")
    try:
        with pytest.raises(ParamError, match="角色不存在"):
            await rbac_seed.seed_rbac_grants_entry(session, ConcurrentStableDict())
    finally:
        await session.close()


# ---- platform-grant 入口（真实授权写入）----


async def test_seed_platform_grants_entry_writes_grants(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`seed_platform_grants_entry`：角色就绪后写授权（平台库无码时写 0 行，不中断）。"""
    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'pg2.db'}"
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'pg2_platform.db'}"
    await _prepare_platform_db(platform_url)
    monkeypatch.setattr(platform_seed, "_urls", lambda _code: (tenant_url, platform_url))  # type: ignore[reportUnknownLambdaType]
    session = await _session(tenant_url)
    try:
        await platform_seed.seed_platform_roles_entry(session, ConcurrentStableDict())
        await session.commit()
        await platform_seed.seed_platform_grants_entry(session, ConcurrentStableDict())
        await session.commit()
        assert await _count(session, SysRole) == 2
    finally:
        await session.close()


# ---- 单步命令成功路径（rbac / platform / sso / user）----


def test_seed_platform_main_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`seed_platform.main` 正常路径：打印角色 / 授权 / 绑定计数。"""
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'pm_platform.db'}"
    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'pm.db'}"
    asyncio.run(_prepare_platform_db(platform_url))
    asyncio.run(_prepare_platform_db(tenant_url))
    monkeypatch.setattr(platform_seed, "_urls", lambda _code: (tenant_url, platform_url))  # type: ignore[reportUnknownLambdaType]
    assert platform_seed.main(ConcurrentStableList(["--code", "platform"])) == 0
    out = capsys.readouterr().out
    assert "角色新增" in out
    assert "授权新增" in out


async def test_seed_rbac_main_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`seed_rbac.main` 正常路径：打印落库汇总与缺码清单。"""
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'rm_platform.db'}"
    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'rm.db'}"
    await _prepare_platform_db(platform_url)
    await _prepare_platform_db(tenant_url)
    monkeypatch.setattr(rbac_seed, "_resolve_platform_url", lambda _url, *, service: platform_url)  # type: ignore[reportUnknownLambdaType]
    await rbac_seed.main(
        rbac_seed.build_parser().parse_args(
            ["--tenant", "demo", "--tenant-url", tenant_url, "--platform-url", platform_url]
        )
    )
    out = capsys.readouterr().out
    assert "落库完成" in out
    assert "平台库未登记、已跳过的权限码" in out
