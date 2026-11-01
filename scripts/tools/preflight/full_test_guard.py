#!/usr/bin/env python3
"""全量测试守卫（薄包装）：与重命令守卫统一在 engkit 内的一套实现（13_05）。

本地非 CI 环境跑全量 pytest 一律拒绝（**没有** `--full` / 环境变量逃生口）；推送入口与 CI
通过内部授权标记放行，开发中改完即测走开发环（`engkit run-changed`）。
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
    full_test_guidance,
    full_test_should_block,
    is_ci,
    is_full_authorized,
    pytest_configure,
)

__all__ = [
    "full_test_guidance",
    "full_test_should_block",
    "is_ci",
    "is_full_authorized",
    "pytest_configure",
]
