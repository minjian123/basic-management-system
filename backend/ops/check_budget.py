"""按服务连接预算离线核对（06_02）：`ops/check_budget.py`。

用法：

```bash
cd backend
uv run python -m ops.check_budget                        # 全部启用服务（平台服务库 + 服务租户库 + 归档库）
uv run python -m ops.check_budget --service platform      # 仅指定服务（可重复）
uv run python -m ops.check_budget --active-tenants 20     # 租户库另按活跃租户数核算
```

口径（与启动期告警**同一内核** `bms_core/db/registry.py::pool_budget_rows`）：

- 平台服务库 / 归档库：`workers_for(service) × (pool_size + max_overflow) ≤ max_connections_for(service) × 70%`；
- 服务租户库：`active_tenants × workers_for(service) × (pool_size + max_overflow) ≤ max_connections_for(service) × 70%`
  （不传 `--active-tenants` 时按 1 个活跃租户的单库口径核算）。

`max_connections == 0` 表示不校验（跳过）；存在超限行 → 退出码 1（不阻断启动，供 CI / 预检与运维核对）。
"""

import argparse
from collections.abc import Sequence

from bms_core.core.config import get_settings
from bms_core.db.registry import PoolBudgetRow, pool_budget_rows


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="按服务连接预算离线核对（服务 × 库类别）")
    parser.add_argument("--service", action="append", default=[], help="服务标识（可重复；缺省全部启用服务）")
    parser.add_argument("--active-tenants", type=int, default=0, help="活跃租户数（租户库按此核算；缺省 0 = 单库口径）")
    return parser


def _format(row: PoolBudgetRow) -> str:
    """格式化单行核算结果。

    Args:
        row: 核算行。

    Returns:
        str: 展示文本。
    """
    limit = "不校验" if row.max_connections == 0 else f"{row.limit:.0f}"
    return (
        f"{row.name:<24} workers={row.workers:<3} pool={row.pool_size}+{row.max_overflow:<3} "
        f"max_connections={row.max_connections:<6} 预计={row.total:<6} 预算上限={limit:<8} "
        f"{'OK' if row.ok else '超限'}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码（存在超限为 1）。
    """
    args = build_parser().parse_args(argv)
    settings = get_settings()
    services = tuple(dict.fromkeys(args.service)) or None
    rows = pool_budget_rows(settings, services=services, active_tenants=max(args.active_tenants, 0))
    print(f"[check_budget] 核算 {len(rows)} 行（服务 × 库类别；70% 预算内不代表容量充裕，请按水位复核）")
    for row in rows:
        print(f"[check_budget] {_format(row)}")
    exceeded = [row for row in rows if not row.ok]
    if exceeded:
        for row in exceeded:
            print(f"[check_budget] 超限：{row.describe()}")
        print(f"[check_budget] 校验失败（{len(exceeded)} 项超限）")
        return 1
    print("[check_budget] 校验通过（均在 70% 连接预算内或未配置上限）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
