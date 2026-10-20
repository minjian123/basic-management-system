#!/usr/bin/env python3
"""并行开关（`--jobs`）：预检与选测执行器的**单一解析来源**（13_02）。

取值 → pytest 并行参数：

| 取值 | 参数 | 语义 |
| --- | --- | --- |
| `auto`（缺省） | `-n auto` | 按逻辑核数启动 worker |
| 正整数（如 `4`） | `-n 4` | 固定并发 |
| `off` / `none` / `0` / 空串 | （无） | 串行（可关） |

`check-preflight.py` 与 `run-selected.py` 都只经本模块解析，禁止各写一份映射
（与 `test_selection.py` 的「推导单一来源」同口径）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _REPO_ROOT / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import ConcurrentStableList  # noqa: E402

DEFAULT_JOBS = "auto"
"""缺省并行档：`auto`（按逻辑核数；可经 `--jobs N|off` 覆盖）。"""

_OFF_VALUES = ("", "off", "none", "0")
"""串行取值（`--jobs off` 即关闭并行）。"""

_LEGAL = "auto / 正整数 / off"
"""非法取值的提示文案（合法取值）。"""

_POSITIVE_INT = re.compile(r"[1-9]\d*")
"""正整数形态（不接受 `0` / 负数 / 小数 / 带符号）。"""


def jobs_args(value: str) -> ConcurrentStableList[str]:
    """把 `--jobs` 取值转换为 pytest 并行参数。

    Args:
        value: 档位取值（`auto` / 正整数 / `off` / `none` / `0` / 空串）。

    Returns:
        tuple[str, ...]: pytest 并行参数（空元组表示串行）。

    Raises:
        ValueError: 取值非法（消息内给出合法取值）。
    """
    normalized = value.strip().lower()
    if normalized in _OFF_VALUES:
        return ()
    if normalized == "auto":
        return ("-n", "auto")
    if _POSITIVE_INT.fullmatch(normalized):
        return ("-n", normalized)
    raise ValueError(f"--jobs 取值非法：{value!r}（合法：{_LEGAL}）")


def describe(value: str) -> str:
    """并行档位的可读描述（供预检 / 执行器日志）。

    Args:
        value: 档位取值。

    Returns:
        str: 如 `并行 -n auto` / `串行（--jobs off）`。

    Raises:
        ValueError: 取值非法（同 `jobs_args`）。
    """
    args = jobs_args(value)
    return f"并行 {' '.join(args)}" if args else "串行（--jobs off）"
