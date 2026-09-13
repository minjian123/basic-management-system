"""租户运维脚本测试（Kiwi 27）：迁移 / 初始化占位。"""

import pytest

import ops.init_tenant as init_tenant
import ops.migrate_tenants as migrate_tenants


@pytest.mark.kiwi_id(27)
def test_migrate_dry_run_lists_fixed_databases(capsys: pytest.CaptureFixture[str]) -> None:
    """--dry-run 输出固定库清单。"""
    assert migrate_tenants.main(["--target", "all", "--db", "mysql", "--dry-run"]) == 0
    out = capsys.readouterr().out
    for name in migrate_tenants.FIXED_DATABASES:
        assert name in out


@pytest.mark.kiwi_id(27)
def test_migrate_targets_and_placeholder(capsys: pytest.CaptureFixture[str]) -> None:
    """目标解析与占位执行分支。"""
    assert migrate_tenants.resolve_databases("platform") == [migrate_tenants.PLATFORM_DB]
    assert migrate_tenants.resolve_databases("tenant_demo") == [migrate_tenants.TENANT_DB]
    assert migrate_tenants.main(["--target", "platform", "--dry-run"]) == 0
    assert migrate_tenants.main([]) == 0
    assert "落库阶段" in capsys.readouterr().out


@pytest.mark.kiwi_id(27)
def test_init_tenant(capsys: pytest.CaptureFixture[str]) -> None:
    """初始化占位：dry-run 输出步骤；非 dry-run 提示归属。"""
    assert init_tenant.main(["--code", "demo", "--dry-run"]) == 0
    out = capsys.readouterr().out
    for step in init_tenant.STEPS:
        assert step in out
    assert init_tenant.main([]) == 0
    assert "落库阶段" in capsys.readouterr().out
