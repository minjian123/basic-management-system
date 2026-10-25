"""批量迁移 / 新租户初始化 / 库级建删用例（Kiwi 1078 / 2305 / 2307）：分链清单、幂等、失败汇总与三步初始化。"""

from pathlib import Path

import pytest

import ops.db_admin as db_admin
import ops.init_tenant as init_tenant
import ops.migrate_tenants as migrate_tenants
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.db.migration import MigrationSeries


def _prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把服务库（按模板每服务每租户一文件）、平台服务库与归档库指向临时目录并刷新配置。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
    """
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}.db")
    monkeypatch.setenv(
        "BMS_DATABASE__TENANTS__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/bms_{{service}}_{{tenant}}.db"
    )
    monkeypatch.setenv("BMS_DATABASE__ARCHIVE__URL", f"sqlite+aiosqlite:///{tmp_path}/archive.db")
    get_settings.cache_clear()
    get_settings().app.service = "platform"


async def _current_none(url: str, *, version_table: str = "", schema: str = "") -> str | None:
    """替身：目标库未迁移（版本号 None）。

    Args:
        url: 连接串（忽略）。
        version_table: 版本记录表名（忽略）。
        schema: 模式名（忽略）。

    Returns:
        str | None: None。
    """
    del url, version_table, schema
    return None


async def _current_head(url: str, *, version_table: str = "", schema: str = "") -> str | None:
    """替身：目标库已达清单头。

    Args:
        url: 连接串（忽略）。
        version_table: 版本记录表名（忽略）。
        schema: 模式名（忽略）。

    Returns:
        str | None: 清单头版本号。
    """
    del url, version_table, schema
    return "0001_demo"


@pytest.mark.kiwi_id(1078)
def test_migrate_dry_run_lists_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--dry-run` 输出「服务 × 数据源 × 租户」清单与库数量统计，不建连、不建文件。"""
    _prepare(tmp_path, monkeypatch)
    assert (
        migrate_tenants.main(
            ConcurrentStableList(["--service", "platform", "--code", "demo", "--code", "acme", "--dry-run"])
        )
        == 0
    )
    out = capsys.readouterr().out
    for label in ("platform_platform", "tenant_platform_demo", "archive", "库数量", "域："):
        assert label in out
    assert not (tmp_path / "bms_platform_demo.db").exists()


