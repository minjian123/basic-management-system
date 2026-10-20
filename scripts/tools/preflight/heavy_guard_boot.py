#!/usr/bin/env python3
"""重命令守卫的 `.pth` 启动钩子实现（08_05 起）。

`backend/.venv/Lib/site-packages/a2_heavy_guard.pth` 在解释器启动时导入本模块并调用 `boot()`——
与既有 `a1_coverage.pth` 同一机制。目的：拦截**不经过 pytest 插件**的重命令
（`pyright` / `check-preflight.py` 等）在本地非 CI、未包装时裸跑。

为何需要 `.pth`：`pyright.exe` 是 Python 启动器（46KB），解释器启动即读 `site-packages` 的 `.pth`，
故可拦；`ruff.exe` 是原生 Rust 二进制（26MB），**不经过 Python 解释器**，此通道无法覆盖（见守卫
模块 docstring 的「已知技术边界」）。

退出方式：命中即向 stderr 打印提示并以退出码 1 终止，命令**零执行**。
"""

from __future__ import annotations

import os
import sys

_ENV = "BMS_HEAVY_GUARD"
"""内部标记：`.pth` 已生效（防重复执行与递归）。"""

_SKIP_ENV = "BMS_HEAVY_GUARD_SKIP"
"""内部标记：本次调用应跳过守卫（守卫自身 / 包装器调用时设置）。"""

_GUARD_FILE = "heavy_command_guard.py"


def _find_guard() -> object | None:
    """定位并加载守卫模块（沿 `sys.path` 与已知仓库布局查找）。

    Returns:
        object | None: 守卫模块；找不到时返回 `None`。
    """
    candidates = []
    for entry in sys.path:
        if entry:
            candidates.append(os.path.join(entry, "scripts", "tools", "preflight", _GUARD_FILE))
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        here = os.path.dirname(here)
        candidates.append(os.path.join(here, "scripts", "tools", "preflight", _GUARD_FILE))
    for path in candidates:
        if os.path.isfile(path):
            import importlib.util

            spec = importlib.util.spec_from_file_location("bms_heavy_command_guard", path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    return None


def check() -> None:
    """判定当前调用是否重命令；命中则抛 `SystemExit`（**不做硬退出**，便于单测）。

    Raises:
        SystemExit: 命中拦截条件。
    """
    if os.environ.get(_ENV) == "1" or os.environ.get(_SKIP_ENV) == "1":
        return
    os.environ[_ENV] = "1"
    try:
        guard = _find_guard()
    except Exception:
        return
    if guard is None:
        return
    try:
        guard.pth_hook(list(sys.argv))
    except SystemExit:
        raise
    except Exception:
        return


def boot() -> None:
    """解释器启动钩子：判定为重命令即报错硬退出。

    `.pth` 在 `site` 初始化期执行，此处的 `SystemExit` 会被 `site` 捕获并打印 traceback（噪声大且
    退出码不可控），故改为先向 stderr 写完提示、再 `os._exit(1)` 硬退出——命令**零执行**。
    """
    try:
        check()
    except SystemExit:
        sys.stderr.flush()
        os._exit(1)
