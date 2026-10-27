"""租户注册种子 CLI 薄壳（实现已下沉 `bms_core.tenant.seed.tenant`；07B `02_03`）。

命令、参数与退出码**不变**：

```bash
cd backend
uv run python -m ops.seed_tenant --dry-run
uv run python -m ops.seed_tenant
```

口径：`ops/` 属运维通道，本脚本只做入口转发；实现、参数解析与种子数据全部归基座。

**内部单步**：本命令仅供排障；统一编排请用 `python -m ops.seed_platform`。
"""

from typing import Any

from bms_core.tenant.seed.tenant import (
    TENANT_SEEDS,
    TenantSeed,
    build_parser,
    main,
    resolve_url,
    seed_tenants,
    seed_tenants_entry,
)

RUN_IMAGE = "*"
"""本脚本只依赖 `bms_core` 与 `ops`（不导入任何服务包），任意服务镜像均可运行。"""


def __getattr__(name: str) -> Any:
    """惰性转发基座模块的模块级属性（如 `SysTenant`）。

    Args:
        name: 属性名。

    Returns:
        Any: 基座模块中的同名属性。

    Raises:
        AttributeError: 基座模块无该属性。
    """
    from bms_core.tenant.seed import tenant as _impl

    return getattr(_impl, name)


__all__ = [
    "TENANT_SEEDS",
    "TenantSeed",
    "build_parser",
    "main",
    "resolve_url",
    "seed_tenants",
    "seed_tenants_entry",
]

if __name__ == "__main__":
    raise SystemExit(main())
