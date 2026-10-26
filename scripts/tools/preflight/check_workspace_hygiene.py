#!/usr/bin/env python3
"""工作区卫生检查入口（bms 侧薄包装）：转发到工作区仓的实现，CI 无工作区上下文时跳过。

实现唯一一份在工作区配置仓 `scripts/tools/workspace/check_workspace_hygiene.py`
（检查范围是整个工作区，跨 bms / engkit / mdm / biz / test 各仓，不属于 bms 单仓职责）。
本文件只做**定位 + 转发**，不含任何判定逻辑。

定位顺序（与 `engkit_boot.py` 同构）：

1. 环境变量 `WS_HYGIENE_SCRIPT`（显式指定，排查与特殊布局时用）；
2. 平级工作区布局：`<工作区根>/scripts/tools/workspace/check_workspace_hygiene.py`
   （本文件位于 `<工作区根>/bms/scripts/tools/preflight/`，上溯四级即工作区根）。

**都找不到时退出码 0（跳过）**：CI 只 clone bms 单仓、没有工作区，此时「工作区卫生」
不适用；本地缺脚本则说明工作区仓未更新，也不应阻断 bms 预检（另有 `--strict` 可改为失败）。

用法（在 bms 仓库根，由 `engkit.toml` 的预检步骤调用）::

    python3 scripts/tools/preflight/check_workspace_hygiene.py          # 检查（违规退出码 1）
    python3 scripts/tools/preflight/check_workspace_hygiene.py --clean  # 隔离违规文件
    python3 scripts/tools/preflight/check_workspace_hygiene.py --strict # 找不到实现时报错

退出码：0 通过或跳过；1 存在违规；2 参数错误。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

_REPO_ROOT = _SCRIPT_DIR.parents[2]
"""bms 仓库根（本文件位于 `scripts/tools/preflight/`）。"""

_SRC_ROOT = _REPO_ROOT / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402

SCRIPT_DIR = _SCRIPT_DIR
"""本文件所在目录（`bms/scripts/tools/preflight`）。"""

WORKSPACE_ROOT = SCRIPT_DIR.parents[3]
"""bms 仓根的上溯：preflight → tools → scripts → bms → 工作区根。"""

IMPL_RELATIVE = Path("scripts") / "tools" / "workspace" / "check_workspace_hygiene.py"
"""工作区仓内实现的相对路径。"""

IMPL_ENV = "WS_HYGIENE_SCRIPT"
"""显式指定实现路径的环境变量。"""


def locate() -> Path | None:
    """定位工作区仓的卫生检查实现。

    Returns:
        Path | None: 实现脚本路径；找不到返回 None。
    """
    env = os.environ.get(IMPL_ENV, "").strip()
    if env:
        candidate = Path(env)
        return candidate if candidate.is_file() else None
    candidate = WORKSPACE_ROOT / IMPL_RELATIVE
    return candidate if candidate.is_file() else None


def passthrough_args(argv: ConcurrentStableList[str]) -> tuple[ConcurrentStableList[str], bool]:
    """拆出 `--strict`（本包装专属），其余原样转发。

    Args:
        argv: 命令行参数（不含脚本名）。

    Returns:
        tuple[ConcurrentStableList[str], bool]: （转发参数, 是否 strict）。
    """
    kept: ConcurrentStableList[str] = ConcurrentStableList()
    strict = False
    for item in argv:
        if item == "--strict":
            strict = True
            continue
        kept.append(item)
    return kept, strict


def main() -> int:
    """入口。

    Returns:
        int: 转发实现脚本的退出码；跳过返回 0。
    """
    args, strict = passthrough_args(ConcurrentStableList(sys.argv[1:]))

    impl = locate()
    if impl is None:
        if strict:
            sys.stderr.write(
                f"[卫生] 未找到工作区卫生检查实现（期望 {WORKSPACE_ROOT / IMPL_RELATIVE}）："
                f"请确认工作区仓已更新，或设置 {IMPL_ENV}\n"
            )
            return 2
        print(
            f"[卫生] 跳过（无工作区上下文：未找到 {IMPL_RELATIVE.as_posix()}；CI 单仓克隆下不适用）",
            flush=True,
        )
        return 0

    command: ConcurrentStableList[str] = ConcurrentStableList([sys.executable, str(impl)])
    command.extend(args)
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
