"""租户账号种子 CLI 薄壳（实现与参数解析已下沉 `bms_core.tenant.seed.user`；14_04）。

命令、参数与退出码**不变**：

```bash
cd backend
uv run python -m ops.seed_user --tenant demo --username admin --dry-run         # 计划预演（不建连）
uv run python -m ops.seed_user --tenant demo --username admin                    # 建号（口令随机生成并一次性打印）
uv run python -m ops.seed_user --tenant demo --username admin --reset-password   # 重置既有账号口令
```

口径：`ops/` 属运维通道，本脚本只做入口转发；实现、参数解析与种子数据全部归基座
（`bms_core.tenant.seed.user`），避免运维包与基座两份实现漂移。
"""

from bms_core.tenant.seed.user import main

RUN_IMAGE = "*"
"""本脚本只依赖 `bms_core` 与 `ops`（不导入任何服务包），任意服务镜像均可运行。"""
if __name__ == "__main__":
    raise SystemExit(main())
