"""选测入口护栏用例（Kiwi 2316）：CLI 输出契约与退化显式。

13_05 起推导实现唯一在 engkit（包内 `tests/test_selection_*.py` 覆盖目录同构 / AST 收敛 /
退化 / 扩圈 / 前端闭包），本仓只锁**包装契约与输出格式**：

1. 包装把位置根翻译为 `--root`，五种 `--format` 与 `changed-services` 保持；
2. 包装内不得出现推导逻辑（单一来源）；
3. 基准不可解析时显式报错（不静默全量）。
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PREFLIGHT_DIR = _REPO_ROOT / "scripts" / "tools" / "preflight"
_SCRIPT = _PREFLIGHT_DIR / "test_selection.py"

for _entry in (_PREFLIGHT_DIR,):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    """以子进程跑包装入口（贴近 CI 调用方式）。

    Args:
        *args: 命令行参数。

    Returns:
        subprocess.CompletedProcess[str]: 执行结果。
    """
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_wrapper_translates_positional_root() -> None:
    """位置根被翻译为 `--root`。"""
    spec = importlib.util.spec_from_file_location("test_selection_wrapper", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    argv = module.build_argv(["/repo", "--changed-from", "origin/main", "--format", "json"])
    assert argv[0] == "selection"
    assert "--root" in argv
    assert "--changed-from" in argv and "origin/main" in argv


def test_wrapper_has_no_derivation_logic() -> None:
    """包装内不得出现推导实现。"""
    source = _SCRIPT.read_text(encoding="utf-8")
    for token in ("ast.parse", "def build_selection", "isomorphic", "_BASE_TEST_THRESHOLD"):
        assert token not in source


def test_json_contract() -> None:
    """`--format json` 字段与类型稳定。"""
    result = _run("--changed-file", "backend/libs/bms_core/src/bms_core/db/bootstrap.py", "--format", "json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert set(payload) >= {"test_paths", "cov_modules", "degraded", "reason", "picked", "total", "projects", "notes"}
    assert payload["cov_modules"] == ["bms_core.db.bootstrap"]
    assert payload["picked"] <= payload["total"]


def test_other_formats() -> None:
    """`pytest-args` / `cov-args` / `projects` / `changed-services` 形态。"""
    changed = ("--changed-file", "backend/services/txn/src/bms_txn/services/recovery.py")
    args = _run(*changed, "--format", "pytest-args")
    assert args.returncode == 0
    assert args.stdout.strip()
    cov = _run(*changed, "--format", "cov-args")
    assert "--cov=bms_txn.services.recovery" in cov.stdout
    projects = _run(*changed, "--format", "projects")
    assert "bms_txn" in projects.stdout
    services = _run(*changed, "--format", "changed-services")
    assert "txn" in services.stdout.split()


def test_frontend_packages_format() -> None:
    """前端包推导输出包名列表。"""
    result = _run(
        "--scope", "frontend", "--changed-file", "frontend/packages/core/src/index.ts", "--format", "packages"
    )
    assert result.returncode == 0, result.stderr
    assert "@bms/core" in result.stdout


def test_bad_ref_is_explicit() -> None:
    """基准不可解析即报错（不静默退化）。"""
    result = _run("--changed-from", "refs/heads/no-such-branch", "--format", "json")
    assert result.returncode == 1
    assert "变更基准不可解析" in result.stderr
