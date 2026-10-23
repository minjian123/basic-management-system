# 允许理由：本套用例按路径动态加载包装模块（文件名含连字符，不能直接 import），其属性类型静态不可解析；
# 判定逻辑的严格类型检查在 engkit 侧（`src/engkit/**` 全量 strict）。
# pyright: reportAttributeAccessIssue=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportPrivateUsage=false
"""并行执行与重复面护栏用例（Kiwi 2318）：开关映射、预算登记、自测登记、重复面判定接线。

13_02 的实现在 13_05 迁入 engkit（包内 `tests/test_preflight.py` 覆盖全部分支），本仓锁**配置与接线**：

- `--jobs` 映射（auto / 正整数 / off）经包装取同一份实现；
- 预算两档在 `engkit.toml` 登记且与实测标定一致；
- 7 项护栏自测全部登记且含脚本自身依赖；
- `service-test` 仍以 `--format changed-services` 判定重复面（不因迁移放宽）。
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PREFLIGHT_DIR = _REPO_ROOT / "scripts" / "tools" / "preflight"
_PARALLEL = _PREFLIGHT_DIR / "parallel_jobs.py"

if str(_PREFLIGHT_DIR) not in sys.path:
    sys.path.insert(0, str(_PREFLIGHT_DIR))


def _load(name: str, path: Path) -> object:
    """按路径加载模块（文件名含连字符时不能直接 import）。

    Args:
        name: 模块名。
        path: 文件路径。

    Returns:
        object: 模块对象。
    """
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def parallel() -> object:
    """并行档位包装模块。

    Returns:
        object: 模块对象。
    """
    return _load("bms_parallel_jobs", _PARALLEL)


def test_jobs_mapping(parallel: object) -> None:
    """`auto` → `-n auto`、正整数 → `-n N`、`off` → 串行。"""
    assert tuple(parallel.jobs_args("auto")) == ("-n", "auto")
    assert tuple(parallel.jobs_args("4")) == ("-n", "4")
    assert tuple(parallel.jobs_args("off")) == ()
    assert "并行" in parallel.describe("auto")
    assert "串行" in parallel.describe("off")
    with pytest.raises(ValueError, match="取值非法"):
        parallel.jobs_args("abc")


def test_budget_registered() -> None:
    """预算两档与实测标定一致（定向 300/420、全量 900/1800）。"""
    from engkit.config import load
    from engkit_boot import config_path

    cfg = load(Path(config_path()))
    assert cfg.preflight.budget.scoped == (300.0, 420.0)
    assert cfg.preflight.budget.full == (900.0, 1800.0)
    assert cfg.preflight.budget.full[0] > cfg.preflight.budget.scoped[0]


def test_self_tests_registered() -> None:
    """7 项护栏自测全部登记，且依赖含脚本自身。"""
    from engkit.config import load
    from engkit_boot import config_path

    cfg = load(Path(config_path()))
    entries = cfg.preflight.self_tests
    assert len(entries) == 7
    for entry in entries:
        assert entry.deps
        assert entry.deps[0] in entry.cmd[1] or entry.deps[0].endswith(".py")


def test_service_test_keeps_changed_services_gate() -> None:
    """服务子流水线仍以 `--format changed-services` 判定重复面（迁移未放宽）。"""
    template = (_REPO_ROOT / "deploy" / "ci" / "templates" / "backend-service.yml").read_text(encoding="utf-8")
    assert "--format changed-services" in template
    assert "test_selection.py" in template


def test_run_selected_exposes_jobs_and_rounds() -> None:
    """执行器仍接受 `--jobs` / `--max-rounds`（并行与扩圈开关未回退）。"""
    source = (_PREFLIGHT_DIR / "run-selected.py").read_text(encoding="utf-8")
    assert "run-selected" in source
    from engkit.cli import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["run-selected", "--jobs", "4", "--max-rounds", "1", "--no-cov"])
    assert args.jobs == "4"
    assert args.max_rounds == 1
    assert args.cov is False
