"""模块注册种子脚本测试（Kiwi 1050）：幂等建表与种子 / dry-run / URL 解析复用。"""

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import ops.seed_module as seed_module
from app.models.platform import SysModule
from app.services.module_registry import PLATFORM_MODULES


@pytest.mark.kiwi_id(1050)
def test_seed_module_resolve_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """URL 解析沿用 seed_tenant 口径（参数 > 环境变量 > 配置）。"""
    assert seed_module.resolve_url("sqlite+aiosqlite:///x.db") == "sqlite+aiosqlite:///x.db"
    monkeypatch.setenv("BMS_MIGRATION_URL", "sqlite+aiosqlite:///env.db")
    assert seed_module.resolve_url() == "sqlite+aiosqlite:///env.db"
    monkeypatch.delenv("BMS_MIGRATION_URL")
    assert seed_module.resolve_url().startswith("sqlite")


@pytest.mark.kiwi_id(1050)
async def test_seed_module_idempotent(tmp_path: Path) -> None:
    """种子幂等：首次建表写入平台域四行；重复执行新增 0；键集合与清单一致。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    assert await seed_module.seed_modules(url) == len(PLATFORM_MODULES)
    assert await seed_module.seed_modules(url) == 0

    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            statement = select(SysModule.module_key).where(SysModule.deleted_at.is_(None))
            keys = (await session.execute(statement)).scalars().all()
        assert set(keys) == {module.module_key for module in PLATFORM_MODULES}
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(1050)
def test_seed_module_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI：dry-run 输出种子清单；正式执行输出新增行数。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    assert seed_module.main(["--url", url, "--dry-run"]) == 0
    out = capsys.readouterr().out
    for module in PLATFORM_MODULES:
        assert module.module_key in out
    assert seed_module.main(["--url", url]) == 0
    assert f"新增 {len(PLATFORM_MODULES)} 行" in capsys.readouterr().out
