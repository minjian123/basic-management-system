"""平台租户 RBAC 种子 CLI 薄壳（实现与参数解析已下沉 `bms_core.tenant.seed.platform`；14_04）。

命令、参数与退出码**不变**：

```bash
cd backend
uv run python -m ops.seed_platform --dry-run
uv run python -m ops.seed_platform
uv run python -m ops.seed_platform --assign-user admin
```

口径：`ops/` 属运维通道，本脚本只做入口转发；实现、参数解析与种子数据全部归基座
（`bms_core.tenant.seed.platform`），避免运维包与基座两份实现漂移。
"""

from bms_core.tenant.seed.platform import main

if __name__ == "__main__":
    raise SystemExit(main())
