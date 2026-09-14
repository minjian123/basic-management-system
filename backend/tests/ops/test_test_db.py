"""三库测试库流程脚本测试（Kiwi 67）：固定库清单、占位口径、与 CI 变量一致、退出码。"""

from pathlib import Path

import pytest

from ops.test_db import (
    ENGINE_CHOICES,
    FLOW_STEPS,
    PLACEHOLDER_NOTICE,
    TEST_DATABASES,
    main,
    resolve_test_database,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CI_FILE = REPO_ROOT / ".gitlab-ci.yml"


@pytest.mark.kiwi_id(67)
@pytest.mark.parametrize("engine", ENGINE_CHOICES)
def test_plan_lists_fixed_database(engine: str, capsys: pytest.CaptureFixture[str]) -> None:
    """`plan` 输出固定库名与四个流程步骤（无副作用，退出码 0）。"""
    assert main(["plan", "--engine", engine]) == 0
    out = capsys.readouterr().out
    assert TEST_DATABASES[engine] in out
    for step in FLOW_STEPS:
        assert f"{step}（plan）" in out


@pytest.mark.kiwi_id(67)
def test_database_names_match_ci_variables() -> None:
    """库清单为唯一事实源：与 `.gitlab-ci.yml` 的 `BMS_TEST_DB_URL` 库名逐字一致（防两处漂移）。"""
    ci = CI_FILE.read_text(encoding="utf-8")
    assert "BMS_TEST_DB_URL" in ci
    for database in TEST_DATABASES.values():
        assert f"/{database}" in ci or f":{database}" in ci, f"{database} 未出现在 CI 变量中"


@pytest.mark.kiwi_id(67)
@pytest.mark.parametrize("command", ("create", "migrate", "drop"))
def test_commands_are_plan_mode_without_execute(command: str, capsys: pytest.CaptureFixture[str]) -> None:
    """不带 `--execute` 时为计划模式：打印库名与步骤，不产生副作用。"""
    assert main([command, "--engine", "mysql"]) == 0
    out = capsys.readouterr().out
    assert "bms_test_mysql" in out
    assert FLOW_STEPS[0] in out
    assert PLACEHOLDER_NOTICE not in out


@pytest.mark.kiwi_id(67)
@pytest.mark.parametrize("command", ("create", "migrate", "drop"))
def test_execute_is_placeholder_only(command: str, capsys: pytest.CaptureFixture[str]) -> None:
    """带 `--execute` 时仅打印占位提示（不建库 / 不迁移 / 不删库），退出码 0。"""
    assert main([command, "--engine", "dm8", "--execute"]) == 0
    out = capsys.readouterr().out
    assert TEST_DATABASES["dm8"] in out
    assert PLACEHOLDER_NOTICE in out


@pytest.mark.kiwi_id(67)
def test_invalid_engine_exits_two() -> None:
    """非法 `--engine` 由 argparse 以退出码 2 结束（与 CI 串联口径一致）。"""
    with pytest.raises(SystemExit) as excinfo:
        main(["plan", "--engine", "sqlite"])
    assert excinfo.value.code == 2


@pytest.mark.kiwi_id(67)
def test_resolve_test_database() -> None:
    """库名解析：三方言映射固定。"""
    assert resolve_test_database("mysql") == "bms_test_mysql"
    assert resolve_test_database("postgres") == "bms_test_pg"
    assert resolve_test_database("dm8") == "BMS_TEST_DM"
