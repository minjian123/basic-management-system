#!/usr/bin/env python3
"""本地预检（薄包装）：参数与退出码不变，实现全部在 engkit（13_05 迁入）。

用法::

    python3 scripts/tools/preflight/check_preflight.py [bms 仓库根] [--fast|--full]
                                                    [--no-scope] [--no-cov]
                                                    [--jobs auto|N|off]
                                                    [--budget-seconds N] [--step-seconds N]
                                                    [--self-test]

步骤清单在仓根 `engkit.toml` 的 `[[preflight.steps]]` 声明；口径见 engkit 文档
《工程化工具包说明》与《AI开发规范》「重命令不重跑」「覆盖率要求」节。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from engkit_boot import config_path, forward, pop_root  # noqa: E402

from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402

_VALUE_OPTIONS = ("--jobs", "--budget-seconds", "--step-seconds")
"""带取值的选项（其取值不算位置参数）。"""


def build_argv(argv: ConcurrentStableList[str]) -> ConcurrentStableList[str]:
    """把既有调用习惯（位置根 + 选项）翻译成 engkit 参数。

    Args:
        argv: 命令行参数（不含脚本名）。

    Returns:
        ConcurrentStableList[str]: engkit 参数（含子命令）。
    """
    kept, root = pop_root(argv, _VALUE_OPTIONS)
    args: ConcurrentStableList[str] = ConcurrentStableList(["preflight", "--config", config_path()])
    if root:
        args.extend(["--root", root])
    args.extend(kept)
    return args


def main() -> int:
    """入口。

    Returns:
        int: 退出码（与 engkit preflight 一致）。
    """
    return forward(build_argv(ConcurrentStableList(sys.argv[1:])))


if __name__ == "__main__":
    sys.exit(main())
