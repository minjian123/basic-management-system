"""预检脚本护栏用例（Kiwi 2311）：默认档定向推导与预算护栏。

《测试规范》「执行方式」节：本地预检以**定向档为缺省**（全量须显式 `--full`），
本用例锁定该口径的两条实现：**按 git 变更推导受影响范围**（测试目录 + 变更源文件覆盖率目标）
与**单步 / 总体预算护栏**（超时即中止，防误跑长命令）。
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from bms_core.core.concurrent import ConcurrentStableList

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SCRIPT = _REPO_ROOT / "scripts" / "tools" / "preflight" / "check-preflight.py"
_spec = importlib.util.spec_from_file_location("check_preflight_guard", _SCRIPT)
assert _spec is not None and _spec.loader is not None
check_preflight = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_preflight)

_BACKEND = _REPO_ROOT / "backend"


@pytest.mark.kiwi_id(2311)
def test_scope_targets_maps_changed_paths() -> None:
    """变更 → 范围映射：基座 / 服务 / ops 各自落到对应测试目录，覆盖率只取包内源文件。"""
    dirs, covs = check_preflight._scope_targets(
        _BACKEND,
        ConcurrentStableList(
            [
                "backend/libs/bms_core/src/bms_core/db/bootstrap.py",
                "backend/libs/bms_core/tests/boundary/test_preflight_scoping_guard.py",
                "backend/services/txn/src/bms_txn/services/recovery.py",
                "backend/ops/test_db.py",
            ]
        ),
    )
    assert list(dirs) == ["libs/bms_core/tests", "services/txn/tests", "libs/bms_core/tests/ops"]
    assert list(covs) == ["bms_core.db.bootstrap", "bms_txn.services.recovery"]


@pytest.mark.kiwi_id(2311)
def test_scope_targets_skips_docs_and_frontend() -> None:
    """纯文档 / 前端变更不引测试目录与覆盖率目标（定向档跳过 pytest）。"""
    dirs, covs = check_preflight._scope_targets(
        _BACKEND,
        ConcurrentStableList(["bms文档/规范/测试规范.md", "frontend/apps/portal/src/main.ts"]),
    )
    assert not dirs
    assert not covs


@pytest.mark.kiwi_id(2311)
def test_scope_targets_ignores_non_package_sources() -> None:
    """覆盖率只取包内源文件：`ops` / `scripts/tools` 变更不产生覆盖率目标（与聚合档 `--cov` 口径一致）。"""
    dirs, covs = check_preflight._scope_targets(
        _BACKEND,
        ConcurrentStableList(
            [
                "backend/ops/test_db.py",
                "scripts/tools/preflight/check-preflight.py",
                "backend/libs/bms_core/src/bms_core/db/__init__.py",
            ]
        ),
    )
    assert list(dirs) == ["libs/bms_core/tests/ops", "libs/bms_core/tests"]
    assert list(covs) == ["bms_core.db"]


@pytest.mark.kiwi_id(2311)
def test_budget_guard_exhausted_skips_remaining(monkeypatch: pytest.MonkeyPatch) -> None:
    """预算护栏：总体预算耗尽即中止并记失败项；后续步骤直接跳过、不重复记。"""
    guard = check_preflight._Budget(step_seconds=0.0, total_seconds=0.0)
    monkeypatch.setattr(check_preflight, "_GUARD", guard)
    failures: ConcurrentStableList[str] = ConcurrentStableList()
    cmd = ConcurrentStableList([sys.executable, "-c", "pass"])

    assert check_preflight._run("步骤一", cmd, _REPO_ROOT, failures) is False
    assert guard.exhausted
    assert len(failures) == 1
    assert "总体超时" in failures[0]

    assert check_preflight._run("步骤二", cmd, _REPO_ROOT, failures) is False
    assert len(failures) == 1


@pytest.mark.kiwi_id(2311)
def test_budget_guard_step_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """预算护栏：单步超时即中止（子进程被结束）并记失败项。"""
    guard = check_preflight._Budget(step_seconds=0.05, total_seconds=60.0)
    monkeypatch.setattr(check_preflight, "_GUARD", guard)
    failures: ConcurrentStableList[str] = ConcurrentStableList()
    cmd = ConcurrentStableList([sys.executable, "-c", "import time; time.sleep(5)"])

    assert check_preflight._run("慢步骤", cmd, _REPO_ROOT, failures) is False
    assert len(failures) == 1
    assert "单步超时" in failures[0]
    assert not guard.exhausted


@pytest.mark.kiwi_id(2311)
def test_budget_guard_allows_fast_step(monkeypatch: pytest.MonkeyPatch) -> None:
    """预算护栏：预算内的步骤照常通过（不影响正常快路径）。"""
    guard = check_preflight._Budget(step_seconds=30.0, total_seconds=60.0)
    monkeypatch.setattr(check_preflight, "_GUARD", guard)
    failures: ConcurrentStableList[str] = ConcurrentStableList()
    cmd = ConcurrentStableList([sys.executable, "-c", "print('ok')"])

    assert check_preflight._run("快步骤", cmd, _REPO_ROOT, failures) is True
    assert not failures
    assert not guard.exhausted


@pytest.mark.kiwi_id(2311)
def test_mode_defaults_and_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """档位与参数解析：缺省定向档（窄预算）、`--full` 放宽预算、`--self-test` 走自测、选项值不当仓库根。"""
    monkeypatch.setattr(sys, "argv", ["check-preflight.py", "/repo", "--budget-seconds", "42", "--step-seconds", "7"])
    assert check_preflight._positional_root() == "/repo"
    assert check_preflight._numeric_flag("--budget-seconds", 180.0) == 42.0
    assert check_preflight._numeric_flag("--step-seconds", 120.0) == 7.0

    monkeypatch.setattr(sys, "argv", ["check-preflight.py", "--budget-seconds", "abc"])
    assert check_preflight._numeric_flag("--budget-seconds", 180.0) == 180.0

    monkeypatch.setattr(sys, "argv", ["check-preflight.py"])
    assert check_preflight._positional_root() == "."
    assert check_preflight._numeric_flag("--budget-seconds", 180.0) == 180.0

    assert check_preflight._DEFAULT_SCOPED_BUDGET == (120.0, 180.0)
    assert check_preflight._DEFAULT_FULL_BUDGET == (600.0, 1200.0)
    assert check_preflight._DEFAULT_FULL_BUDGET[0] > check_preflight._DEFAULT_SCOPED_BUDGET[0]
