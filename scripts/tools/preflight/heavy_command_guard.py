#!/usr/bin/env python3
"""重命令包装守卫（08_05 起）：**本地非 CI 环境未经 `run-once.py` 包装跑重命令立即报错**。

## 为什么需要它（技术约束，不靠自觉）

《AI开发规范》「重命令不重跑」已强制：分钟级重命令一律经 `run-once.py` 包装。但「顺手直接跑」
是高频惯性——实测代价：定向预检约 **100 秒**、全量 pytest 约 **54 秒**（3300 项）、全仓 pyright 约
**90 秒**；一次误跑 + 一次「为挑报错再跑一遍」等于浪费数分钟。本守卫把「包装」从**口头约定**变成
**运行期强制**：未包装即报错，且报错信息直接给出该用的命令。

## 覆盖范围（口径同「重命令不重跑」一节）

1. **预检脚本**：`check-preflight.py`（定向 / `--fast` 档均算）；
2. **全量 / 多目录 pytest**：无位置参数，或位置参数指向目录（含 `testpaths` 缺省情形）；
   单文件 / 单节点（`file.py::test_x`）**放行**（秒级，不属重命令）；
3. **全仓 ruff**：无路径参数，或路径参数含仓库级目录（`libs` / `services` / `scripts` / 仓库根）；
4. **全仓 pyright**：同上。

**放行**（不算重命令）：单文件 / 单目录下的精确文件清单 / 带 `-k` 收窄的单文件调用。

## 判定口径（命中即报错，命令**零执行**）

同时满足下列三条即拦截：

1. **未经包装**：环境变量无 `BMS_RUN_ONCE=1`（由 `run-once.py` 注入）；
2. **未显式绕过**：环境变量无 `BMS_ALLOW_UNWRAPPED=1`；
3. **非 CI**：环境变量无 `CI` / `GITLAB_CI` 等 CI 标识（CI 跑全量是职责，不拦）。

## 挂接方式（两条独立通道）

- **pytest**：由 `bms_testing_plugin.py` 在 `pytest_configure` 最早期调用 `pytest_configure(config)`；
- **pyright / 预检脚本**：由 `backend/.venv/Lib/site-packages/` 下的 `a2_heavy_guard.pth` 启动钩子
  在解释器启动时调用 `pth_hook(argv)`（与既有 `a1_coverage.pth` 同一机制）。

**已知技术边界**：`ruff` 是原生 Rust 二进制（`ruff.exe` 约 26MB，非 Python 启动器），Python 层
钩子**无法拦截**——其全仓调用仍需靠自觉与预检兜底；本守卫不谎称覆盖。

用例：Kiwi **2330**（`backend/libs/bms_core/tests/boundary/test_heavy_command_guard.py`）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
"""bms 仓库根（本脚本位于 `scripts/tools/preflight/`）。"""

_SRC_ROOT = _REPO_ROOT / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402

WRAPPED_ENV = "BMS_RUN_ONCE"
"""包装标记环境变量（由 `run-once.py` 注入 `1`）。"""

ALLOW_ENV = "BMS_ALLOW_UNWRAPPED"
"""显式绕过环境变量（`1` / `true` 放行；排查 run-once 自身问题时用）。"""

CI_ENVS = ("CI", "GITLAB_CI", "GITHUB_ACTIONS", "JENKINS_URL", "BUILDKITE", "TF_BUILD")
"""CI 环境标识（任一存在即视为 CI，不拦）。"""

_REPO_DIRS = ("libs", "services", "scripts", "deploy", "frontend")
"""仓库级目录（ruff / pyright 参数指向这些即视为全仓 / 大范围扫描）。"""

_PREFLIGHT_SCRIPTS = ("check-preflight.py", "check-base.py", "check-links.py")
"""预检 / 基座脚本名（一律算重命令）。"""

_DIR_TEST_THRESHOLD = 20
"""目录判重阈值：pytest 位置参数指向的目录下测试文件数超过此值即视为重命令。"""

_SUBCOMMANDS = ("check", "format", "rule", "config", "linter", "clean", "server", "analyze", "version")
"""工具子命令（不算目标路径；`ruff check` / `ruff format` 后缺目标即扫全仓）。"""


def is_ci() -> bool:
    """是否 CI 环境（任一 CI 标识存在即为真）。

    Returns:
        bool: CI 环境返回 True。
    """
    return any(os.environ.get(name) for name in CI_ENVS)


def is_wrapped() -> bool:
    """本次调用是否经 `run-once.py` 包装。

    Returns:
        bool: 存在包装标记返回 True。
    """
    return os.environ.get(WRAPPED_ENV, "").strip() == "1"


def allow_unwrapped() -> bool:
    """是否显式声明绕过包装检查。

    Returns:
        bool: `BMS_ALLOW_UNWRAPPED` 为真值返回 True。
    """
    return os.environ.get(ALLOW_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _positional(args: ConcurrentStableList[str]) -> ConcurrentStableList[str]:
    """取命令行中的位置参数（非选项、非子命令，且跳过选项取值）。

    Args:
        args: 命令行参数（不含程序名）。

    Returns:
        ConcurrentStableList[str]: 位置参数列表。
    """
    positional: ConcurrentStableList[str] = ConcurrentStableList()
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in ("-k", "-m", "--deselect", "--cov", "--cov-report", "-p", "--rootdir", "-c", "--changed-file"):
            skip_next = True
            continue
        if arg.startswith("-"):
            continue
        if arg in _SUBCOMMANDS:
            continue
        positional.add(arg)
    return positional


def _count_test_files(target: Path) -> int:
    """统计目录下测试文件数（`test_*.py` / `*_test.py`）；非目录返回 0。

    Args:
        target: 目标路径。

    Returns:
        int: 测试文件数（无法读取时为 0，不阻断判定）。
    """
    if not target.is_dir():
        return 0
    try:
        return sum(
            1 for item in target.rglob("*.py") if item.name.startswith("test_") or item.name.endswith("_test.py")
        )
    except OSError:  # pragma: no cover - 权限等异常时的退化路径
        return 0


def _is_heavy_pytest(args: ConcurrentStableList[str]) -> bool:
    """pytest 调用是否属重命令（无范围 / 范围覆盖的测试文件数超阈值）。

    Args:
        args: 命令行参数（不含程序名）。

    Returns:
        bool: 属重命令返回 True。
    """
    positional = _positional(args)
    if not positional:
        return True
    for item in positional:
        if "::" in item:
            continue
        target = Path(item)
        if target.suffix.lower() == ".py":
            continue
        if _count_test_files(target) > _DIR_TEST_THRESHOLD:
            return True
    return False


def _is_heavy_scanner(args: ConcurrentStableList[str], *, default_targets: bool) -> bool:
    """ruff / pyright 调用是否属重命令（无参数扫缺省目标，或参数指向仓库级目录）。

    Args:
        args: 命令行参数（不含程序名）。
        default_targets: 该工具无参数时是否默认扫全仓。

    Returns:
        bool: 属重命令返回 True。
    """
    positional = _positional(args)
    if not positional:
        return default_targets
    for item in positional:
        normalized = item.replace("\\", "/").strip("/")
        if normalized in (".", "") or normalized in _REPO_DIRS:
            return True
    return False


def classify(argv: ConcurrentStableList[str]) -> str:
    """判定本次调用是否重命令并给出类别标识。

    Args:
        argv: 完整命令行（含程序名 / 解释器路径）。

    Returns:
        str: 重命令类别（`preflight` / `pytest` / `pyright` / `ruff`）；非重命令返回空串。
    """
    if not argv:
        return ""
    program = Path(argv[0]).name.lower()
    rest = ConcurrentStableList(argv[1:])

    if program in ("python", "python3", "python.exe") and len(rest) >= 2 and rest[0] == "-m":
        program = rest[1].lower()
        rest = ConcurrentStableList(rest[2:])

    for script in _PREFLIGHT_SCRIPTS:
        if program == script or any(Path(item).name == script for item in argv):
            return "preflight"

    if program.startswith("pytest"):
        return "pytest" if _is_heavy_pytest(rest) else ""
    if program.startswith("pyright"):
        return "pyright" if _is_heavy_scanner(rest, default_targets=True) else ""
    if program.startswith("ruff"):
        return "ruff" if _is_heavy_scanner(rest, default_targets=True) else ""
    return ""


def guidance(kind: str) -> str:
    """生成拦截提示（含该用的包装命令）。

    Args:
        kind: 重命令类别（`classify` 返回值）。

    Returns:
        str: 提示文本。
    """
    examples = {
        "preflight": "python scripts/tools/preflight/run-once.py -- python scripts/tools/preflight/check-preflight.py",
        "pytest": "python scripts/tools/preflight/run-once.py -- uv run pytest <测试文件或目录>",
        "pyright": "python scripts/tools/preflight/run-once.py -- uv run pyright <路径>",
        "ruff": "python scripts/tools/preflight/run-once.py -- uv run ruff check <路径>",
    }
    example = examples.get(kind, "python scripts/tools/preflight/run-once.py -- <原命令>")
    return (
        f"[重命令守卫] 拒绝执行：本地非 CI 环境未经 run-once 包装跑重命令（{kind}）。\n"
        "  重命令（分钟级 / 数十秒级）一律经包装调用，避免重复执行与为挑报错重跑：\n"
        f"    {example}\n"
        "  包装口径：缓存键 =「命令 + 工作目录 + 工作区指纹」，窗口内（缺省 30 分钟）命中即回放；\n"
        "  改完代码想立刻重验加 `--force`，只想看缓存状态用 `--show`。\n"
        "  单文件 / 单节点调用（秒级）不受此限，可直接跑。\n"
        "  确需裸跑（排查 run-once 自身问题）请**显式声明**：\n"
        f"    {ALLOW_ENV}=1 <原命令>\n"
        "  口径见《AI开发规范》「重命令不重跑」一节。"
    )


def should_block(argv: ConcurrentStableList[str]) -> str:
    """判定是否应拦截本次调用。

    Args:
        argv: 完整命令行（含程序名 / 解释器路径）。

    Returns:
        str: 应拦截返回重命令类别（非空），放行返回空串。
    """
    if is_ci() or is_wrapped() or allow_unwrapped():
        return ""
    return classify(argv)


def pytest_configure(config: object) -> None:
    """pytest 入口拦截（在收集之前，命中即 `UsageError`，零用例执行）。

    Args:
        config: pytest 配置对象。

    Raises:
        Exception: 命中拦截条件时抛出 pytest 的 `UsageError`。
    """
    import pytest

    params = getattr(config, "invocation_params", None)
    args = ConcurrentStableList(params.args if params is not None else ())
    kind = classify(ConcurrentStableList(["pytest", *args]))
    if not kind or is_ci() or is_wrapped() or allow_unwrapped():
        return
    raise pytest.UsageError(guidance(kind))


def pth_hook(argv: ConcurrentStableList[str] | None = None) -> None:
    """解释器启动钩子（供 `.pth` 调用；判定为重命令即打印提示并终止进程）。

    Args:
        argv: 命令行（缺省取 `sys.argv`）。

    Raises:
        SystemExit: 命中拦截条件时以退出码 1 终止。
    """
    command = ConcurrentStableList(sys.argv if argv is None else argv)
    kind = should_block(command)
    if not kind:
        return
    sys.stderr.write(guidance(kind) + "\n")
    raise SystemExit(1)
