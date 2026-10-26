#!/usr/bin/env python3
"""engkit 包定位（薄包装共用）：先 `import engkit`，失败则按 `ENGKIT_HOME` → 同级 `../engkit` 注入路径。

口径（13_05 / 13_07）：`13_07` 起 bms 以 **git 源依赖**安装 `engkit[devtools]`（与 mdm 同构，
install 成功即走第一条路径）；路径探测保留为**兜底**——包不可用（未 sync / 老环境）时，
本地平级克隆或 CI 的 `ENGKIT_HOME` 仍能让包装入口工作。ruff 规则基线另需**克隆**（读文件路径），
与包是两条独立路径。包装脚本**不含任何推导逻辑**，只做参数转发（见《工程化工具包说明》）。
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList

_SRC_ROOT = Path(__file__).resolve().parents[3] / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

REPO_ROOT = Path(__file__).resolve().parents[3]
"""bms 仓库根（本文件位于 `scripts/tools/preflight/`）。"""

CONFIG_NAME = "engkit.toml"
"""仓配置文件名（仓根）。"""


def _stable_list() -> Any:
    """按需导入插入序集合（解释器启动期不导入 `bms_core`，避免覆盖率漏计导入期行）。

    Returns:
        Any: `ConcurrentStableList()` 实例。
    """
    from bms_core.core.concurrent import ConcurrentStableList

    return ConcurrentStableList()


def _frozen_list() -> Any:
    """按需导入冻结插入序集合（同上，保持启动期零 `bms_core` 导入）。

    Returns:
        Any: `ConcurrentStableFrozenList()` 实例。
    """
    from bms_core.core.concurrent import ConcurrentStableFrozenList

    return ConcurrentStableFrozenList()


def _candidate_sources() -> Iterator[Path]:
    """engkit 克隆候选目录（环境变量优先，其次平级克隆）。

    以生成器逐个产出，避免启动期构造集合与导入 `bms_core`（覆盖率探针须先于被测包启动）。

    Yields:
        Path: 候选克隆目录。
    """
    env = os.environ.get("ENGKIT_HOME", "").strip()
    if env:
        yield Path(env)
    yield REPO_ROOT.parent / "engkit"


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
    for candidate in _candidate_sources():
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
    kept = _stable_list()
    options = _frozen_list() if value_options is None else value_options
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
