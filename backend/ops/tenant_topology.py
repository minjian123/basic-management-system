"""租户部署拓扑运维入口（07C `02_01`）：默认拓扑自举与按租户导出。

```bash
cd backend
uv run python -m ops.tenant_topology bootstrap              # 幂等自举默认拓扑（CI 集成档 / 部署前）
uv run python -m ops.tenant_topology export --tenant-id 0   # 按租户导出当前版本
```

口径：

- **不写第二套逻辑**：经平台应用工厂进入生命周期，自举与导出都复用启动钩子与服务层
  （`TenantTopologyService`），故命令行与进程内行为一致；
- **bootstrap 幂等**：已有默认拓扑时只做覆盖校验与快照装载，不改数据；
- 退出码：0 成功 / 1 失败（异常信息打到 stderr，不吞错）。
"""

import argparse
import asyncio
import json
import sys
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.session import session_scope
from bms_platform.domains.platform_registry.services.tenant_topology import TenantTopologyService
from bms_platform.main import ApplicationFactory

__all__ = ["build_parser", "main", "run"]

RUN_IMAGE = "platform"
"""本脚本依赖平台服务包（`bms_platform`），仅平台镜像可运行。"""


def build_parser() -> argparse.ArgumentParser:
    """构造命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器（`bootstrap` / `export` 两个子命令）。
    """
    parser = argparse.ArgumentParser(description="租户部署拓扑运维入口（自举 / 导出）")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap", help="幂等自举默认拓扑并装载快照")
    export = sub.add_parser("export", help="按租户导出当前版本拓扑")
    export.add_argument("--tenant-id", type=int, default=0, help="租户主键（0 = 平台级默认拓扑）")
    return parser


async def run(command: str, *, tenant_id: int = 0) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """在平台应用生命周期内执行命令。

    Args:
        command: `bootstrap` 或 `export`。
        tenant_id: 导出用的租户主键。

    Returns:
        ConcurrentStableList[ConcurrentStableDict[str, object]]: 导出结果（`bootstrap` 返回空清单）。

    Raises:
        ValueError: 未知命令。
    """
    if command not in ("bootstrap", "export"):
        raise ValueError(f"未知命令：{command}")
    app = ApplicationFactory().create(None)
    async with app.router.lifespan_context(app):
        if command == "bootstrap":
            return ConcurrentStableList()
        async with session_scope(
            app.state.engine_registry,
            db_key=PLATFORM_DB_KEY,
            factory=app.state.session_factory,
        ) as session:
            version, rows = await TenantTopologyService(session).export(tenant_id)
            return ConcurrentStableList(
                ConcurrentStableDict(
                    {
                        "tenant_id": row.tenant_id,
                        "domain_key": row.domain_key,
                        "unit_key": row.unit_key,
                        "topology_version": version,
                        "status": row.status,
                    }
                )
                for row in rows
            )


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（缺省取 `sys.argv`）。

    Returns:
        int: 退出码（0 成功 / 1 失败）。
    """
    args = build_parser().parse_args(argv)
    tenant_id = cast("int", getattr(args, "tenant_id", 0))
    try:
        result = asyncio.run(run(cast("str", args.command), tenant_id=tenant_id))
    except Exception as exc:
        print(f"[tenant_topology] 失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if result:
        print(json.dumps(list(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
