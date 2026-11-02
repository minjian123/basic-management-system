#!/usr/bin/env python3
"""安装 / 校验 / 卸载提交前覆盖率门禁钩子（`.git/hooks/pre-commit`）。

钩子只做转发：解释器取 `backend/.venv`（Windows `Scripts/python.exe`、其余 `bin/python`），
判定逻辑全在 `提交前预检.py`（口径与退出码见该脚本说明）。

用法::

    python scripts/tools/preflight/install_precommit_hook.py            # 安装 / 覆盖
    python scripts/tools/preflight/install_precommit_hook.py --check    # 只校验（缺 / 过期退出码 1）
    python scripts/tools/preflight/install_precommit_hook.py --remove   # 卸载

幂等：钩子内容带标记块，重复安装只会更新本工具写入的部分；`.git/hooks` 不随仓库分发，
换机器 / 重新 clone 后需重跑一次（`--check` 可判定缺失）。

钩子是 `pre-commit`，`git commit --no-verify` 可跳过（推送环仍判覆盖率，不构成绕过）。
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from engkit_boot import REPO_ROOT  # noqa: E402

from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402

MARKER_BEGIN = "# >>> bms precommit coverage gate >>>"
"""钩子标记块起始行（重复安装据此替换）。"""

MARKER_END = "# <<< bms precommit coverage gate <<<"
"""钩子标记块结束行。"""

HOOK_RELATIVE = Path(".git") / "hooks" / "pre-commit"
"""钩子文件相对路径。"""


def venv_python(root: Path) -> Path:
    """取后端虚拟环境解释器路径（按平台区分目录名）。

    Args:
        root: 仓库根。

    Returns:
        Path: 解释器绝对路径（可能不存在，调用方自行校验）。
    """
    if os.name == "nt":
        return root / "backend" / ".venv" / "Scripts" / "python.exe"
    return root / "backend" / ".venv" / "bin" / "python"


def hook_content(root: Path) -> str:
    """生成钩子脚本全文（含标记块）。

    Args:
        root: 仓库根。

    Returns:
        str: 钩子脚本内容（POSIX sh）。
    """
    python = venv_python(root).as_posix()
    gate = (root / "scripts" / "tools" / "preflight" / "提交前预检.py").as_posix()
    return (
        "#!/bin/sh\n"
        f"{MARKER_BEGIN}\n"
        "# 提交前覆盖率门禁：暂存的后端改动必须让对应模块行 + 分支 100% 覆盖。\n"
        "# 由 scripts/tools/preflight/install_precommit_hook.py 生成，勿手工编辑本块。\n"
        f'PY="{python}"\n'
        f'GATE="{gate}"\n'
        'if [ ! -x "$PY" ]; then\n'
        '    echo "[precommit] 未找到后端虚拟环境解释器：$PY（先建 venv 或重跑安装脚本）" >&2\n'
        "    exit 0\n"
        "fi\n"
        '"$PY" "$GATE" "$@"\n'
        f"{MARKER_END}\n"
    )


def read_hook(target: Path) -> str:
    """读取既有钩子内容（不存在返回空串）。

    Args:
        target: 钩子文件。

    Returns:
        str: 文件内容。
    """
    return target.read_text(encoding="utf-8") if target.is_file() else ""


def merge_hook(existing: str, block: str) -> str:
    """把门禁块并入既有钩子（已有标记块则替换，否则追加）。

    Args:
        existing: 既有内容（空表示新建）。
        block: 门禁块全文。

    Returns:
        str: 合并后的内容。
    """
    if MARKER_BEGIN in existing and MARKER_END in existing:
        head, _, rest = existing.partition(MARKER_BEGIN)
        _, _, tail = rest.partition(MARKER_END)
        return f"{head}{block.rstrip(chr(10))}{tail}"
    if not existing.strip():
        return block
    separator = "" if existing.endswith("\n") else "\n"
    return f"{existing}{separator}{block}"


def make_executable(target: Path) -> None:
    """给钩子文件加可执行位（Windows 依赖 sh 关联，无实际权限位）。

    Args:
        target: 钩子文件。
    """
    mode = target.stat().st_mode
    target.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def install(root: Path) -> int:
    """安装 / 更新钩子。

    Args:
        root: 仓库根。

    Returns:
        int: 退出码（0 成功）。
    """
    target = root / HOOK_RELATIVE
    target.parent.mkdir(parents=True, exist_ok=True)
    merged = merge_hook(read_hook(target), hook_content(root))
    target.write_text(merged, encoding="utf-8", newline="\n")
    make_executable(target)
    print(f"[precommit] 已安装：{target}")
    print(f"[precommit] 解释器：{venv_python(root)}")
    return 0


def check(root: Path) -> int:
    """校验钩子是否已安装且内容最新。

    Args:
        root: 仓库根。

    Returns:
        int: 0 已安装且最新 / 1 缺失或过期。
    """
    target = root / HOOK_RELATIVE
    existing = read_hook(target)
    if MARKER_BEGIN not in existing:
        print(f"[precommit] 未安装：{target}（跑一次安装脚本）")
        return 1
    expected = hook_content(root).rstrip("\n")
    if expected not in existing:
        print(f"[precommit] 已安装但内容过期：{target}（重跑安装脚本）")
        return 1
    print(f"[precommit] 已安装且为最新：{target}")
    return 0


def remove(root: Path) -> int:
    """卸载门禁块（钩子无其他内容时删除文件）。

    Args:
        root: 仓库根。

    Returns:
        int: 退出码（0 成功 / 1 未安装）。
    """
    target = root / HOOK_RELATIVE
    existing = read_hook(target)
    if MARKER_BEGIN not in existing:
        print(f"[precommit] 未安装：{target}")
        return 1
    head, _, rest = existing.partition(MARKER_BEGIN)
    _, _, tail = rest.partition(MARKER_END)
    remainder = f"{head}{tail}".strip()
    if remainder in ("", "#!/bin/sh"):
        target.unlink()
        print(f"[precommit] 已删除：{target}")
        return 0
    target.write_text(f"{remainder}\n", encoding="utf-8", newline="\n")
    print(f"[precommit] 已移除门禁块（保留其余钩子内容）：{target}")
    return 0


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（None 取 `sys.argv`）。

    Returns:
        int: 退出码。
    """
    parser = argparse.ArgumentParser(prog="install_precommit_hook", description="安装提交前覆盖率门禁钩子")
    parser.add_argument("--root", default=str(REPO_ROOT), help="仓库根（缺省为脚本所在仓）")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="只校验安装状态")
    group.add_argument("--remove", action="store_true", help="卸载门禁块")
    args = parser.parse_args(None if argv is None else list(argv))

    root = Path(args.root).resolve()
    if args.check:
        return check(root)
    if args.remove:
        return remove(root)
    return install(root)


if __name__ == "__main__":
    sys.exit(main())
