# 允许理由：本套用例按路径动态加载包装模块（文件名含连字符，不能直接 import），其属性类型静态不可解析；
# 判定逻辑的严格类型检查在 engkit 侧（`src/engkit/**` 全量 strict）。
# pyright: reportAttributeAccessIssue=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportPrivateUsage=false
"""全量测试守卫护栏用例（Kiwi 2329）：本地非 CI 跑全量须显式声明。

13_05 起判定统一在 engkit（包内 `tests/test_guard.py` 覆盖全部分支），本仓只锁：
`full_test_guard.py` 转发到 engkit、`--full` / 显式环境变量 / CI 三种放行条件成立。
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PREFLIGHT_DIR = _REPO_ROOT / "scripts" / "tools" / "preflight"
_GUARD_PATH = _PREFLIGHT_DIR / "full_test_guard.py"

if str(_PREFLIGHT_DIR) not in sys.path:
    sys.path.insert(0, str(_PREFLIGHT_DIR))


def _load() -> object:
    """加载全量守卫包装模块。

    Returns:
        object: 模块对象。
    """
    spec = importlib.util.spec_from_file_location("bms_full_test_guard", _GUARD_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def guard(monkeypatch: pytest.MonkeyPatch) -> object:
    """加载模块并清空相关环境变量。

    Args:
        monkeypatch: pytest 补丁器。

    Returns:
        object: 模块对象。
    """
    module = _load()
    for name in ("CI", "GITLAB_CI", module.FULL_ENV, "ENGKIT_RUN_ONCE"):
        monkeypatch.delenv(name, raising=False)
    return module


def test_blocks_bare_pytest(guard: object) -> None:
    """无范围、未声明全量即拦截。"""
    assert guard.full_test_should_block([]) is True
    assert guard.FULL_ENV in guard.full_test_guidance()


def test_allows_explicit_scope(guard: object) -> None:
    """指定测试范围即放行。"""
    assert guard.full_test_should_block(["libs/bms_core/tests/boundary/test_x.py"]) is False
    assert guard.full_test_should_block(["-k", "some_case"]) is False


def test_allows_full_flag(guard: object) -> None:
    """`--full` 显式声明放行。"""
    assert guard.full_test_should_block([guard.FULL_FLAG]) is False


def test_allows_env_declaration(guard: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """显式环境变量放行。"""
    monkeypatch.setenv(guard.FULL_ENV, "1")
    assert guard.full_test_should_block([]) is False


def test_allows_in_ci(guard: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """CI 环境放行（CI 跑全量是职责）。"""
    monkeypatch.setenv("CI", "1")
    assert guard.full_test_should_block([]) is False
    assert guard.is_ci() is True


def test_wrapper_forwards_to_engkit() -> None:
    """包装只转发到 engkit（不含判定实现）。"""
    source = _GUARD_PATH.read_text(encoding="utf-8")
    assert "engkit" in source
    assert "has_explicit_scope" not in source
    assert "_SCOPE_OPTIONS" not in source
