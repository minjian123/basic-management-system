#!/usr/bin/env python3
"""并行开关（薄包装）：`--jobs` → `-n` 映射的唯一实现在 engkit（13_02 / 13_05）。

取值：`auto`（缺省）→ `-n auto`；正整数 → `-n N`；`off` / `none` / `0` / 空串 → 串行。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from engkit_boot import ensure_engkit  # noqa: E402

ensure_engkit()

from engkit.preflight import DEFAULT_JOBS, describe_jobs, jobs_args  # noqa: E402

describe = describe_jobs
"""既有调用面的别名（`describe(value)`）。"""

__all__ = ["DEFAULT_JOBS", "describe", "jobs_args"]
