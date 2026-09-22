"""三库测试库流程脚本测试（Kiwi 1155）：两对象清单 / 与 CI 变量一致 / 建号语句 / 真实执行分支。"""

import sqlite3
from pathlib import Path

import pytest

from bms_core.db.migration import head_revision, resolve_chain
from ops.test_db import (
    ENGINE_CHOICES,
    FLOW_STEPS,
    SCOPE_CHOICES,
    TEST_ACCOUNT,
    TEST_DATABASES,
    TEST_URL_ENV,
    account_statements,
    build_target,
    create,
    drop,
    main,
    migrate,
    resolve_admin_url,
    resolve_test_database,
    resolve_test_url,
)

REPO_ROOT = Path(__file__).resolve().parents[5]
CI_FILE = REPO_ROOT / ".gitlab-ci.yml"

_DM_URL = "dm+dmPython://SYSDBA:secret@192.0.2.10:5236/BMS_TEST_DM"


def _revisions(path: Path) -> list[str]:
    """读 SQLite 库 `alembic_version` 版本行。"""
    connection = sqlite3.connect(path)
    try:
        return [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")]
    finally:
        connection.close()


def _clear_url_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """清空对象连接串环境变量（隔离本地 / CI 注入）。"""
    for name in TEST_URL_ENV.values():
        monkeypatch.delenv(name, raising=False)


@pytest.mark.kiwi_id(1156)
@pytest.mark.parametrize("engine", ENGINE_CHOICES)
def test_two_objects_per_dialect(engine: str) -> None:
    """对象拓扑：每方言平台 / 租户两对象且互异（名称为库名或模式名）。"""
    assert set(TEST_DATABASES[engine]) == {"platform", "tenant"}
    platform = resolve_test_database(engine, "platform")
    tenant = resolve_test_database(engine, "tenant")
    assert platform != tenant
    assert tenant.startswith(platform) or platform.startswith("BMS_TEST")
    assert resolve_test_database(engine) == platform


@pytest.mark.kiwi_id(1156)
def test_database_names_match_ci_variables() -> None:
    """清单为唯一事实源：库名 / 模式名与 `.gitlab-ci.yml` 两变量逐字一致（防两处漂移）。"""
    ci = CI_FILE.read_text(encoding="utf-8")
    for env_name in TEST_URL_ENV.values():
        assert env_name in ci
    for objects in TEST_DATABASES.values():
        for database in objects.values():
            assert f"/{database}" in ci or f":{database}" in ci, f"{database} 未出现在 CI 变量中"


@pytest.mark.kiwi_id(1156)
def test_resolve_url_override_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """连接串解析：显式覆盖 > 环境变量；未配置返回空串。"""
    _clear_url_env(monkeypatch)
    assert resolve_test_url("mysql", "platform") == ""
    assert resolve_test_url("mysql", "tenant", override="mysql+aiomysql://u:p@h:3306/x") == (
        "mysql+aiomysql://u:p@h:3306/x"
    )
    monkeypatch.setenv("BMS_TEST_DB_URL", "mysql+aiomysql://u:p@h:3306/bms_test_mysql")
    monkeypatch.setenv("BMS_TEST_TENANT_DB_URL", "mysql+aiomysql://u:p@h:3306/bms_test_mysql_t1")
    assert resolve_test_url("mysql", "platform").endswith("bms_test_mysql")
    assert resolve_test_url("mysql", "tenant").endswith("bms_test_mysql_t1")


@pytest.mark.kiwi_id(1156)
def test_resolve_admin_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """管理连接串推导：达梦去模式段；MySQL 用 root 且不带库名；缺管理员密码返回空串。"""
    monkeypatch.delenv("MYSQL_ROOT_PASSWORD", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)

    assert resolve_admin_url("dm8", _DM_URL) == "dm+dmPython://SYSDBA:secret@192.0.2.10:5236"
    assert resolve_admin_url("mysql", "mysql+aiomysql://bms_test:pwd@192.0.2.10:3306/bms_test_mysql") == ""
    assert resolve_admin_url("mysql", _DM_URL, override="mysql+aiomysql://root:r@h:3306") == (
        "mysql+aiomysql://root:r@h:3306"
    )

    monkeypatch.setenv("MYSQL_ROOT_PASSWORD", "root-secret")
    admin = resolve_admin_url("mysql", "mysql+aiomysql://bms_test:pwd@192.0.2.10:3306/bms_test_mysql")
    assert admin == "mysql+aiomysql://root:root-secret@192.0.2.10:3306"


@pytest.mark.kiwi_id(1156)
def test_account_statements() -> None:
    """建号语句：MySQL 幂等建号 + 库级 `bms\\_test%` 授权；PostgreSQL / 达梦不在本函数内出语句。"""
    statements = account_statements("mysql", "p'wd")
    assert len(statements) == 2
    assert statements[0].startswith("CREATE USER IF NOT EXISTS 'bms_test'@'%'")
    assert "p''wd" in statements[0]
    assert "GRANT ALL PRIVILEGES ON `bms\\_test%`.*" in statements[1]
    assert account_statements("postgres", "x") == ()
    assert account_statements("dm8", "x") == ()
    assert TEST_ACCOUNT == {"mysql": "bms_test", "postgres": "bms_test", "dm8": "SYSDBA"}


@pytest.mark.kiwi_id(1156)
def test_build_target_dm_strips_schema_segment() -> None:
    """达梦目标：建删模式用去模式段连接串 + 清单内模式名（名称大写归一）。"""
    target = build_target("dm8", "tenant", url=_DM_URL)
    assert target.dialect == "dm"
    assert target.name == "BMS_TEST_DM_T1"
    assert target.url == "dm+dmPython://SYSDBA:secret@192.0.2.10:5236"
    assert target.admin_url == target.url


@pytest.mark.kiwi_id(1156)
@pytest.mark.parametrize("engine", ENGINE_CHOICES)
def test_plan_lists_objects_and_steps(engine: str, capsys: pytest.CaptureFixture[str]) -> None:
    """`plan` 输出两对象与四个流程步骤（无副作用，退出码 0）。"""
    assert main(["plan", "--engine", engine]) == 0
    out = capsys.readouterr().out
    for database in TEST_DATABASES[engine].values():
        assert database in out
    for step in FLOW_STEPS:
        assert f"{step}（plan）" in out


@pytest.mark.kiwi_id(1156)
def test_plan_mode_without_execute_has_no_side_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """不带 `--execute` 为计划模式：不建连、不建库（SQLite 文件不产生）。"""
    db_file = tmp_path / "planned.db"
    monkeypatch.setenv("BMS_TEST_DB_URL", f"sqlite+aiosqlite:///{db_file}")
    monkeypatch.delenv("BMS_TEST_TENANT_DB_URL", raising=False)
    assert main(["create", "--engine", "mysql", "--scope", "platform"]) == 0
    out = capsys.readouterr().out
    assert "（plan）" in out
    assert not db_file.exists()


@pytest.mark.kiwi_id(1156)
def test_execute_without_url_fails(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """`--execute` 但未配置连接串：显式失败（退出码 1），不静默跳过。"""
    _clear_url_env(monkeypatch)
    assert main(["create", "--engine", "mysql", "--execute"]) == 1
    out = capsys.readouterr().out
    assert "未配置" in out
    assert "失败" in out


@pytest.mark.kiwi_id(1156)
def test_invalid_arguments_exit_two() -> None:
    """非法 `--engine` / `--scope` 由 argparse 以退出码 2 结束。"""
    with pytest.raises(SystemExit) as engine_exc:
        main(["plan", "--engine", "sqlite"])
    assert engine_exc.value.code == 2
    with pytest.raises(SystemExit) as scope_exc:
        main(["create", "--engine", "mysql", "--scope", "all2"])
    assert scope_exc.value.code == 2
    assert SCOPE_CHOICES == ("all", "platform", "tenant")


@pytest.mark.kiwi_id(1156)
async def test_sqlite_objects_full_flow(tmp_path: Path) -> None:
    """真实执行（SQLite 代替真库）：建对象 → 分链迁移（幂等）→ 删对象（幂等）。"""
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'tenant.db'}"

    assert await create("mysql", "platform", url=platform_url) is True
    assert await create("mysql", "platform", url=platform_url) is False
    assert await migrate("mysql", "platform", url=platform_url) is True
    assert await migrate("mysql", "platform", url=platform_url) is False
    assert await migrate("mysql", "tenant", url=tenant_url) is True

    assert _revisions(tmp_path / "platform.db") == [head_revision(resolve_chain("platform"))]
    assert _revisions(tmp_path / "tenant.db") == [head_revision(resolve_chain("tenant"))]

    assert await drop("mysql", "platform", url=platform_url) is True
    assert await drop("mysql", "platform", url=platform_url) is False
    assert not (tmp_path / "platform.db").exists()
