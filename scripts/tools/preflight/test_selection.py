#!/usr/bin/env python3
"""变更影响分析选测器（薄包装）：推导实现唯一在 engkit（13_01 / 13_05）。

用途：预检与 CI 只经本入口或 engkit CLI 取值，禁止另写映射规则。

用法::

    python3 scripts/tools/preflight/test_selection.py --changed-from origin/main --format json
    python3 scripts/tools/preflight/test_selection.py --scope frontend --changed-from origin/main --format packages
    python3 scripts/tools/preflight/test_selection.py --changed-from origin/main --format changed-services

退出码：`0` 正常（含「无受影响用例」）；`1` 推导异常（工程发现为空、基准不可解析）。
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
    "--scope",
    "--changed-from",
    "--changed-file",
    "--changed-file-list",
    "--format",
    "--base-threshold",
    "--base-ratio",
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
    args: ConcurrentStableList[str] = ConcurrentStableList(["selection", "--config", config_path()])
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
