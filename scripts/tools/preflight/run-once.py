#!/usr/bin/env python3
"""重命令「跑一次」包装（薄包装）：参数与退出码不变，实现全部在 engkit（13_05 迁入）。

用法::

    python3 scripts/tools/preflight/run-once.py -- <命令...>
    python3 scripts/tools/preflight/run-once.py --force -- <命令...>
    python3 scripts/tools/preflight/run-once.py --window-seconds 600 -- <命令...>
    python3 scripts/tools/preflight/run-once.py --show -- <命令...>     # 只看缓存状态，不执行

缓存键 =「命令 + 工作目录 + 工作区指纹」；窗口内（缺省 30 分钟）命中即回放上次完整输出与退出码。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from engkit_boot import config_path, forward  # noqa: E402


def main() -> int:
    """入口。

    Returns:
        int: 退出码（真跑 / 回放透传命令退出码；选项错为 2）。
    """
    return forward(["run-once", "--config", config_path(), *sys.argv[1:]])


if __name__ == "__main__":
    sys.exit(main())
