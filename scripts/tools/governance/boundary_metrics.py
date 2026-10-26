#!/usr/bin/env python3
"""服务边界与跨库访问度量采集（薄包装）：实现在 engkit `base boundary-metrics`（13_06 迁入）。

判定与采集逻辑在 engkit，越界计数键 / 跨库访问键 / 例外登记键 / 运行期指标名落本仓 `engkit.toml`
的 `[rules.metrics]`，静态来源取 `[rules.service_boundaries]`（登记源留仓内、工具包只做判定）；
本脚本只做参数转发与退出码透传，**不含任何推导逻辑**（《AI开发规范》「重命令不重跑」+ 13_05 决策 9）。

用法::

    python3 scripts/tools/governance/boundary_metrics.py [--root <仓库根>]
    python3 scripts/tools/governance/boundary_metrics.py --metrics-url http://127.0.0.1:9090/metrics
    python3 scripts/tools/governance/boundary_metrics.py --out /tmp/boundary.json --fail-on-violation

退出码：0 采集完成 / 1 静态越界非零（`--fail-on-violation`）/ 2 规则未登记。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PREFLIGHT_DIR = _SCRIPT_DIR.parent / "preflight"
for _entry in (_SCRIPT_DIR, _PREFLIGHT_DIR):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from engkit_boot import config_path, forward  # noqa: E402


def main() -> int:
    """入口。

    Returns:
        int: 退出码（engkit 透传）。
    """
    args = ["base", "boundary-metrics", "--config", config_path()]
    args.extend(sys.argv[1:])
    return forward(args)


if __name__ == "__main__":
    sys.exit(main())
