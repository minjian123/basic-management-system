"""内置角色与授权种子 CLI 薄壳（实现与参数解析已下沉 `bms_core.tenant.seed.rbac`；14_04）。

命令、参数与退出码**不变**：

```bash
cd backend
uv run python -m ops.seed_rbac --tenant demo --dry-run                    # 计划预演
uv run python -m ops.seed_rbac --tenant demo                              # 落库（幂等）
uv run python -m ops.seed_rbac --tenant demo --assign-user admin          # 落库并把 admin 绑到内置系统管理员
```

口径：`ops/` 属运维通道，本脚本只做入口转发；实现、参数解析与种子数据全部归基座
（`bms_core.tenant.seed.rbac`），避免运维包与基座两份实现漂移。
"""

import asyncio

from bms_core.tenant.seed.rbac import build_parser, main

if __name__ == "__main__":
    asyncio.run(main(build_parser().parse_args()))
