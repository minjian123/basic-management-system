#!/usr/bin/env python3
"""服务边界与跨库访问校验（薄包装）：实现在 engkit `base service-boundaries`（13_06 迁入）。

判定逻辑在 engkit，规则数据落本仓 `engkit.toml` 的 `[rules.service_boundaries]`（表归属登记模块、
服务目录模块、域布局 / 例外白名单 / 域级基线三份 JSON、运维镜像取值与镜像包集合）；本脚本只做参数
转发与退出码透传，**不含任何推导逻辑**（《AI开发规范》「重命令不重跑」+ 13_05 决策 9）。

用法::

    python3 scripts/tools/base_check/check_service_boundaries.py [仓库根] [--json] [--self-test]
    python3 scripts/tools/base_check/check_service_boundaries.py [仓库根] --update-baseline

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
    args = ["base", "service-boundaries", "--config", config_path()]
    if root:
        args.extend(["--root", root])
    args.extend(kept)
    return forward(args)


if __name__ == "__main__":
    sys.exit(main())
