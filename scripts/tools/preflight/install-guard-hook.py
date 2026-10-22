#!/usr/bin/env python3
"""安装 / 校验重命令守卫的 `.pth` 启动钩子（薄包装，实现在 engkit）。

用法::

    python scripts/tools/preflight/install-guard-hook.py            # 安装 / 覆盖
    python scripts/tools/preflight/install-guard-hook.py --check    # 只校验（缺 / 过期退出码 1）
    python scripts/tools/preflight/install-guard-hook.py --remove   # 卸载

依赖外置 / 重装后钩子会消失（fail-open），重跑一次即可复原；`ruff` 为原生二进制，不适用本钩子。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from engkit_boot import REPO_ROOT, config_path, forward  # noqa: E402

from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402


def build_argv(argv: ConcurrentStableList[str]) -> ConcurrentStableList[str]:
    """把既有选项翻译成 `engkit guard` 子命令。

    Args:
        argv: 命令行参数（不含脚本名）。

    Returns:
        ConcurrentStableList[str]: engkit 参数（含子命令）。
    """
    action = "install-hook"
    root = str(REPO_ROOT)
    for token in argv:
        if token == "--check":
            action = "check-hook"
        elif token == "--remove":
            action = "remove-hook"
        elif token.startswith("--root="):
            root = token.split("=", 1)[1]
    venv = str(Path(root) / "backend" / ".venv")
    return ConcurrentStableList(["guard", action, "--config", config_path(), "--root", root, "--venv", venv])


def main() -> int:
    """入口。

    Returns:
        int: 退出码（0 正常 / 1 缺失或过期）。
    """
    return forward(build_argv(ConcurrentStableList(sys.argv[1:])))


if __name__ == "__main__":
    sys.exit(main())
