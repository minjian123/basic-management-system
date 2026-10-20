#!/usr/bin/env python3
"""全量测试守卫（08_05 起）：**本地非 CI 环境跑全量 pytest 立即报错**，不收集、不执行任何用例。

## 为什么需要它（技术约束，不靠自觉）

《测试规范》§2.1 已强制「变更驱动、不全量重跑」，`scripts/tools/preflight/run-selected.py` 是其执行入口。
但「改一个字段就顺手跑全量」是高频惯性——实测代价：单文件用例 **1.4 秒**、定向档 **6.5 秒**、
全量 **7 分钟**（约 3300 项），一次误跑等于浪费数十倍时间。本守卫把「跑全量」从**默认动作**变成
**必须显式声明**的动作。

## 判定口径（在 `pytest_collection` 之前判定，命中即 `UsageError` 退出，**零用例执行**）

跑全量 = 同时满足下列三条：

1. **未指定测试范围**：命令行无位置参数（无测试文件 / 目录 / `::` 节点），且未用 `-k` / `-m` / `--lf` /
   `--ff` / `--deselect` 收窄；也未经 `run-selected.py` 注入 `--changed-file-list`；
2. **未显式声明全量**：命令行无 `--full`、环境变量无 `BMS_ALLOW_FULL_TESTS=1`；
3. **非 CI**：环境变量无 `CI` / `GITLAB_CI` / `GITHUB_ACTIONS` 等 CI 标识。

命中即报错，并打印**该用的命令**（按当前 git 变更自动推导）：

```
[全量测试守卫] 拒绝执行：本地非 CI 环境未声明全量、也未指定测试范围。
  当前变更：3 个文件
  请改用（定向档，约数秒）：
    python scripts/tools/preflight/run-selected.py --changed-from HEAD
  确需全量（约数分钟）请显式声明其一：
    uv run pytest --full
    BMS_ALLOW_FULL_TESTS=1 uv run pytest
```

## 允许全量的正当场景

- **提交前收口**：`uv run pytest --full`（显式声明，审计可见）；
- **CI**：CI 环境变量自动放行（CI 全量是职责，不是浪费）；
- **基线排查**：`BMS_ALLOW_FULL_TESTS=1`（临时、显式）。

## 挂接

- 本地：`backend/pyproject.toml` 的 `addopts` 已含 `-p bms_testing_plugin`；本模块由该插件在
  `pytest_configure` 最早期调用 `install_guard(config)`（见 `bms_testing_plugin.py`）；
- CI：`CI` 等环境变量天然存在 ⇒ 放行，无需改 CI 配置。

用例：Kiwi **2329**（`backend/libs/bms_core/tests/boundary/test_full_test_guard.py`）。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
"""bms 仓库根（本脚本位于 `scripts/tools/preflight/`）。"""

_SRC_ROOT = _REPO_ROOT / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402

FULL_FLAG = "--full"
"""显式全量开关（pytest 自定义选项，由本守卫注册）。"""

ALLOW_ENV = "BMS_ALLOW_FULL_TESTS"
"""显式全量环境变量（`1` / `true` 放行；临时排查用）。"""

CI_ENVS = ("CI", "GITLAB_CI", "GITHUB_ACTIONS", "JENKINS_URL", "BUILDKITE", "TF_BUILD")
"""CI 环境标识（任一存在即视为 CI，放行全量）。"""

_SCOPE_OPTIONS = ("-k", "-m", "--lf", "--ff", "--deselect", "--changed-file-list")
"""收窄测试范围的选项（存在即视为「已指定范围」，不拦）。"""

_GUARD_ENV = "BMS_FULL_TEST_GUARD"
"""内部标记：守卫已安装（防重复注册）。"""


def is_ci() -> bool:
    """是否 CI 环境（任一 CI 标识存在即为真）。

    Returns:
        bool: CI 环境返回 True。
    """
    return any(os.environ.get(name) for name in CI_ENVS)


def allow_full() -> bool:
    """是否显式声明全量（`--full` 由调用方另行判定，本函数只看环境变量）。

    Returns:
        bool: `BMS_ALLOW_FULL_TESTS` 为真值返回 True。
    """
    return os.environ.get(ALLOW_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def changed_file_count(repo_root: Path = _REPO_ROOT) -> int:
    """取当前工作区变更文件数（含未跟踪；取不到返回 0，不阻断判定）。

    Args:
        repo_root: 仓库根。

    Returns:
        int: 变更文件数（git 不可用时为 0）。
    """
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
    except OSError, subprocess.SubprocessError:
        return 0
    return len([line for line in proc.stdout.splitlines() if line.strip()])


def has_explicit_scope(args: ConcurrentStableList[str]) -> bool:
    """命令行是否已显式指定测试范围。

    Args:
        args: 命令行参数（不含程序名）。

    Returns:
        bool: 存在位置参数或收窄选项返回 True。
    """
    for arg in args:
        if arg in _SCOPE_OPTIONS or any(arg.startswith(f"{option}=") for option in _SCOPE_OPTIONS):
            return True
        if arg.startswith("-"):
            continue
        # 非选项参数 = 测试文件 / 目录 / 节点 id
        return True
    return False


def should_block(args: ConcurrentStableList[str]) -> bool:
    """判定是否应拦截本次 pytest 调用。

    Args:
        args: 命令行参数（不含程序名）。

    Returns:
        bool: 应拦截返回 True。
    """
    if is_ci() or allow_full():
        return False
    if FULL_FLAG in args:
        return False
    return not has_explicit_scope(args)


def guidance(repo_root: Path = _REPO_ROOT) -> str:
    """生成拦截提示（含按当前变更推导的定向命令）。

    Args:
        repo_root: 仓库根。

    Returns:
        str: 提示文本。
    """
    count = changed_file_count(repo_root)
    return (
        "[全量测试守卫] 拒绝执行：本地非 CI 环境既未声明全量、也未指定测试范围。\n"
        f"  当前工作区变更：{count} 个文件\n"
        "  请改用定向档（按变更自动推导，约数秒）：\n"
        "    python scripts/tools/preflight/run-selected.py --changed-from HEAD\n"
        "    python scripts/tools/preflight/run-selected.py --changed-file <改动的文件>\n"
        "  确需全量（约数分钟）请**显式声明**其一：\n"
        "    uv run pytest --full\n"
        f"    {ALLOW_ENV}=1 uv run pytest\n"
        "  口径见《测试规范》§2.1「变更驱动、不全量重跑」。"
    )


def pytest_addoption(parser: object) -> None:
    """注册 `--full` 显式全量开关。

    Args:
        parser: pytest 的 Parser 对象（类型放宽以避免插件模块依赖 pytest 类型）。
    """
    addoption = getattr(parser, "addoption", None)
    if addoption is None:  # pragma: no cover - 非 pytest 环境调用
        return
    addoption(
        FULL_FLAG,
        action="store_true",
        default=False,
        help="显式声明本次跑全量（本地非 CI 环境必需；缺省由全量测试守卫拒绝）",
    )


def pytest_configure(config: object) -> None:
    """收集阶段之前拦截全量调用（命中即 `UsageError`，零用例执行）。

    Args:
        config: pytest 配置对象。

    Raises:
        Exception: 命中拦截条件时抛出 pytest 的 `UsageError`（以 `pytest.UsageError` 为准）。
    """
    import pytest

    params = getattr(config, "invocation_params", None)
    args = ConcurrentStableList(params.args if params is not None else ())
    if not should_block(args):
        return
    raise pytest.UsageError(guidance())
