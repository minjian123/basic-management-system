"""租户运维脚本测试（Kiwi 1019 种子扩展 + Kiwi 38 迁移 / 初始化占位）。"""

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import ops.init_tenant as init_tenant
import ops.migrate_tenants as migrate_tenants
import ops.seed_tenant as seed_tenant


@pytest.mark.kiwi_id(38)
def test_migrate_dry_run_lists_fixed_databases(capsys: pytest.CaptureFixture[str]) -> None:
    """--dry-run 输出固定库清单。"""
    assert migrate_tenants.main(["--target", "all", "--db", "mysql", "--dry-run"]) == 0
    out = capsys.readouterr().out
    for name in migrate_tenants.FIXED_DATABASES:
        assert name in out


@pytest.mark.kiwi_id(38)
def test_migrate_targets_and_placeholder(capsys: pytest.CaptureFixture[str]) -> None:
    """目标解析与占位执行分支。"""
    assert migrate_tenants.resolve_databases("platform") == [migrate_tenants.PLATFORM_DB]
    assert migrate_tenants.resolve_databases("tenant_demo") == [migrate_tenants.TENANT_DB]
    assert migrate_tenants.main(["--target", "platform", "--dry-run"]) == 0
    assert migrate_tenants.main([]) == 0
    assert "落库阶段" in capsys.readouterr().out


@pytest.mark.kiwi_id(38)
def test_init_tenant(capsys: pytest.CaptureFixture[str]) -> None:
    """初始化占位：dry-run 输出步骤；非 dry-run 提示归属。"""
    assert init_tenant.main(["--code", "demo", "--dry-run"]) == 0
    out = capsys.readouterr().out
    for step in init_tenant.STEPS:
        assert step in out
    assert init_tenant.main([]) == 0
    assert "落库阶段" in capsys.readouterr().out


@pytest.mark.kiwi_id(1019)
def test_seed_tenant_resolve_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """URL 解析：参数 > 环境变量 > 配置平台库。"""
    assert seed_tenant.resolve_url("sqlite+aiosqlite:///x.db") == "sqlite+aiosqlite:///x.db"
    monkeypatch.setenv("BMS_MIGRATION_URL", "sqlite+aiosqlite:///env.db")
    assert seed_tenant.resolve_url() == "sqlite+aiosqlite:///env.db"
    monkeypatch.delenv("BMS_MIGRATION_URL")
    assert seed_tenant.resolve_url().startswith("sqlite")


@pytest.mark.kiwi_id(1019)
async def test_seed_tenant_idempotent(tmp_path: Path) -> None:
    """种子幂等：首次建表并写入 demo / acme，重复执行新增 0；重复 code 不重复插入。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    assert await seed_tenant.seed_tenants(url) == len(seed_tenant.TENANT_SEEDS)
    assert await seed_tenant.seed_tenants(url) == 0

    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        from sqlalchemy import func, select

        from app.models.platform import SysTenant

        async with factory() as session:
            total = (await session.execute(select(func.count()).select_from(SysTenant))).scalar_one()
        assert total == len(seed_tenant.TENANT_SEEDS)
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(1019)
def test_seed_tenant_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI：dry-run 输出种子清单；正式执行输出新增行数。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    assert seed_tenant.main(["--url", url, "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "demo" in out
    assert "acme" in out
    assert seed_tenant.main(["--url", url]) == 0
    assert "新增 2 行" in capsys.readouterr().out
