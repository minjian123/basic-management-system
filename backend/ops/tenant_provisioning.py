"""租户开通编排 CLI 薄壳（实现与参数解析已下沉 `bms_core.tenant.provisioning`；14_04）。

命令、参数与退出码**不变**：

```bash
cd backend
uv run python -m ops.tenant_provisioning --code acme --dry-run
uv run python -m ops.tenant_provisioning --code acme --password "<初始口令>"
```

口径：`ops/` 属运维通道，本脚本只做入口转发；实现、参数解析与业务语义全部归基座
（`bms_core.tenant.provisioning`），避免运维包与基座两份实现漂移。
"""

from bms_core.tenant.provisioning import main

RUN_IMAGE = "*"
"""本脚本只依赖 `bms_core` 与 `ops`（不导入任何服务包），任意服务镜像均可运行。"""
if __name__ == "__main__":
    raise SystemExit(main())
