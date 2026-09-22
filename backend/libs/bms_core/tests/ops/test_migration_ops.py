"""批量迁移 / 新租户初始化 / 库级建删用例（Kiwi 1078）：清单预演、幂等、失败汇总与三步初始化。"""

import sqlite3
from pathlib import Path

import pytest

import ops.db_admin as db_admin
import ops.init_tenant as init_tenant
import ops.migrate_tenants as migrate_tenants
from bms_core.core.config import get_settings


def _prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把租户库（按模板每租户一文件）与归档库指向临时目录并刷新配置。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/tenant_{{tenant}}.db")
    monkeypatch.setenv("BMS_DATABASE__ARCHIVE__URL", f"sqlite+aiosqlite:///{tmp_path}/archive.db")
    get_settings.cache_clear()


def _revisions(path: Path) -> list[str]:
    """取库文件 `alembic_version` 版本列表。

    Args:
        path: 库文件路径。

    Returns:
        list[str]: 版本号列表。
    """
    connection = sqlite3.connect(path)
    try:
        return [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")]
    finally:
        connection.close()


@pytest.mark.kiwi_id(1078)
def test_migrate_dry_run_lists_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--dry-run` 输出清单（平台 + 各租户 + 归档），不建连、不建文件。"""
    _prepare(tmp_path, monkeypatch)
    assert migrate_tenants.main(["--target", "all", "--dry-run"]) == 0
    out = capsys.readouterr().out
    for label in ("platform", "tenant_demo", "tenant_acme", "archive", "dry-run"):
        assert label in out
    assert not (tmp_path / "tenant_demo.db").exists()


@pytest.mark.kiwi_id(1078)
def test_migrate_dry_run_never_connects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--dry-run` 不建连：平台库指向不可达地址（MySQL）仍正常输出并退出 0。"""
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", "mysql+aiomysql://u:p@127.0.0.1:3306/bms_platform")
    get_settings.cache_clear()
    assert migrate_tenants.main(["--target", "platform", "--dry-run"]) == 0
    assert "dry-run" in capsys.readouterr().out


@pytest.mark.kiwi_id(1078)
def test_migrate_tenants_idempotent_and_single_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """各租户库迁移：首跑成功、重跑「已是最新」；单库（platform / archive）同理。"""
    _prepare(tmp_path, monkeypatch)
    assert migrate_tenants.main(["--target", "tenants"]) == 0
    out = capsys.readouterr().out
    assert "汇总：成功 2、跳过 0、失败 0" in out
    assert _revisions(tmp_path / "tenant_demo.db") == ["0001_dict_query_scheme"]
    assert _revisions(tmp_path / "tenant_acme.db") == ["0001_dict_query_scheme"]

    assert migrate_tenants.main(["--target", "tenants"]) == 0
    assert "汇总：成功 0、跳过 2、失败 0" in capsys.readouterr().out

    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    assert migrate_tenants.main(["--target", "platform", "--url", platform_url]) == 0
    assert _revisions(tmp_path / "platform.db") == ["0002_sys_module_catalog"]
    assert "汇总：成功 1、跳过 0、失败 0" in capsys.readouterr().out

    assert migrate_tenants.main(["--target", "archive"]) == 0
    assert "汇总：成功 1、跳过 0、失败 0" in capsys.readouterr().out


@pytest.mark.kiwi_id(1078)
def test_migrate_failure_is_collected_not_fatal(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """单库失败不中断整批：记失败并汇总结论，退出码 1（可幂等重跑补做）。"""
    broken = "sqlite+aiosqlite:////nonexistent_dir_for_drill/bms_migrcheck.db"
    assert migrate_tenants.main(["--target", "tenant", "--url", broken]) == 1
    out = capsys.readouterr().out
    assert "失败" in out
    assert "汇总：成功 0、跳过 0、失败 1" in out


@pytest.mark.kiwi_id(1078)
def test_migrate_requires_url_for_single_tenant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """单租户目标缺 `--url` → 明确报错（不猜测目标库）。"""
    _prepare(tmp_path, monkeypatch)
    assert migrate_tenants.main(["--target", "tenant"]) == 1
    assert "需显式 `--url`" in capsys.readouterr().out


@pytest.mark.kiwi_id(1078)
def test_init_tenant_three_steps_and_idempotent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """新租户初始化：建库 → 迁移 → 种子三步；重复执行幂等（建库跳过 / 迁移最新 / 种子 0 行）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'tenant_acme.db'}"
    assert init_tenant.main(["--code", "acme", "--url", url]) == 0
    out = capsys.readouterr().out
    assert "建库 → 新建" in out
    assert "迁移 tenant 链 → 完成" in out
    assert "种子 → 新增" in out and "新增 0 行" not in out
    assert _revisions(tmp_path / "tenant_acme.db") == ["0001_dict_query_scheme"]

    assert init_tenant.main(["--code", "acme", "--url", url]) == 0
    again = capsys.readouterr().out
    assert "建库 → 已存在（跳过）" in again
    assert "迁移 tenant 链 → 已是最新" in again
    assert "种子 → 新增 0 行" in again


@pytest.mark.kiwi_id(1078)
def test_init_tenant_skip_create_db_and_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`--skip-create-db` 跳过建库（库由 CI / 运维先行建好）；`--dry-run` 只打印计划。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'tenant_skip.db'}"
    assert init_tenant.main(["--code", "skip", "--url", url, "--dry-run"]) == 0
    dry = capsys.readouterr().out
    assert "租户 skip" in dry and "计划：建库" in dry
    assert not (tmp_path / "tenant_skip.db").exists()

    assert init_tenant.main(["--code", "skip", "--url", url, "--skip-create-db"]) == 0
    assert "建库 → 跳过（--skip-create-db）" in capsys.readouterr().out


@pytest.mark.kiwi_id(1078)
def test_db_admin_cli_create_exists_drop(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """库级建删 CLI：create / exists / drop 幂等（SQLite 文件形态）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'bms_migrcheck.db'}"
    assert db_admin.main(["exists", "--url", url]) == 0
    assert "不存在" in capsys.readouterr().out

    assert db_admin.main(["create", "--url", url]) == 0
    assert "新建" in capsys.readouterr().out
    assert (tmp_path / "bms_migrcheck.db").is_file()

    assert db_admin.main(["create", "--url", url]) == 0
    assert "已存在（跳过）" in capsys.readouterr().out

    assert db_admin.main(["exists", "--url", url]) == 0
    assert "存在" in capsys.readouterr().out

    assert db_admin.main(["drop", "--url", url]) == 0
    assert "已删除" in capsys.readouterr().out
    assert db_admin.main(["drop", "--url", url]) == 0
    assert "不存在（跳过）" in capsys.readouterr().out


@pytest.mark.kiwi_id(1078)
def test_db_admin_cli_dry_run_and_illegal_name(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`--dry-run` 只解析打印；非法目标名快速失败（退出码 1）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'x.db'}"
    assert db_admin.main(["create", "--url", url, "--dry-run"]) == 0
    assert "dry-run" in capsys.readouterr().out
    assert not (tmp_path / "x.db").exists()

    assert db_admin.main(["create", "--url", "mysql+aiomysql://u:p@h:3306/db", "--name", "bad;name"]) == 1
    assert "失败" in capsys.readouterr().out
