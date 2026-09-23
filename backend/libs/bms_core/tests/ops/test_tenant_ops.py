"""租户运维脚本测试（Kiwi 1019：租户注册种子；批量迁移 / 新租户初始化见 test_migration_ops）。"""

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import ops.seed_tenant as seed_tenant


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

        from ops.seed_tenant import SysTenant  # 归属迁至租户服务：经运维脚本复用声明

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
