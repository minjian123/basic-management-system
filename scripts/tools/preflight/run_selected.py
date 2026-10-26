#!/usr/bin/env python3
"""定向执行器（薄包装）：推导 → 跑 pytest → 覆盖率判定 → 扩圈 → 退化 → 度量，实现在 engkit。

参数与退出码与迁移前一致（`0` 通过 / 覆盖率或推导异常 `1` / 单轮超时 `124`）。
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
    "--pytest-cmd",
    "--pytest-cwd",
    "--pytest-arg",
    "--jobs",
    "--cov-fail-under",
    "--max-rounds",
    "--cov-json",
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
    args: ConcurrentStableList[str] = ConcurrentStableList(["run-selected", "--config", config_path()])
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
