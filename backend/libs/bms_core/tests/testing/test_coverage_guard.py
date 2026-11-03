"""覆盖率入口守卫（Kiwi 2404）：走错入口立即退出，不执行任何用例。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from _pytest.outcomes import Exit

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing import coverage_guard
from bms_core.testing.coverage_guard import assert_entrypoint, expected_data_dir

pytestmark = [pytest.mark.kiwi_id(2404)]


def _config(*args: str) -> Any:
    """构造带命令行参数的 pytest 配置替身。

    Args:
        *args: 原始命令行参数。

    Returns:
        Any: 配置替身。
    """
    return SimpleNamespace(invocation_params=SimpleNamespace(args=ConcurrentStableList(args)))


def test_clean_entrypoint_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常入口（无 --cov、落点正确）不拦截。"""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("BMS_COVERAGE_ENTRY_BYPASS", raising=False)
    monkeypatch.delenv("COVERAGE_FILE", raising=False)
    monkeypatch.delenv("BMS_COVERAGE_DATA", raising=False)
    assert_entrypoint(_config("-q", "libs/bms_core/tests/i18n/test_i18n.py"))


def test_pytest_cov_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """`pytest --cov` 立即退出（禁止手工采集）。"""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("BMS_COVERAGE_ENTRY_BYPASS", raising=False)
    with pytest.raises(Exit):
        assert_entrypoint(_config("-q", "--cov=bms_core"))


def test_cov_report_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """`--cov-report` 同样拦（变体不得漏网）。"""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("BMS_COVERAGE_ENTRY_BYPASS", raising=False)
    with pytest.raises(Exit):
        assert_entrypoint(_config("--cov-report=term-missing"))


def test_misplaced_coverage_file_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """`COVERAGE_FILE` 指向门禁目录之外立即退出。"""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("BMS_COVERAGE_ENTRY_BYPASS", raising=False)
    expected = expected_data_dir()
    assert expected is not None
    monkeypatch.setenv("COVERAGE_FILE", str(expected.parent / "elsewhere" / ".coverage"))
    with pytest.raises(Exit):
        assert_entrypoint(_config("-q"))


def test_legit_data_env_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """`BMS_COVERAGE_DATA` 与配置同目录时放行（预检 / 门禁链路的正常形态）。"""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("BMS_COVERAGE_ENTRY_BYPASS", raising=False)
    monkeypatch.delenv("COVERAGE_FILE", raising=False)
    expected = expected_data_dir()
    assert expected is not None
    monkeypatch.setenv("BMS_COVERAGE_DATA", str(expected / ".coverage"))
    assert_entrypoint(_config("-q"))


def test_ci_and_bypass_are_exempt(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI 与排障逃生口放行（CI 需 `--cov-json` 产出显式证据）。"""
    monkeypatch.delenv("BMS_COVERAGE_ENTRY_BYPASS", raising=False)
    monkeypatch.setenv("CI", "true")
    assert_entrypoint(_config("--cov-json=backend/coverage.json"))
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("BMS_COVERAGE_ENTRY_BYPASS", "1")
    assert_entrypoint(_config("--cov=bms_core"))


def test_expected_data_dir_from_config() -> None:
    """合法落点目录来自 `[coverage].data_file`（不写死）。"""
    expected = expected_data_dir()
    assert expected is not None
    assert expected.name == "coverage"
    assert expected.parts[-2:] == (".cache", "coverage")


def test_missing_or_broken_config_skips_location_check(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """配置缺失 / 损坏 / 无 `data_file`：视为不可判定，跳过落点校验（不误伤单仓）。"""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("BMS_COVERAGE_ENTRY_BYPASS", raising=False)
    monkeypatch.setattr(coverage_guard, "_REPO_ROOT", tmp_path)
    assert expected_data_dir() is None

    (tmp_path / "engkit.toml").write_text("[[[", encoding="utf-8")
    assert expected_data_dir() is None

    (tmp_path / "engkit.toml").write_text("[coverage]\nfail_under = 100\n", encoding="utf-8")
    assert expected_data_dir() is None

    monkeypatch.setenv("COVERAGE_FILE", str(tmp_path / "elsewhere" / ".coverage"))
    assert_entrypoint(_config("-q"))
