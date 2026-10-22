#!/usr/bin/env python3
"""重命令守卫（薄包装）：判定 / 提示 / 钩子实现唯一在 engkit（13_05 统一为一套）。

未包装跑重命令即报错、命令零执行；两条挂接通道（pytest 插件与 `.pth` 启动钩子）共用 engkit 的
同一份 `classify()`。已知边界：`ruff` 为原生二进制，Python 层钩子无法覆盖。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from engkit_boot import config_path, ensure_engkit  # noqa: E402

from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402

ensure_engkit()

from engkit.config import GuardConfig, load  # noqa: E402
from engkit.guard import (  # noqa: E402
    ALLOW_ENV,
    CI_ENVS,
    heavy_guidance,
    is_ci,
    pytest_configure,
)
from engkit.guard import (  # noqa: E402
    check as pth_hook,
)
from engkit.guard import (  # noqa: E402
    classify as _classify,
)
from engkit.guard import (  # noqa: E402
    should_block as _should_block,
)
from engkit.runonce import WRAPPED_ENV  # noqa: E402


def _guard_config() -> GuardConfig:
    """取本仓拦截配置（读仓根 `engkit.toml`）。

    Returns:
        GuardConfig: 拦截配置（读取失败时用缺省值，宁放行不误拦）。
    """
    try:
        return load(Path(config_path())).guard
    except Exception:
        return GuardConfig()


def classify(argv: ConcurrentStableList[str]) -> str:
    """按本仓配置判定重命令类别。

    Args:
        argv: 完整命令行。

    Returns:
        str: 类别（非重命令为空串）。
    """
    return _classify(argv, _guard_config())


def should_block(argv: ConcurrentStableList[str]) -> str:
    """判定是否应拦截。

    Args:
        argv: 完整命令行。

    Returns:
        str: 类别（放行为空串）。
    """
    return _should_block(argv, _guard_config())


def guidance(kind: str) -> str:
    """拦截提示。

    Args:
        kind: 类别。

    Returns:
        str: 提示文本。
    """
    return heavy_guidance(kind)


__all__ = [
    "ALLOW_ENV",
    "CI_ENVS",
    "WRAPPED_ENV",
    "classify",
    "guidance",
    "is_ci",
    "pth_hook",
    "pytest_configure",
    "should_block",
]
