#!/usr/bin/env python3
"""覆盖率门禁（薄包装）：合并并行采集数据并判定「行 + 分支」，实现在 engkit。

用法（解释器须为 backend venv，含 coverage）::

    uv run python scripts/tools/preflight/coverage_gate.py --data-file backend/.coverage \\
        --out backend/coverage.json --module bms_core.db.bootstrap

退出码：`0` 达标；`1` 未达标（含未采集到数据）；`2` 参数 / 环境错误。
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
    return forward(["coverage", *sys.argv[1:]])


if __name__ == "__main__":
    sys.exit(main())
