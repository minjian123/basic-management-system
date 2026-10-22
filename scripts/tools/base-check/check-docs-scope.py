#!/usr/bin/env python3
"""排期与工时落点护栏（薄包装）：实现在 engkit `docs-scope`（13_05 迁入）。

口径见《计划文档规范》「排期唯一落点与边界」节：进度类字段只允许出现在阶段计划与总体规划；
规范 / 资料 / 用户文档目录与行内 `docs-scope:allow` 豁免按仓配置声明。

用法::

    python3 scripts/tools/base-check/check-docs-scope.py [bms 仓库根]
    python3 scripts/tools/base-check/check-docs-scope.py --self-test

退出码：0 无违规；1 存在违规；2 目录缺失。
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


def main() -> int:
    """入口。

    Returns:
        int: 退出码。
    """
    kept, root = pop_root(sys.argv[1:])
    args = ["docs-scope", "--config", config_path()]
    if root:
        args.extend(["--root", root])
    args.extend(kept)
    return forward(args)


if __name__ == "__main__":
    sys.exit(main())
