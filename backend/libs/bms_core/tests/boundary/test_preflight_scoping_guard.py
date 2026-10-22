"""预检入口护栏用例（Kiwi 2311）：定向档缺省、步骤配置化、预算护栏在配置里登记。

13_05 起预检实现整体迁入 engkit（包内自带 281 条用例、覆盖率 100%），本仓只锁**包装契约**：

1. `check-preflight.py` 只转发、不含推导与步骤清单（单一来源在工具包与 `engkit.toml`）；
2. 仓根 `engkit.toml` 声明了定向 / 全量两档预算与预检步骤（缺省即定向）；
3. 包装能把「位置根 + 选项」翻译成 engkit 参数。
"""

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PREFLIGHT_DIR = _REPO_ROOT / "scripts" / "tools" / "preflight"
_SCRIPT = _PREFLIGHT_DIR / "check-preflight.py"

if str(_PREFLIGHT_DIR) not in sys.path:
    sys.path.insert(0, str(_PREFLIGHT_DIR))


def _load_wrapper() -> object:
    """按文件路径加载预检包装模块。

    Returns:
        object: 模块对象。
    """
    spec = importlib.util.spec_from_file_location("check_preflight_wrapper", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_wrapper_forwards_with_positional_root() -> None:
    """位置根被翻译为 `--root`，选项原样保留。"""
    wrapper = _load_wrapper()
    argv = wrapper.build_argv(["/repo", "--fast", "--jobs", "auto", "--self-test"])
    assert argv[:2] == ["preflight", "--config"]
    assert "--root" in argv and "/repo" in argv
    assert "--fast" in argv and "--jobs" in argv and "auto" in argv
    assert argv[-1] == "--self-test"


def test_wrapper_has_no_derivation_logic() -> None:
    """包装内不得出现推导 / 步骤清单（单一来源约束）。"""
    source = _SCRIPT.read_text(encoding="utf-8")
    for token in ("ast.parse", "pytest-args", "cov_modules", "_ROOTS", "check-base.py", "ruff check"):
        assert token not in source


def test_config_declares_steps_and_budgets() -> None:
    """仓配置登记了预检步骤、自测与两档预算。"""
    sys.path.insert(0, str(_PREFLIGHT_DIR))
    from engkit_boot import config_path

    from engkit.config import load

    cfg = load(Path(config_path()))
    assert cfg.preflight.budget.scoped == (300.0, 420.0)
    assert cfg.preflight.budget.full == (900.0, 1800.0)
    assert cfg.preflight.since == "origin/main"
    kinds = {step.type for step in cfg.preflight.steps}
    assert {"command", "scoped_tests", "full_tests", "project_tests"} <= kinds
    assert len(cfg.preflight.self_tests) == 7
    scoped = [step for step in cfg.preflight.steps if step.preset == "scoped"]
    assert [step.type for step in scoped] == ["scoped_tests"]


def test_config_registers_all_projects() -> None:
    """自动发现的工程全部登记到全量范围与覆盖率范围（新增工程必登记）。"""
    sys.path.insert(0, str(_PREFLIGHT_DIR))
    from engkit_boot import config_path

    from engkit import selection
    from engkit.config import load

    cfg = load(Path(config_path()))
    assert selection.unregistered_projects(selection.discover_projects(cfg), cfg) == []
