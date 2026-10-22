#!/usr/bin/env python3
"""基座文档链接自洽校验（薄包装）：实现在 engkit `links`（13_05 迁入）。

校验内容：文档根下全部 Markdown 的相对链接与锚点（跳过行内代码、外部链接与本地凭据文档）。

用法::

    python3 scripts/tools/base-check/check-links.py            # bms 仓库根运行
    python3 scripts/tools/base-check/check-links.py <其他根>     # 指定根目录

退出码：有问题 1，通过 0，文档根缺失 2。
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
    args = ["links", "--config", config_path()]
    if root:
        args.extend(["--root", root])
    args.extend(kept)
    return forward(args)


if __name__ == "__main__":
    sys.exit(main())
