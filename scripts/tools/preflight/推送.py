#!/usr/bin/env python3
"""推送入口（薄包装）：预检是推送的内部步骤，实现全部在 engkit。

用法::

    python3 scripts/tools/preflight/推送.py [bms 仓库根] [--check] [--full]
                                          [--remote origin] [--branch main]
                                          [--jobs auto|N|off]
                                          [--budget-seconds N] [--step-seconds N]

档位由**待推提交**自动选择（不再是人工选档）：全为文档 → 快速档（静态 + 护栏，秒级）；
含代码 / 配置 → 定向档（静态 + 定向用例 + 覆盖率门禁）；`--full` 显式全量。

闸门：工作树有未提交改动（含未跟踪文件）即拒绝——推送前的工作树本就应当是干净的。
预检**不再是独立命令**：本地手动调用 `engkit preflight` 一律拒绝（CI 环境除外），
`--check` 是「只跑预检、不推送」的唯一出口。

步骤清单在仓根 `engkit.toml` 的 `[[preflight.steps]]` 声明；口径见 engkit 文档
《工程化工具包说明》与《AI开发规范》「开发环 / 推送环」节。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from engkit_boot import config_path, forward, pop_root  # noqa: E402

from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402

_VALUE_OPTIONS = ("--root", "--config", "--jobs", "--budget-seconds", "--step-seconds", "--remote", "--branch")
"""带取值的选项（其取值不算位置参数）。"""


def build_argv(argv: ConcurrentStableList[str]) -> ConcurrentStableList[str]:
    """把既有调用习惯（位置根 + 选项）翻译成 engkit 参数。

    Args:
        argv: 命令行参数（不含脚本名）。

    Returns:
        ConcurrentStableList[str]: engkit 参数（含子命令）。
    """
    kept, root = pop_root(argv, _VALUE_OPTIONS)
    args: ConcurrentStableList[str] = ConcurrentStableList(["push", "--config", config_path()])
    if root:
        args.extend(["--root", root])
    args.extend(kept)
    return args


def main() -> int:
    """入口。

    Returns:
        int: 退出码（与 engkit push 一致）。
    """
    return forward(build_argv(ConcurrentStableList(sys.argv[1:])))


if __name__ == "__main__":
    sys.exit(main())