@pytest.mark.kiwi_id(1078)
def test_migrate_dry_run_never_connects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--dry-run` 不建连：平台库指向不可达地址（MySQL）仍正常输出并退出 0。"""
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", "mysql+aiomysql://u:p@127.0.0.1:3306/bms_platform")
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL_TEMPLATE", "mysql+aiomysql://u:p@127.0.0.1:3306/{database}")
    get_settings.cache_clear()
    assert (
        migrate_tenants.main(ConcurrentStableList(["--service", "platform", "--target", "platform", "--dry-run"])) == 0
    )
    assert "dry-run" in capsys.readouterr().out


@pytest.mark.kiwi_id(2307)
def test_migrate_tenants_scripts_cleared_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """脚本清空（06_05）：各链输出「无脚本（跳过）」，清单与汇总照常，不建连、不落库文件。"""
    _prepare(tmp_path, monkeypatch)
    args = ["--service", "platform", "--target", "tenants", "--code", "demo", "--code", "acme"]
    assert migrate_tenants.main(ConcurrentStableList(args)) == 0
    out = capsys.readouterr().out
    assert "汇总：成功 0、跳过 2、失败 0" in out
    # 每条清单各自「无脚本（跳过）」：一个库内多域 → 行数 = 域数 × 库数（至少 2 行）
    assert out.count("无脚本（跳过）") >= 2
    assert not (tmp_path / "bms_platform_demo.db").exists()


@pytest.mark.kiwi_id(2307)
def test_migrate_tenants_mechanism_with_temp_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """迁移机制保留（临时链脚本自检）：有脚本链走出「迁移完成」与「已是最新（跳过）」两分支。"""
    _prepare(tmp_path, monkeypatch)
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    def _head(series: MigrationSeries) -> str:
        """替身：该清单恒有脚本（临时清单脚本口径，头 `0001_demo`）。"""
        del series
        return "0001_demo"

    def _upgrade(series: MigrationSeries, url: str, *, schema: str = "") -> None:
        """替身：记录升级调用（不真跑 Alembic）。"""
        del url, schema
        calls.add(series.name)

    monkeypatch.setattr(migrate_tenants, "head_revision", _head)
    monkeypatch.setattr(migrate_tenants, "current_revision", _current_none)
    monkeypatch.setattr(migrate_tenants, "upgrade_series", _upgrade)

    # 替身版本号不在真实清单脚本内（仓库脚本已清空）：版本校验按通过处理，只验机制分支
    def _no_problems(*args: object, **kwargs: object) -> ConcurrentStableList[str]:
        """替身：版本校验恒通过。"""
        del args, kwargs
        return ConcurrentStableList()

    monkeypatch.setattr(migrate_tenants, "check_version_known", _no_problems)
    monkeypatch.setattr(migrate_tenants, "check_monotonic", _no_problems)
    args = ["--service", "platform", "--target", "tenants", "--code", "demo"]
    assert migrate_tenants.main(ConcurrentStableList(args)) == 0
    out = capsys.readouterr().out
    assert "迁移完成" in out
    # 一个库内按域逐条清单执行（platform 单元承载多个域）
    assert "user:tenant" in calls
    assert "platform_registry:tenant" in calls

    monkeypatch.setattr(migrate_tenants, "current_revision", _current_head)
    assert migrate_tenants.main(ConcurrentStableList(args)) == 0
    assert "已是最新（跳过）" in capsys.readouterr().out


@pytest.mark.kiwi_id(2307)
def test_migrate_failure_is_collected_not_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """单库失败不中断整批：记失败并汇总结论，退出码 1（可幂等重跑补做）。"""
    _prepare(tmp_path, monkeypatch)

    def _head(series: MigrationSeries) -> str:
        """替身：该清单恒有脚本（临时清单脚本口径）。"""
        del series
        return "0001_demo"

    def _boom(series: MigrationSeries, url: str, *, schema: str = "") -> None:
        """替身：升级即失败。"""
        del series, url, schema
        raise RuntimeError("drill")

    monkeypatch.setattr(migrate_tenants, "head_revision", _head)
    monkeypatch.setattr(migrate_tenants, "current_revision", _current_none)
    monkeypatch.setattr(migrate_tenants, "upgrade_series", _boom)
    args = ["--service", "platform", "--target", "tenants", "--code", "demo", "--code", "acme"]
    assert migrate_tenants.main(ConcurrentStableList(args)) == 1
    out = capsys.readouterr().out
    assert "失败" in out
    assert "汇总：成功 0、跳过 0、失败 2" in out


@pytest.mark.kiwi_id(1078)
def test_migrate_requires_url_for_single_tenant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """单租户目标缺 `--url` → 明确报错（不猜测目标库）。"""
    _prepare(tmp_path, monkeypatch)
    assert migrate_tenants.main(ConcurrentStableList(["--target", "tenant"])) == 1
    assert "需显式 `--url`" in capsys.readouterr().out


@pytest.mark.kiwi_id(1078)
def test_migrate_requires_tenant_dimension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """批量租户目标缺租户维度（`--code` / `--all-tenants`）→ 明确报错。"""
    _prepare(tmp_path, monkeypatch)
    assert migrate_tenants.main(ConcurrentStableList(["--service", "platform", "--target", "tenants"])) == 1
    assert "需 --code" in capsys.readouterr().out


@pytest.mark.kiwi_id(2305)
def test_init_tenant_three_steps_and_idempotent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """新租户初始化：建库 → 建表 → 种子三步；重复执行幂等（建库跳过 / 表已存在 / 种子 0 行）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'tenant_acme.db'}"
    args = ["--service", "platform", "--code", "acme", "--url", url]
    assert init_tenant.main(ConcurrentStableList(args)) == 0
    out = capsys.readouterr().out
    assert "建库 → 新建" in out
    assert "建表 platform 单元（租户库）→ 新建" in out and "已存在 0" in out
    assert "种子 → 新增" in out and "新增 0 行" not in out

    assert init_tenant.main(ConcurrentStableList(args)) == 0
    again = capsys.readouterr().out
    assert "建库 → 已存在（跳过）" in again
    assert "建表 platform 单元（租户库）→ 新建 0" in again
    assert "种子 → 新增 0 行" in again


@pytest.mark.kiwi_id(1078)
def test_init_tenant_skip_create_db_and_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`--skip-create-db` 跳过建库（库由 CI / 运维先行建好）；`--dry-run` 只打印计划。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'tenant_skip.db'}"
    dry_args = ["--service", "platform", "--code", "skip", "--url", url, "--dry-run"]
    assert init_tenant.main(ConcurrentStableList(dry_args)) == 0
    dry = capsys.readouterr().out
    assert "租户 skip" in dry and "计划：建库" in dry
    assert not (tmp_path / "tenant_skip.db").exists()

    assert (
        init_tenant.main(
            ConcurrentStableList(["--service", "platform", "--code", "skip", "--url", url, "--skip-create-db"])
        )
        == 0
    )
    assert "建库 → 跳过（--skip-create-db）" in capsys.readouterr().out


@pytest.mark.kiwi_id(1078)
def test_init_tenant_requires_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """缺服务标识（`--service` / `[app].service`）→ 快速失败（分链需服务段）。"""
    monkeypatch.delenv("BMS_APP__SERVICE", raising=False)
    get_settings.cache_clear()
    get_settings().app.service = ""
    assert init_tenant.main(ConcurrentStableList(["--code", "acme", "--url", "sqlite+aiosqlite:///:memory:"])) == 1
    get_settings.cache_clear()


@pytest.mark.kiwi_id(1078)
def test_db_admin_cli_create_exists_drop(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """库级建删 CLI：create / exists / drop 幂等（SQLite 文件形态）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'bms_migrcheck.db'}"
    assert db_admin.main(ConcurrentStableList(["exists", "--url", url])) == 0
    assert "不存在" in capsys.readouterr().out

    assert db_admin.main(ConcurrentStableList(["create", "--url", url])) == 0
    assert "新建" in capsys.readouterr().out
    assert (tmp_path / "bms_migrcheck.db").is_file()

    assert db_admin.main(ConcurrentStableList(["create", "--url", url])) == 0
    assert "已存在（跳过）" in capsys.readouterr().out

    assert db_admin.main(ConcurrentStableList(["exists", "--url", url])) == 0
    assert "存在" in capsys.readouterr().out

    assert db_admin.main(ConcurrentStableList(["drop", "--url", url])) == 0
    assert "已删除" in capsys.readouterr().out
    assert db_admin.main(ConcurrentStableList(["drop", "--url", url])) == 0
    assert "不存在（跳过）" in capsys.readouterr().out


@pytest.mark.kiwi_id(1078)
def test_db_admin_cli_dry_run_and_illegal_name(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`--dry-run` 只解析打印；非法目标名快速失败（退出码 1）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'x.db'}"
    assert db_admin.main(ConcurrentStableList(["create", "--url", url, "--dry-run"])) == 0
    assert "dry-run" in capsys.readouterr().out
    assert not (tmp_path / "x.db").exists()

    assert (
        db_admin.main(ConcurrentStableList(["create", "--url", "mysql+aiomysql://u:p@h:3306/db", "--name", "bad;name"]))
        == 1
    )
    assert "失败" in capsys.readouterr().out
