#!/usr/bin/env python3
"""engkit 包定位（薄包装共用）：先 `import engkit`，失败则按 `ENGKIT_HOME` → 同级 `../engkit` 注入路径。

口径（13_05）：本仓不安装 engkit 也能跑——本地有平级克隆即可；CI 由 job 按锁定 SHA 克隆并导出
`ENGKIT_HOME`。包装脚本**不含任何推导逻辑**，只做参数转发（见《工程化工具包说明》）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[3] / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
"""bms 仓库根（本文件位于 `scripts/tools/preflight/`）。"""

CONFIG_NAME = "engkit.toml"
"""仓配置文件名（仓根）。"""


def _candidates() -> ConcurrentStableList[Path]:
    """engkit 克隆候选目录（环境变量优先，其次平级克隆）。

    Returns:
        ConcurrentStableList[Path]: 候选目录。
    """
    found: ConcurrentStableList[Path] = ConcurrentStableList()
    env = os.environ.get("ENGKIT_HOME", "").strip()
    if env:
        found.append(Path(env))
    found.append(REPO_ROOT.parent / "engkit")
    return found


def ensure_engkit() -> None:
    """确保 `import engkit` 可用。

    Raises:
        SystemExit: 既未安装、也找不到可用的克隆（退出码 2，并给出安装指引）。
    """
    try:
        import engkit  # noqa: F401

        return
    except ModuleNotFoundError:
        pass
    for candidate in _candidates():
        source = candidate / "src"
        if (source / "engkit" / "__init__.py").is_file():
            sys.path.insert(0, str(source))
            return
    sys.stderr.write(
        "[engkit] 未找到 engkit：请在工作区平级克隆 engkit，或 `pip install engkit`，"
        "或设置 ENGKIT_HOME 指向其克隆目录\n"
    )
    raise SystemExit(2)


def config_path() -> str:
    """仓配置路径（供 `--config` 显式传递，避免依赖当前目录）。

    Returns:
        str: `engkit.toml` 绝对路径。
    """
    return str(REPO_ROOT / CONFIG_NAME)


def forward(argv: ConcurrentStableList[str]) -> int:
    """把参数转交给 engkit 命令行入口。

    Args:
        argv: 完整的 engkit 子命令参数（含子命令名）。

    Returns:
        int: engkit 的退出码。
    """
    ensure_engkit()
    from engkit.cli import main as engkit_main

    return engkit_main(argv)


def pop_root(
    argv: ConcurrentStableList[str],
    value_options: ConcurrentStableFrozenList[str] | None = None,
) -> tuple[ConcurrentStableList[str], str]:
    """从参数里取出位置参数形式的仓库根（bms 既有入口的调用习惯）。

    Args:
        argv: 命令行参数（不含脚本名）。
        value_options: 带取值的选项名（其取值不算位置参数）。

    Returns:
        tuple[ConcurrentStableList[str], str]: （去掉位置根后的参数, 仓库根；缺省空串）。
    """
    kept: ConcurrentStableList[str] = ConcurrentStableList()
    options = ConcurrentStableFrozenList() if value_options is None else value_options
    root = ""
    skip_next = False
    for token in argv:
        if skip_next:
            skip_next = False
            kept.append(token)
            continue
        if token in options:
            skip_next = True
            kept.append(token)
            continue
        if token.startswith("-"):
            kept.append(token)
            continue
        if not root:
            root = token
            continue
        kept.append(token)
    return kept, root
