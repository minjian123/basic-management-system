#!/usr/bin/env python3
"""后端基类体系校验（薄包装）：实现在 engkit `base backend-base`（13_06 迁入）。

判定逻辑与规则数据均在 engkit（规则数据落本仓 `engkit.toml` 的 `[rules.backend_base]`），本脚本只做
参数转发与退出码透传，**不含任何推导逻辑**（《AI开发规范》「重命令不重跑」+ 13_05 决策 9）。

用法::

    python3 scripts/tools/base_check/check_backend_base.py [仓库根] [--self-test] [其他透传选项]

退出码：0 通过 / 1 存在问题 / 2 规则未登记或登记源缺失。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PREFLIGHT_DIR = _SCRIPT_DIR.parent / "preflight"
for _entry in (_SCRIPT_DIR, _PREFLIGHT_DIR):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from engkit_boot import config_path, forward, pop_root  # noqa: E402

_VALUE_OPTIONS = ()


def main() -> int:
    """入口。

    Returns:
        int: 退出码（engkit 透传）。
    """
    kept, root = pop_root(sys.argv[1:], _VALUE_OPTIONS)
    args = ["base", "backend-base", "--config", config_path()]
    if root:
        args.extend(["--root", root])
    args.extend(kept)
    return forward(args)


if __name__ == "__main__":
    sys.exit(main())
