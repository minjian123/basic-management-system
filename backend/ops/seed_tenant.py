"""租户注册种子脚本（幂等）：平台库建 `sys_tenant` 表并写入演示租户（需求 01-2）。

用法：

```bash
cd backend
uv run python -m ops.seed_tenant
uv run python -m ops.seed_tenant --url sqlite+aiosqlite:///./bms_platform.db
uv run python -m ops.seed_tenant --dry-run
```

- URL 解析：`--url` 参数 > `BMS_MIGRATION_URL` 环境变量 > 配置 `database.platform.url`；
- 幂等：`SysTenant` 表 `create(checkfirst=True)`，按 `code` + 未软删除判存跳过；
- 迁移与 SQLite 全量自动建表归 01_04（Alembic 落地后本脚本退化为纯种子脚本，建表分支兼容保留）。
"""

import argparse
import asyncio
import os
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.tenant import build_tenant_db_key
from app.models.platform import SysTenant


@dataclass(frozen=True)
class TenantSeed:
    """演示租户种子（开发 / 实测：demo 与 acme 双租户，供跨租户隔离验证）。"""

    code: str
    name: str
    domain: str
    status: str = "active"


TENANT_SEEDS: tuple[TenantSeed, ...] = (
    TenantSeed(code="demo", name="演示租户", domain="demo.bms.example.com"),
    TenantSeed(code="acme", name="示例租户", domain="acme.bms.example.com"),
)


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="租户注册种子（平台库 sys_tenant，幂等）")
    parser.add_argument("--url", default="", help="平台库连接串（缺省读 BMS_MIGRATION_URL / 配置）")
    parser.add_argument("--dry-run", action="store_true", help="仅输出目标库与种子清单")
    return parser


def resolve_url(url: str = "") -> str:
    """解析目标平台库 URL（参数 > 环境变量 > 配置）。

    Args:
        url: 命令行传入的 URL（空串表示未指定）。

    Returns:
        str: 平台库连接串。
    """
    if url:
        return url
    env_url = os.environ.get("BMS_MIGRATION_URL", "")
    if env_url:
        return env_url
    return get_settings().database.platform.url


async def seed_tenants(url: str) -> int:
    """建表并写入种子租户（幂等）。

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
            await connection.run_sync(SysTenant.__table__.create, checkfirst=True)
        async with factory() as session:
            for seed in TENANT_SEEDS:
                statement = select(SysTenant).where(SysTenant.code == seed.code, SysTenant.deleted_at.is_(None))
                if (await session.execute(statement)).scalar_one_or_none() is not None:
                    continue
                session.add(
                    SysTenant(
                        code=seed.code,
                        name=seed.name,
                        domain=seed.domain,
                        db_key=build_tenant_db_key(seed.code),
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
        print(f"[seed_tenant] 目标库：{target}")
        for seed in TENANT_SEEDS:
            print(f"[seed_tenant] 种子租户：{seed.code}（{seed.name} / {seed.domain}）（dry-run）")
        return 0
    created = asyncio.run(seed_tenants(url))
    print(f"[seed_tenant] 新增 {created} 行（幂等；重复执行输出 0）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
