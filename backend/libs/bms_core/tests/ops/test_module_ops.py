"""服务目录与产品档案种子脚本测试（Kiwi 1050 / 2162 / 2249）：幂等 upsert / 既有行补齐 / dry-run / URL 解析复用。"""

from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import ops.seed_module as seed_module
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.platform.catalog import SysModule, SysProduct
from bms_core.services.module_registry import PRODUCT_CATALOG, SERVICE_CATALOG

_TOTAL_SEEDS = len(SERVICE_CATALOG) + len(PRODUCT_CATALOG)
"""种子总行数（服务目录 + 产品档案）。"""


async def test_check_modules_reports_empty_and_drift(tmp_path: Path) -> None:
    """引导性校验：已建表但空库 → 两侧为空提示；写入后一致 → 无明细；改行 → 漂移明细。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'check.db'}"
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(cast("Table", SysModule.__table__).create, checkfirst=True)
            await connection.run_sync(cast("Table", SysProduct.__table__).create, checkfirst=True)
        empty = await seed_module.check_modules(url)
        assert any("服务目录为空" in item for item in empty)
        assert any("产品档案为空" in item for item in empty)

        await seed_module.seed_modules(url)
        assert list(await seed_module.check_modules(url)) == []

        async with factory() as session:
            row = (await session.execute(select(SysModule).where(SysModule.module_key == "sys"))).scalar_one()
            row.name = "被改坏的名字"
            await session.commit()
        drift = await seed_module.check_modules(url)
        assert any("sys" in item for item in drift)
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(1050)
def test_seed_module_resolve_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """URL 解析沿用 seed_tenant 口径（参数 > 环境变量 > 配置）。"""
    assert seed_module.resolve_url("sqlite+aiosqlite:///x.db") == "sqlite+aiosqlite:///x.db"
    monkeypatch.setenv("BMS_MIGRATION_URL", "sqlite+aiosqlite:///env.db")
    assert seed_module.resolve_url() == "sqlite+aiosqlite:///env.db"
    monkeypatch.delenv("BMS_MIGRATION_URL")
    assert seed_module.resolve_url().startswith("sqlite")


@pytest.mark.kiwi_id(2162)
async def test_seed_module_upsert_idempotent(tmp_path: Path) -> None:
    """种子幂等：首建 16 + 3 行；重复执行 0 / 0；既有行补齐服务维度字段。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    assert await seed_module.seed_modules(url) == (_TOTAL_SEEDS, 0)
    assert await seed_module.seed_modules(url) == (0, 0)

    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            statement = select(SysModule.module_key).where(SysModule.deleted_at.is_(None))
            keys = (await session.execute(statement)).scalars().all()
        assert set(keys) == {module.module_key for module in SERVICE_CATALOG}

        # 模拟既有平台域行（无服务维度字段）——upsert 补齐服务标识等字段
        async with factory() as session:
            legacy = (await session.execute(select(SysModule).where(SysModule.module_key == "sys"))).scalar_one()
            legacy.service_key = None
            legacy.service_group = "foundation"
            await session.commit()
        created, updated = await seed_module.seed_modules(url)
        assert (created, updated) == (0, 1)
        async with factory() as session:
            refreshed = (await session.execute(select(SysModule).where(SysModule.module_key == "sys"))).scalar_one()
            assert refreshed.service_key == "platform"
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2249)
async def test_seed_module_products_upsert(tmp_path: Path) -> None:
    """产品档案种子：首建三行；重复 0 / 0；既有行按清单差异回写（状态漂移被纠正）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'product.db'}"
    assert await seed_module.seed_modules(url) == (_TOTAL_SEEDS, 0)
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            statement = select(SysProduct.product_key).where(SysProduct.deleted_at.is_(None))
            keys = (await session.execute(statement)).scalars().all()
        assert set(keys) == {product.product_key for product in PRODUCT_CATALOG}

        async with factory() as session:
            row = (await session.execute(select(SysProduct).where(SysProduct.product_key == "biz"))).scalar_one()
            row.status = "planned"
            await session.commit()
        assert await seed_module.seed_modules(url) == (0, 1)
        async with factory() as session:
            refreshed = (await session.execute(select(SysProduct).where(SysProduct.product_key == "biz"))).scalar_one()
            assert refreshed.status == "enabled"
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2162)
def test_seed_module_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI：dry-run 输出种子清单；默认只做引导性校验；`--write` 才写库（应急口径）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    assert seed_module.main(ConcurrentStableList(["--url", url, "--dry-run"])) == 0
    out = capsys.readouterr().out
    for module in SERVICE_CATALOG:
        assert module.module_key in out
    for product in PRODUCT_CATALOG:
        assert f"产品档案：{product.product_key}" in out
    # 默认：空库 → 引导性校验不通过（写库归注册通道）
    assert seed_module.main(ConcurrentStableList(["--url", url])) == 1
    assert "请先执行迁移并启动平台注册" in capsys.readouterr().out
    # 应急写库 → 写入后再校验通过
    assert seed_module.main(ConcurrentStableList(["--url", url, "--write"])) == 0
    assert f"新增 {_TOTAL_SEEDS} 行 / 更新 0 行" in capsys.readouterr().out
    assert seed_module.main(ConcurrentStableList(["--url", url])) == 0
    assert "引导性校验通过" in capsys.readouterr().out
