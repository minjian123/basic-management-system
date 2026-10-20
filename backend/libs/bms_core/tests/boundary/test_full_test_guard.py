"""全量测试守卫回归（Kiwi 2329）：本地非 CI 环境跑全量立即报错、指定范围与显式声明放行。

守卫落点 `scripts/tools/preflight/full_test_guard.py`，由 `backend/bms_testing_plugin.py` 在
`pytest_configure` 最早期调用。本用例直接对守卫的纯函数断言（不真跑子进程 pytest，避免递归）：

- **拦截**：本地（无 CI 标识）+ 无位置参数 + 无收窄选项 + 无 `--full` + 无 `BMS_ALLOW_FULL_TESTS`；
- **放行**：CI 标识 / `--full` / `BMS_ALLOW_FULL_TESTS=1` / 位置参数（测试文件 / 目录 / 节点 id）/
  收窄选项（`-k` / `-m` / `--lf` / `--ff` / `--deselect` / `--changed-file-list`）；
- **提示**：拦截提示含定向命令 `run-selected.py` 与显式全量的两种写法。
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[5]
_GUARD_PATH = _REPO_ROOT / "scripts" / "tools" / "preflight" / "full_test_guard.py"
"""守卫模块路径（`scripts/tools/preflight/full_test_guard.py`）。"""

_spec = importlib.util.spec_from_file_location("full_test_guard", _GUARD_PATH)
assert _spec is not None and _spec.loader is not None
guard = importlib.util.module_from_spec(_spec)
sys.modules["full_test_guard"] = guard
_spec.loader.exec_module(guard)

pytestmark = pytest.mark.kiwi_id(2329)

_CI_ENVS = guard.CI_ENVS


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """隔离 CI / 显式全量环境变量（避免宿主机 CI 标识影响判定）。"""
    for name in _CI_ENVS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv(guard.ALLOW_ENV, raising=False)


def test_blocks_bare_full_run() -> None:
    """本地裸跑（无位置参数 / 无收窄选项 / 无显式声明）⇒ 拦截。"""
    assert guard.should_block([]) is True
    assert guard.should_block(["-q", "--no-header"]) is True


@pytest.mark.parametrize("scope", ["libs/bms_core/tests", "libs/bms_core/tests/core", "tests/x.py::test_y"])
def test_allows_positional_scope(scope: str) -> None:
    """位置参数（目录 / 文件 / 节点 id）⇒ 放行。"""
    assert guard.should_block([scope]) is False
    assert guard.should_block(["-q", scope]) is False


@pytest.mark.parametrize("option", ["-k", "-m", "--lf", "--ff", "--deselect", "--changed-file-list"])
def test_allows_narrowing_options(option: str) -> None:
    """收窄选项（含 `--opt=value` 形态）⇒ 放行。"""
    assert guard.should_block([f"{option}=value"]) is False
    assert guard.should_block([option, "value"]) is False


def test_allows_explicit_full_flag() -> None:
    """显式 `--full` ⇒ 放行。"""
    assert guard.should_block(["--full"]) is False
    assert guard.should_block(["--full", "-q"]) is False


def test_allows_allow_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """`BMS_ALLOW_FULL_TESTS=1` ⇒ 放行。"""
    monkeypatch.setenv(guard.ALLOW_ENV, "1")
    assert guard.should_block([]) is False


@pytest.mark.parametrize("ci_env", _CI_ENVS)
def test_allows_ci(monkeypatch: pytest.MonkeyPatch, ci_env: str) -> None:
    """任一 CI 标识存在 ⇒ 放行（CI 全量是职责）。"""
    monkeypatch.setenv(ci_env, "true")
    assert guard.should_block([]) is False


def test_guidance_mentions_selected_and_full() -> None:
    """拦截提示含定向命令与显式全量两种写法（可操作，不是单纯拒绝）。"""
    text = guard.guidance(_REPO_ROOT)
    assert "run-selected.py" in text
    assert "--full" in text
    assert guard.ALLOW_ENV in text
    assert "变更驱动" in text


def test_changed_file_count_non_negative() -> None:
    """变更文件数为非负整数（git 不可用时为 0，不阻断判定）。"""
    assert guard.changed_file_count(_REPO_ROOT) >= 0
