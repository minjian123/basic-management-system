"""服务目录种子脚本测试（Kiwi 1050 / 2162）：幂等 upsert / 既有行补齐 / dry-run / URL 解析复用。"""

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import ops.seed_module as seed_module
from bms_core.services.module_registry import SERVICE_CATALOG
from bms_platform.models.catalog import SysModule


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
    """种子幂等：首建 16 行；重复执行 0 / 0；既有行补齐服务维度字段。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    assert await seed_module.seed_modules(url) == (len(SERVICE_CATALOG), 0)
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


@pytest.mark.kiwi_id(2162)
def test_seed_module_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI：dry-run 输出种子清单；正式执行输出新增 / 更新行数。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    assert seed_module.main(["--url", url, "--dry-run"]) == 0
    out = capsys.readouterr().out
    for module in SERVICE_CATALOG:
        assert module.module_key in out
    assert seed_module.main(["--url", url]) == 0
    assert f"新增 {len(SERVICE_CATALOG)} 行 / 更新 0 行" in capsys.readouterr().out
    assert seed_module.main(["--url", url]) == 0
    assert "新增 0 行 / 更新 0 行" in capsys.readouterr().out
