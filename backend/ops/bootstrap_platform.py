"""平台租户显式引导（生产用；任务 `04_01`）。

用法：

```bash
cd backend
uv run python -m ops.bootstrap_platform --dry-run
uv run python -m ops.bootstrap_platform
```

- 与 tenant 服务启动钩子共用 `ensure_platform_tenant_row`（幂等）：创建平台租户注册行 → 建库 / 建表 / 种子
  （平台 RBAC + 初始超管 + 默认 IdP 占位 + 归档策略参数）→ 基础模块清单 → 置 `active` + `tenant.created`。
- 生产 `[platform_tenant].auto_bootstrap = false` 时由本脚本执行；初始超管口令一次性打印。
- 前置：platform 服务平台库已建表并完成 `ops.seed_menu`（权限码 / 菜单 / 表单种子）。
"""

import argparse
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.outbox.null import NullOutboxStore
from bms_core.servicecall.null import NullServiceClient
from bms_tenant.services.platform_tenant import ensure_platform_tenant_row
from bms_tenant.services.tenant_admin import TenantAdminService
from bms_tenant.services.tenant_module import ModuleCatalog, TenantModuleService
from bms_tenant.services.tenant_quota import TenantQuotaService

RUN_IMAGE = "tenant"
"""本脚本导入 `bms_tenant.services.*`（平台租户引导复用 tenant 服务实现），只有 tenant 镜像含该包。"""
__all__ = ["main"]


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="平台租户显式引导（幂等）")
    parser.add_argument("--dry-run", action="store_true", help="仅打印目标（不建连）")
    return parser


async def _run() -> int:
    """执行引导。

    Returns:
        int: 退出码。
    """
    settings = get_settings()
    factory = EngineFactory(settings, allow_cross_service=True)
    url = factory.resolved_url(PLATFORM_DB_KEY)
    engine = create_async_engine(url)
    factory_session: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory_session() as session:
            modules = TenantModuleService(
                session=session,
                catalog=ModuleCatalog(client=NullServiceClient(), cache=None),
            )
            admin = TenantAdminService(
                session=session,
                modules=modules,
                quotas=TenantQuotaService(session, settings),
                outbox=NullOutboxStore(),
            )
            created = await ensure_platform_tenant_row(
                session=session,
                settings=settings,
                modules=modules,
                admin=admin,
                outbox=NullOutboxStore(),
            )
            print(f"[bootstrap_platform] {'已引导' if created else '已就绪（跳过）'}：{settings.platform_tenant.code}")
    finally:
        await engine.dispose()
    return 0


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码。
    """
    args = build_parser().parse_args(argv)
    settings = get_settings()
    if args.dry_run:
        print(f"[bootstrap_platform] 平台租户 {settings.platform_tenant.code}（{settings.platform_tenant.name}）")
        print(f"[bootstrap_platform] 平台库：{PLATFORM_DB_KEY}")
        return 0
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
