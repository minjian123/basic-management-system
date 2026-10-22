#!/usr/bin/env python3
"""重命令守卫的 `.pth` 启动钩子实现（薄包装）：判定与退出逻辑在 engkit（13_05）。

`backend/.venv/.../site-packages/engkit_heavy_guard.pth` 在解释器启动时调用 `engkit.guard.boot()`；
旧的 `a2_heavy_guard.pth` 指向本文件并调用 `boot()`，故保留同名入口转发。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from engkit_boot import ensure_engkit  # noqa: E402

ensure_engkit()

from engkit.guard import boot as _boot  # noqa: E402
from engkit.guard import check as _check  # noqa: E402


def check() -> None:
    """判定当前调用是否重命令；命中抛 `SystemExit`（便于单测）。"""
    _check()


def boot() -> None:
    """解释器启动钩子：命中即硬退出（`.pth` 在 site 初始化期执行）。"""
    _boot()


if __name__ == "__main__":  # pragma: no cover - 由 .pth 调用
    boot()
