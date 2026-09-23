#!/usr/bin/env python3
"""服务边界与跨库访问度量采集（《微服务演进规划》S7；只读脚本）。

采集「服务边界越界数 / 跨库访问数 / 已登记例外数」：

1. **静态**：调用 `check-service-boundaries.py --json`，解析各分类计数与违规明细；
2. **运行时**（可选）：抓取运行期 `bms_boundary_cross_access_total`（`--metrics-url`；随 08_01
   可观测栈端点就绪后启用；不可达 / 未配置则标注降级）。

默认退出码 0（只作度量与留痕）；`--fail-on-violation` 时静态越界数非零退 1。**不并入**
`collect_metrics.py` 的既有「三项度量」口径（《项目规划说明》§25.2）。

用法::

    python3 scripts/tools/governance/boundary_metrics.py [--root <仓库根>]
    python3 scripts/tools/governance/boundary_metrics.py --metrics-url http://127.0.0.1:9090/metrics
    python3 scripts/tools/governance/boundary_metrics.py --out /tmp/boundary.json --fail-on-violation
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

_CHECKER = Path(__file__).resolve().parents[1] / "base-check" / "check-service-boundaries.py"
_METRIC_LINE_RE = re.compile(r"^bms_boundary_cross_access_total(?:\{[^}]*\})?\s+([0-9.eE+]+)\s*$", re.MULTILINE)
_VIOLATION_KEYS = (
    "cross_service_dependency",
    "layer_violation",
    "private_reference",
    "table_name_conflict",
    "table_prefix_conflict",
    "table_ownership_violation",
    "cross_service_access_violation",
)


def run_static(root: Path) -> dict[str, object]:
    """运行静态边界校验并解析 `--json` 输出。

    Args:
        root: bms 仓库根。

    Returns:
        dict[str, object]: 校验结果（`counts` / `problems` / `passed`）；运行失败时 `error`。
    """
    result = subprocess.run(
        [sys.executable, str(_CHECKER), str(root), "--json"],
        capture_output=True,
        text=True,
    )
    if not result.stdout.strip():
        return {"error": f"边界校验无输出（退出码 {result.returncode}）：{result.stderr.strip()[:200]}"}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {"error": f"边界校验输出非 JSON：{exc}"}


def scrape_runtime(metrics_url: str | None) -> dict[str, object]:
    """抓取运行期跨库访问计数（未配置 / 不可达则降级）。

    Args:
        metrics_url: Prometheus 文本端点地址；None 表示未采集。

    Returns:
        dict[str, object]: `available` + `cross_access_total`（或 `reason`）。
    """
    if not metrics_url:
        return {"available": False, "reason": "未配置 --metrics-url（运行期遥测随 08_01）"}
    try:
        with urllib.request.urlopen(metrics_url, timeout=10) as resp:  # noqa: S310 - 内网自托管端点
            text = resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:  # noqa: BLE001 - 网络 / 鉴权失败按降级处理
        return {"available": False, "reason": f"指标端点不可达：{type(exc).__name__}"}
    matches = [float(value) for value in _METRIC_LINE_RE.findall(text)]
    return {"available": True, "cross_access_total": sum(matches) if matches else 0.0}


def main(argv: list[str] | None = None) -> int:
    """入口：采集静态与运行时计数并打印 / 落盘。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码（0 采集完成；--fail-on-violation 且静态越界非零时 1；2 参数 / 路径错误）。
    """
    parser = argparse.ArgumentParser(description="服务边界与跨库访问度量采集（只读）")
    parser.add_argument("--root", default=".", help="bms 仓库根（默认当前目录）")
    parser.add_argument("--metrics-url", default=None, help="运行期 Prometheus 指标端点（可选）")
    parser.add_argument("--out", default=None, help="结果写为 JSON（默认只打印）")
    parser.add_argument("--fail-on-violation", action="store_true", help="静态越界非零时退码 1")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not (root / "backend").is_dir():
        print(f"未找到 bms 仓库根（缺 backend/）：{root}")
        return 2

    static = run_static(root)
    runtime = scrape_runtime(args.metrics_url)
    if "error" in static:
        total_violations = None
        cross_access = None
    else:
        counts = static.get("counts", {})
        total_violations = sum(int(counts.get(key, 0)) for key in _VIOLATION_KEYS)
        cross_access = int(counts.get("cross_service_access_violation", 0))
    result = {
        "collected_at": date.today().isoformat(),
        "static": static,
        "runtime": runtime,
        "summary": {
            "boundary_violations": total_violations,
            "cross_db_access": cross_access,
            "registered_exceptions": (static.get("counts", {}) or {}).get("registered_exceptions_total") if "error" not in static else None,
        },
    }

    print(f"== 服务边界与跨库访问度量（{result['collected_at']}）==")
    if "error" in static:
        print(f"  静态校验失败：{static['error']}")
    else:
        counts = static.get("counts", {})
        print(
            f"  静态：服务边界越界数 {total_violations}（跨库访问 {cross_access}、"
            f"表归属越界 {counts.get('table_ownership_violation', 0)}、"
            f"表名前缀冲突 {int(counts.get('table_name_conflict', 0)) + int(counts.get('table_prefix_conflict', 0))}）"
        )
        print(
            f"  例外白名单：登记 {counts.get('registered_exceptions_total', 0)} 条、"
            f"命中 {counts.get('registered_exceptions_used', 0)} 条"
        )
        if static.get("problems"):
            print(f"  违规明细（{len(static['problems'])} 项）：")
            for problem in static["problems"]:
                print(f"    {problem}")
    if runtime.get("available"):
        print(f"  运行时：跨库访问计数 {runtime.get('cross_access_total')}")
    else:
        print(f"  运行时：未采集（{runtime.get('reason')}）")

    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 JSON：{args.out}")
    if args.fail_on_violation and total_violations:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
