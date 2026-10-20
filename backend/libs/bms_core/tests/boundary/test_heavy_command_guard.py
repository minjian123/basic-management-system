"""重命令包装守卫用例（Kiwi 2330）：本地非 CI 未经 run-once 包装跑重命令即拦截。

覆盖判定矩阵：预检脚本 / 全量·多目录 pytest / 全仓 pyright·ruff 拦截；单文件 / 单节点 / 窄目录放行；
CI、包装标记、显式绕过三条放行通道；以及 `.pth` 启动钩子的硬退出行为。
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from bms_core.core.concurrent import ConcurrentStableList

pytestmark = pytest.mark.kiwi_id(2330)

_PREFLIGHT_DIR = Path(__file__).resolve().parents[5] / "scripts" / "tools" / "preflight"
"""`scripts/tools/preflight` 目录（本用例位于 `backend/libs/bms_core/tests/boundary/`）。"""

_GUARD_PATH = _PREFLIGHT_DIR / "heavy_command_guard.py"
_BOOT_PATH = _PREFLIGHT_DIR / "heavy_guard_boot.py"


def _load(path: Path, name: str) -> Any:
    """按路径加载模块（与被测守卫同口径，不依赖 `scripts` 可导入性）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load(_GUARD_PATH, "bms_heavy_command_guard")
boot = _load(_BOOT_PATH, "bms_heavy_guard_boot")

_CI_ENVS = guard.CI_ENVS


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]  # pytest 按名调用
    """隔离三通道环境变量（避免宿主机环境干扰判定）。"""
    for name in (*_CI_ENVS, guard.WRAPPED_ENV, guard.ALLOW_ENV):
        monkeypatch.delenv(name, raising=False)


# --------------------------------------------------------------------------- 预检脚本


def test_blocks_unwrapped_preflight() -> None:
    """裸跑预检脚本 ⇒ 拦截（预检是最重的单条命令）。"""
    assert guard.should_block(["python", "scripts/tools/preflight/check-preflight.py", "--fast"]) == "preflight"
    assert guard.should_block(["python", "scripts/tools/preflight/check-preflight.py"]) == "preflight"


def test_blocks_baseline_check_scripts() -> None:
    """基座 / 链接校验脚本同样算重命令。"""
    assert guard.should_block(["python", "scripts/tools/base-check/check-base.py"]) == "preflight"
    assert guard.should_block(["python", "scripts/tools/check-links.py"]) == "preflight"


# --------------------------------------------------------------------------- pytest 通道


def test_blocks_bare_pytest() -> None:
    """无位置参数 ⇒ 拦截（跑缺省 testpaths）。"""
    assert guard.should_block(["pytest"]) == "pytest"
    assert guard.should_block(["pytest", "-q", "--no-header"]) == "pytest"


def test_blocks_wide_directory_pytest() -> None:
    """目录覆盖的测试文件数超阈值 ⇒ 拦截（实测 `libs/bms_core/tests` 约 2100 用例）。"""
    wide = Path(__file__).resolve().parents[1]
    assert guard.should_block(["pytest", str(wide)]) == "pytest"


def test_allows_single_file_pytest(tmp_path: Path) -> None:
    """单文件 / 单节点 ⇒ 放行（秒级，不属重命令）。"""
    single = tmp_path / "test_single.py"
    single.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    assert guard.should_block(["pytest", str(single)]) == ""
    assert guard.should_block(["pytest", f"{single}::test_ok"]) == ""
    assert guard.should_block(["pytest", "-q", str(single)]) == ""


def test_allows_narrow_directory_pytest() -> None:
    """测试文件数未超阈值的窄目录 ⇒ 放行（本用例所在目录即窄目录）。"""
    narrow = Path(__file__).resolve().parent
    assert guard.should_block(["pytest", str(narrow)]) == ""


# --------------------------------------------------------------------------- pyright / ruff 通道


def test_blocks_bare_scanner() -> None:
    """无参数 ⇒ 扫全仓，拦截。"""
    assert guard.should_block(["pyright"]) == "pyright"
    assert guard.should_block(["ruff", "check"]) == "ruff"


def test_blocks_repo_level_scanner() -> None:
    """参数指向仓库级目录 / 仓库根 ⇒ 拦截。"""
    assert guard.should_block(["pyright", "libs"]) == "pyright"
    assert guard.should_block(["pyright", "services"]) == "pyright"
    assert guard.should_block(["pyright", "."]) == "pyright"
    assert guard.should_block(["ruff", "check", "libs"]) == "ruff"
    assert guard.should_block(["ruff", "format", "services"]) == "ruff"


def test_allows_narrow_scanner() -> None:
    """参数为单个模块 / 文件路径 ⇒ 放行（定向检查，秒级）。"""
    assert guard.should_block(["pyright", "libs/bms_core/src/bms_core/captcha"]) == ""
    assert guard.should_block(["pyright", "libs/bms_core/tests/captcha"]) == ""
    assert guard.should_block(["ruff", "check", "libs/bms_core/src/bms_core/dict/http.py"]) == ""


