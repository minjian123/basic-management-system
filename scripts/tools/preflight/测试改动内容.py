#!/usr/bin/env python3
"""开发环入口（薄包装）：只跑本次 git 改动相关内容，实现在 engkit `run-changed`。

口径（与推送前预检分工，见《AI开发规范》「开发环 / 推送环」）：
- 后端：直接依赖选测（不做传递 import 闭包），不跑覆盖率、不退化工程级全量；
- 前端：只跑受影响包（`pnpm --filter <包> test`，不带覆盖率）；
- 静态：只对改动文件跑 `ruff check` + `ruff format --check`；
- 推送前预检（`check_preflight.py`）仍按传递闭包 + 100% 覆盖率 + 全仓静态执行。

用法（在仓库根）::

    python3 scripts/tools/preflight/测试改动内容.py [--changed-from origin/main]
                                                   [--changed-file <路径>]...
                                                   [--jobs auto|N|off] [--timeout N]
                                                   [--no-lint] [--no-frontend]
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from engkit_boot import config_path, forward, pop_root  # noqa: E402

from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402

_VALUE_OPTIONS = (
    "--root",
    "--config",
    "--changed-from",
    "--changed-file",
    "--changed-file-list",
    "--jobs",
    "--timeout",
)
"""带取值的选项（其取值不算位置参数）。"""


def build_argv(argv: ConcurrentStableList[str]) -> ConcurrentStableList[str]:
    """翻译参数（位置根 → `--root`）。

    Args:
        argv: 命令行参数（不含脚本名）。

    Returns:
        ConcurrentStableList[str]: engkit 参数（含子命令）。
    """
    kept, root = pop_root(argv, _VALUE_OPTIONS)
    args: ConcurrentStableList[str] = ConcurrentStableList(["run-changed", "--config", config_path()])
    if root:
        args.extend(["--root", root])
    args.extend(kept)
    return args


def main() -> int:
    """入口。

    Returns:
        int: 退出码。
    """
    return forward(build_argv(ConcurrentStableList(sys.argv[1:])))


if __name__ == "__main__":
    sys.exit(main())
