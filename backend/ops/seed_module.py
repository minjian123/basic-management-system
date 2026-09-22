"""模块注册种子脚本（幂等）：平台库建 `sys_module` 表并写入平台域注册清单（需求 01-3）。

用法：

```bash
cd backend
uv run python -m ops.seed_module
uv run python -m ops.seed_module --url sqlite+aiosqlite:///./bms_platform.db
uv run python -m ops.seed_module --dry-run
```

- URL 解析复用 `ops.seed_tenant.resolve_url`（`--url` > `BMS_MIGRATION_URL` > 配置 `database.platform.url`）；
- 种子单一来源取 `PLATFORM_MODULES`（与启动 / CI 校验清单同源，避免漂移）；
- 幂等：`SysModule` 表 `create(checkfirst=True)`，按 `module_key` + 未软删除判存跳过；
- 迁移与 SQLite 全量自动建表归 01_04（Alembic 落地后本脚本退化为纯种子脚本，建表分支兼容保留）。
"""

import argparse
import asyncio
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.platform import SysModule
from app.services.module_registry import PLATFORM_MODULES
from ops.seed_tenant import resolve_url


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="模块注册种子（平台库 sys_module，幂等）")
    parser.add_argument("--url", default="", help="平台库连接串（缺省读 BMS_MIGRATION_URL / 配置）")
    parser.add_argument("--dry-run", action="store_true", help="仅输出目标库与种子清单")
    return parser


async def seed_modules(url: str) -> int:
    """建表并写入平台域模块种子（幂等）。

    Args:
        url: 平台库连接串。

    Returns:
        int: 新增行数（重复执行为 0）。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    created = 0
    try:
        async with engine.begin() as connection:
            await connection.run_sync(SysModule.__table__.create, checkfirst=True)
        async with factory() as session:
            for seed in PLATFORM_MODULES:
                statement = select(SysModule).where(
                    SysModule.module_key == seed.module_key, SysModule.deleted_at.is_(None)
                )
                if (await session.execute(statement)).scalar_one_or_none() is not None:
                    continue
                session.add(
                    SysModule(
                        module_key=seed.module_key,
                        name=seed.name,
                        table_prefix=seed.table_prefix,
                        errcode_segment=seed.errcode_segment,
                        event_domain=seed.event_domain,
                        status=seed.status,
                    )
                )
                created += 1
            await session.commit()
    finally:
        await engine.dispose()
    return created


def main(argv: Sequence[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码。
    """
    args = build_parser().parse_args(argv)
    url = resolve_url(args.url)
    if args.dry_run:
        target = make_url(url).render_as_string(hide_password=True)
        print(f"[seed_module] 目标库：{target}")
        for seed in PLATFORM_MODULES:
            print(f"[seed_module] 种子模块：{seed.module_key}（{seed.name} / {seed.table_prefix}）（dry-run）")
        return 0
    created = asyncio.run(seed_modules(url))
    print(f"[seed_module] 新增 {created} 行（幂等；重复执行输出 0）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