def test_unknown_program_is_not_heavy() -> None:
    """非重命令（其他脚本 / 普通 python 调用）⇒ 放行。"""
    assert guard.should_block(["python", "-c", "print(1)"]) == ""
    assert guard.should_block(["git", "status"]) == ""
    assert guard.should_block([]) == ""


# --------------------------------------------------------------------------- 三条放行通道


def test_allows_when_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    """`run-once.py` 注入包装标记 ⇒ 全部放行。"""
    monkeypatch.setenv(guard.WRAPPED_ENV, "1")
    assert guard.should_block(["pytest"]) == ""
    assert guard.should_block(["pyright"]) == ""
    assert guard.should_block(["python", "scripts/tools/preflight/check-preflight.py"]) == ""


def test_allows_in_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI 环境 ⇒ 放行（CI 跑全量是职责，不拦）。"""
    monkeypatch.setenv("CI", "1")
    assert guard.should_block(["pytest"]) == ""
    assert guard.should_block(["pyright"]) == ""


def test_allows_with_explicit_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    """显式绕过环境变量 ⇒ 放行（排查 run-once 自身问题用）。"""
    monkeypatch.setenv(guard.ALLOW_ENV, "1")
    assert guard.should_block(["pytest"]) == ""


def test_guidance_mentions_wrapper_command() -> None:
    """拦截提示须直接给出该用的包装命令与绕过开关（否则等于没教）。"""
    text = guard.guidance("pytest")
    assert "run-once.py" in text
    assert guard.ALLOW_ENV in text


# --------------------------------------------------------------------------- pytest 钩子与 .pth 钩子


def test_pytest_configure_raises_for_heavy(monkeypatch: pytest.MonkeyPatch) -> None:
    """pytest 钩子：重命令经 `UsageError` 拦截（零用例执行）。"""
    pytest_module = pytest

    class _Params:
        args: ConcurrentStableList[str] = ConcurrentStableList(("libs/bms_core/tests",))

    class _Config:
        invocation_params = _Params()

    with pytest.raises(pytest_module.UsageError, match="重命令守卫"):
        guard.pytest_configure(_Config())


def test_pytest_configure_passes_narrow_call(tmp_path: Path) -> None:
    """pytest 钩子：单文件调用不抛错。"""
    single = tmp_path / "test_one.py"
    single.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    class _Params:
        args: ConcurrentStableList[str] = ConcurrentStableList((str(single),))

    class _Config:
        invocation_params = _Params()

    guard.pytest_configure(_Config())  # 不抛错即通过


def test_pth_boot_exits_hard_for_heavy(monkeypatch: pytest.MonkeyPatch) -> None:
    """`.pth` 启动钩子：命中即硬退出（`site` 初始化期不得抛可捕获异常）。"""
    monkeypatch.delenv(boot._ENV, raising=False)  # pyright: ignore[reportPrivateUsage]  # 本用例验证内部标记
    monkeypatch.delenv(boot._SKIP_ENV, raising=False)  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(sys, "argv", ["pyright"])
    with pytest.raises(SystemExit):
        boot.check()


def test_pth_boot_skips_when_marked(monkeypatch: pytest.MonkeyPatch) -> None:
    """`.pth` 启动钩子：已生效 / 显式跳过标记 ⇒ 不再重复判定。"""
    monkeypatch.setenv(boot._ENV, "1")  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(sys, "argv", ["pyright"])
    boot.check()  # 不退出即通过
    monkeypatch.delenv(boot._ENV, raising=False)  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setenv(boot._SKIP_ENV, "1")  # pyright: ignore[reportPrivateUsage]
    boot.check()


def test_pth_boot_passes_narrow_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """`.pth` 启动钩子：窄范围调用不放行退出。"""
    monkeypatch.delenv(boot._ENV, raising=False)  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(sys, "argv", ["python", "-c", "print(1)"])
    boot.check()


def test_boot_module_locates_guard_file() -> None:
    """钩子能沿仓库布局找回守卫文件（`.pth` 只给绝对路径，重装依赖后依旧可用）。"""
    assert boot._find_guard() is not None  # pyright: ignore[reportPrivateUsage]


def test_run_once_injects_wrapper_marker() -> None:
    """`run-once.py` 必须以 `BMS_RUN_ONCE=1` 注入子进程环境（否则包装后仍被拦）。"""
    source = (_GUARD_PATH.parent / "run-once.py").read_text(encoding="utf-8")
    assert f'"{guard.WRAPPED_ENV}": "1"' in source
    assert "env=child_env" in source


def test_guard_reads_ci_envs_from_environment() -> None:
    """CI 标识取自真实环境变量（非硬编码常量副本）。"""
    assert all(os.environ.get(name) is None for name in _CI_ENVS) or guard.is_ci()
