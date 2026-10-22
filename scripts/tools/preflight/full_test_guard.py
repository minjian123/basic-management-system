#!/usr/bin/env python3
"""全量测试守卫（薄包装）：与重命令守卫统一在 engkit 内的一套实现（13_05）。

本地非 CI 环境跑全量 pytest 且未显式声明（`--full` / `ENGKIT_ALLOW_FULL_TESTS=1`）时拒绝执行、
零用例收集；CI 环境自动放行。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from engkit_boot import ensure_engkit  # noqa: E402

ensure_engkit()

from engkit.guard import (  # noqa: E402
    FULL_ENV,
    FULL_FLAG,
    allow_full,
    full_test_guidance,
    full_test_should_block,
    is_ci,
    pytest_addoption,
    pytest_configure,
)

ALLOW_ENV = FULL_ENV
"""显式声明全量的环境变量（别名，保持既有调用面）。"""

__all__ = [
    "ALLOW_ENV",
    "FULL_ENV",
    "FULL_FLAG",
    "allow_full",
    "full_test_guidance",
    "full_test_should_block",
    "is_ci",
    "pytest_addoption",
    "pytest_configure",
]
