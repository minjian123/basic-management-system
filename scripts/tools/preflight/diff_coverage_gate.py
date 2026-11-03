#!/usr/bin/env python3
"""改动行覆盖率门禁（bms 侧薄包装）：转发 `engkit coverage-changed`。

实现唯一一份在 `engkit` 仓的 `coverage.py`（`check_changed`）——本目录**只做转发**，
不承载推导 / 判定逻辑（见同目录 README「关键约束」第 1、2 条）。

判据：只要求**本次 diff 触达的可执行行**被本轮测试执行；注释 / 空行 / 文档串不在语句集合，
天然不误报；未被覆盖率采集的文件（无同名测试）跳过，其覆盖率交推送环 / CI。

用法（解释器须为 backend venv，清单从标准输入读，与 `--files-from -` 同口径）::

    python scripts/tools/preflight/diff_coverage_gate.py --data-file backend/.coverage \\
        --out backend/.coverage.json --root .

退出码：0 达标；1 存在未覆盖的改动行；2 参数 / 环境错误。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from engkit_boot import forward  # noqa: E402


def main() -> int:
    """入口。

    Returns:
        int: 退出码。
    """
    return forward(["coverage-changed", *sys.argv[1:]])


if __name__ == "__main__":
    sys.exit(main())
