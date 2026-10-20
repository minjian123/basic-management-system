#!/usr/bin/env python3
"""安装 / 校验重命令守卫的 `.pth` 启动钩子（08_05 起，可重复执行）。

## 为什么需要它

`pyright.exe` 是 **Python 启动器**（约 46KB，解释器启动即读 `site-packages` 的 `.pth`），这是 Python
层唯一能在其**启动瞬间**拦截的通道。但 `.pth` 落在 `backend/.venv/.../site-packages/`，而本仓依赖
**外置**到本地依赖仓（`backend/.venv` 是指向 `dev-deps/bms/backend-venv` 的链接）——`还原依赖` /
`重装依赖` / `uv sync` 之后该 `.pth` 会**消失**，守卫静默失效（fail-open，安全方向，但等于没装）。

本脚本把 `.pth` 内容收敛为可重复生成的单一来源：依赖重装后重跑一次即可复原。

## 用法

```bash
python scripts/tools/preflight/install-guard-hook.py            # 安装 / 覆盖
python scripts/tools/preflight/install-guard-hook.py --check    # 只校验（缺 / 过期退出码 1）
python scripts/tools/preflight/install-guard-hook.py --remove   # 卸载
```

## 已知边界

`ruff` 是原生 Rust 二进制（`ruff.exe` 约 26MB），**不经过 Python 解释器**，本钩子无法覆盖；其全仓
调用靠规范约束与预检兜底（见 `heavy_command_guard.py` docstring）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PTH_NAME = "a2_heavy_guard.pth"
"""钩子文件名（`a1_coverage.pth` 之后加载，编号保证顺序）。"""

_BOOT_NAME = "heavy_guard_boot.py"
"""钩子实现模块名（位于 `scripts/tools/preflight/`）。"""


def _site_packages(repo_root: Path) -> Path:
    """定位后端 venv 的 `site-packages` 目录。

    Args:
        repo_root: bms 仓库根。

    Returns:
        Path: `site-packages` 路径。

    Raises:
        SystemExit: 找不到 venv 的 `site-packages`（未建环境 / 路径不符）。
    """
    windows = repo_root / "backend" / ".venv" / "Lib" / "site-packages"
    if windows.is_dir():
        return windows
    lib = repo_root / "backend" / ".venv" / "lib"
    if lib.is_dir():
        for candidate in sorted(lib.glob("python*/site-packages")):
            return candidate
    sys.stderr.write(f"[guard-hook] 未找到后端 venv 的 site-packages：{repo_root / 'backend' / '.venv'}\n")
    raise SystemExit(1)


def _boot_path(repo_root: Path) -> Path:
    """守卫钩子实现模块的绝对路径。

    Args:
        repo_root: bms 仓库根。

    Returns:
        Path: `heavy_guard_boot.py` 路径。
    """
    return repo_root / "scripts" / "tools" / "preflight" / _BOOT_NAME


def render_pth(repo_root: Path) -> str:
    """渲染 `.pth` 内容（单行 import + 调用 `boot()`）。

    Args:
        repo_root: bms 仓库根。

    Returns:
        str: `.pth` 文件内容。
    """
    boot = _boot_path(repo_root).as_posix()
    return (
        "import importlib.util; "
        f"spec = importlib.util.spec_from_file_location('bms_heavy_guard_boot', r'{boot}'); "
        "mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); mod.boot()"
    )


def install(repo_root: Path) -> int:
    """写入 `.pth`（幂等覆盖）。

    Args:
        repo_root: bms 仓库根。

    Returns:
        int: 退出码。
    """
    target = _site_packages(repo_root) / _PTH_NAME
    target.write_text(render_pth(repo_root) + "\n", encoding="utf-8")
    print(f"[guard-hook] 已安装：{target}")
    print("[guard-hook] 覆盖范围：pyright / 预检脚本（ruff 为原生二进制，不适用）")
    return 0


def check(repo_root: Path) -> int:
    """校验 `.pth` 是否存在且内容与当前仓库路径一致。

    Args:
        repo_root: bms 仓库根。

    Returns:
        int: 0 一致 / 1 缺失或过期。
    """
    target = _site_packages(repo_root) / _PTH_NAME
    expected = render_pth(repo_root)
    if not target.is_file():
        print(f"[guard-hook] 缺失：{target}（请运行本脚本安装；依赖重装后需重跑）")
        return 1
    actual = target.read_text(encoding="utf-8").strip()
    if actual != expected:
        print(f"[guard-hook] 过期：{target}（仓库路径已变，请重跑安装）")
        return 1
    print(f"[guard-hook] 正常：{target}")
    return 0


def remove(repo_root: Path) -> int:
    """卸载 `.pth`。

    Args:
        repo_root: bms 仓库根。

    Returns:
        int: 退出码。
    """
    target = _site_packages(repo_root) / _PTH_NAME
    if target.is_file():
        target.unlink()
        print(f"[guard-hook] 已卸载：{target}")
    else:
        print(f"[guard-hook] 无需卸载：{target}")
    return 0


def main() -> int:
    """入口：安装 / 校验 / 卸载 `.pth` 钩子。

    Returns:
        int: 退出码。
    """
    parser = argparse.ArgumentParser(description="安装 / 校验重命令守卫的 .pth 启动钩子")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[3]), help="bms 仓库根")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只校验，不写入")
    mode.add_argument("--remove", action="store_true", help="卸载钩子")
    args = parser.parse_args()
    repo_root = Path(args.root).resolve()
    if args.check:
        return check(repo_root)
    if args.remove:
        return remove(repo_root)
    return install(repo_root)


if __name__ == "__main__":
    sys.exit(main())
