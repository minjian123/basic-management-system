# 允许理由：本套用例按路径动态加载包装模块（文件名含连字符，不能直接 import），其属性类型静态不可解析；
# 判定逻辑的严格类型检查在 engkit 侧（`src/engkit/**` 全量 strict）。
# pyright: reportAttributeAccessIssue=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportPrivateUsage=false
"""重命令守卫护栏用例（Kiwi 2330）：拦截判定与放行条件。

13_05 起判定 / 提示 / `.pth` 钩子统一在 engkit（包内 `tests/test_guard.py` 全覆盖），本仓只锁：
包装按本仓 `engkit.toml` 的 `[guard]` 配置判定——预检脚本一律拦、单文件放行、CI / 已包装 / 显式绕过放行。
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PREFLIGHT_DIR = _REPO_ROOT / "scripts" / "tools" / "preflight"
_GUARD_PATH = _PREFLIGHT_DIR / "heavy_command_guard.py"
_BOOT_PATH = _PREFLIGHT_DIR / "heavy_guard_boot.py"

if str(_PREFLIGHT_DIR) not in sys.path:
    sys.path.insert(0, str(_PREFLIGHT_DIR))


def _load(path: Path, name: str) -> object:
    """按文件路径加载模块。

    Args:
        path: 模块文件。
        name: 模块名。

    Returns:
        object: 模块对象。
    """
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def guard_module(monkeypatch: pytest.MonkeyPatch) -> object:
    """加载守卫模块并清空相关环境变量。

    Args:
        monkeypatch: pytest 补丁器。

    Returns:
        object: 守卫模块。
    """
    module = _load(_GUARD_PATH, "bms_heavy_command_guard")
    for name in ("CI", "GITLAB_CI", module.WRAPPED_ENV, module.ALLOW_ENV):
        monkeypatch.delenv(name, raising=False)
    return module


def test_blocks_unwrapped_preflight(guard_module: object) -> None:
    """未包装跑预检脚本即拦截。"""
    argv = [sys.executable, str(_PREFLIGHT_DIR / "check-preflight.py")]
    assert guard_module.should_block(argv) == "script"
    assert guard_module.ALLOW_ENV in guard_module.guidance("script")


def test_allows_single_file_pytest(guard_module: object, tmp_path: Path) -> None:
    """单文件 pytest 放行（秒级不属重命令）。"""
    target = tmp_path / "test_one.py"
    target.write_text("def test_one():\n    assert True\n", encoding="utf-8")
    assert guard_module.should_block(["pytest", str(target)]) == ""


def test_blocks_directory_pytest(guard_module: object) -> None:
    """目录覆盖的用例数超阈值即拦截（本仓测试目录远超 20 个文件）。"""
    assert guard_module.should_block(["pytest", "libs/bms_core/tests"]) == "pytest"


def test_allows_narrow_scanner(guard_module: object) -> None:
    """扫描单个包目录放行；扫仓库级目录拦截。"""
    assert guard_module.should_block(["pyright", "libs/bms_core/src/bms_core/captcha"]) == ""
    assert guard_module.should_block(["ruff", "check", "libs"]) == "ruff"


def test_allows_in_ci(guard_module: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """CI 环境放行。"""
    monkeypatch.setenv("CI", "1")
    assert guard_module.should_block(["pytest"]) == ""


def test_allows_when_wrapped(guard_module: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """已包装放行。"""
    monkeypatch.setenv(guard_module.WRAPPED_ENV, "1")
    assert guard_module.should_block(["pytest"]) == ""


def test_allows_explicit_bypass(guard_module: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """显式绕过放行。"""
    monkeypatch.setenv(guard_module.ALLOW_ENV, "1")
    assert guard_module.should_block(["pytest"]) == ""


def test_boot_delegates_to_engkit() -> None:
    """`.pth` 启动钩子转发到 engkit（不含判定实现）。"""
    boot = _load(_BOOT_PATH, "bms_heavy_guard_boot")
    source = _BOOT_PATH.read_text(encoding="utf-8")
    assert "engkit" in source
    assert "os._exit" not in source
    assert callable(boot.boot) and callable(boot.check)
