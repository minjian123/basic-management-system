"""服务目录与产品档案种子脚本（幂等）：平台库 `sys_module` + `sys_product` 幂等 upsert（需求 03-1 / 12-1）。

用法：

```bash
cd backend
uv run python -m ops.seed_module
uv run python -m ops.seed_module --dry-run
```

- URL 解析复用 `ops.seed_tenant.resolve_url(service="platform")`（`--url` > `BMS_MIGRATION_URL` >
  按库键 `platform_platform` 解析：`sys_module` / `sys_product` 归平台服务，06_01 起平台服务库按服务拆分）；
- 单一来源：服务目录取 `SERVICE_CATALOG`、产品档案取 `PRODUCT_CATALOG`（与启动 / CI 校验清单同源，避免漂移）；
- 幂等：按 `module_key` / `product_key` + 未软删除判存——不存在插入、存在则更新本清单字段
  （服务维度 / 分组 / 批次 / 版本 / 产品状态等）；
- 建表分支兼容保留（Alembic 落库后由 `alembic -n alembic:platform:platform upgrade head` 建表；
  SQLite 开发库由启动期自动建表）。
"""

import argparse
import asyncio
from typing import cast

from sqlalchemy import Table, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.keys import PLATFORM_SERVICE_KEY
from bms_core.services.module_registry import PRODUCT_CATALOG, SERVICE_CATALOG, ModuleRecord, ProductRecord
from bms_platform.models.catalog import SysModule, SysProduct
from ops.seed_tenant import resolve_url


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(
        description="服务目录与产品档案种子（平台库 sys_module + sys_product，幂等 upsert）"
    )
    parser.add_argument("--url", default="", help="平台库连接串（缺省读 BMS_MIGRATION_URL / 配置）")
    parser.add_argument("--dry-run", action="store_true", help="仅输出目标库与种子清单")
    return parser


def _fields(seed: ModuleRecord) -> ConcurrentStableDict[str, object]:
    """取服务目录种子的可写字段（与 `sys_module` 列对齐）。

    Args:
        seed: 目录记录。

    Returns:
        ConcurrentStableDict[str, object]: 字段值。
    """
    return ConcurrentStableDict(
        {
            "module_key": seed.module_key,
            "service_key": seed.service_key,
            "name": seed.name,
            "table_prefix": seed.table_prefix,
            "business_code": seed.business_code,
            "errcode_segment": seed.errcode_segment,
            "event_domain": seed.event_domain,
            "service_group": seed.service_group,
            "build_batch": seed.build_batch,
            "service_version": seed.service_version,
            "contract_version": seed.contract_version,
            "product_key": seed.product_key,
            "status": seed.status,
        }
    )


def _product_fields(seed: ProductRecord) -> ConcurrentStableDict[str, object]:
    """取产品档案种子的可写字段（与 `sys_product` 列对齐）。

    Args:
        seed: 产品档案记录。

    Returns:
        ConcurrentStableDict[str, object]: 字段值。
    """
    return ConcurrentStableDict(
        {
            "product_key": seed.product_key,
            "name": seed.name,
            "frontend_package_source": seed.frontend_package_source,
            "status": seed.status,
        }
    )


async def seed_modules(url: str) -> tuple[int, int]:
    """建表并按登记键幂等 upsert 服务目录与产品档案。

    Args:
        url: 平台库连接串。

    Returns:
        tuple[int, int]: (新增行数, 更新行数) 合计（服务目录 + 产品档案）；重复执行为 (0, 0)。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    created = 0
    updated = 0
    try:
        async with engine.begin() as connection:
            await connection.run_sync(cast("Table", SysModule.__table__).create, checkfirst=True)
            await connection.run_sync(cast("Table", SysProduct.__table__).create, checkfirst=True)
        async with factory() as session:
            created, updated = await _upsert_modules(session)
            product_created, product_updated = await _upsert_products(session)
            await session.commit()
            created += product_created
            updated += product_updated
    finally:
        await engine.dispose()
    return created, updated


async def _upsert_modules(session: AsyncSession) -> tuple[int, int]:
    """按 `module_key` 幂等 upsert 服务目录（既有行仅差异赋值）。

    Args:
        session: 平台库会话。

    Returns:
        tuple[int, int]: (新增行数, 更新行数)。
    """
    created = 0
    updated = 0
    for seed in SERVICE_CATALOG:
        statement = select(SysModule).where(SysModule.module_key == seed.module_key, SysModule.deleted_at.is_(None))
        payload = _fields(seed)
        existing = (await session.execute(statement)).scalar_one_or_none()
        if existing is None:
            session.add(SysModule(**payload))
            created += 1
            continue
        changed = False
        for field, value in payload.items():
            if getattr(existing, field) != value:
                setattr(existing, field, value)
                changed = True
        if changed:
            updated += 1
    return created, updated


async def _upsert_products(session: AsyncSession) -> tuple[int, int]:
    """按 `product_key` 幂等 upsert 产品档案（既有行仅差异赋值）。

    Args:
        session: 平台库会话。

    Returns:
        tuple[int, int]: (新增行数, 更新行数)。
    """
    created = 0
    updated = 0
    for seed in PRODUCT_CATALOG:
        statement = select(SysProduct).where(
            SysProduct.product_key == seed.product_key, SysProduct.deleted_at.is_(None)
        )
        payload = _product_fields(seed)
        existing = (await session.execute(statement)).scalar_one_or_none()
        if existing is None:
            session.add(SysProduct(**payload))
            created += 1
            continue
        changed = False
        for field, value in payload.items():
            if getattr(existing, field) != value:
                setattr(existing, field, value)
                changed = True
        if changed:
            updated += 1
    return created, updated


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码。
    """
    args = build_parser().parse_args(argv)
    url = resolve_url(args.url, service=PLATFORM_SERVICE_KEY)
    if args.dry_run:
        target = make_url(url).render_as_string(hide_password=True)
        print(f"[seed_module] 目标库：{target}")
        for seed in SERVICE_CATALOG:
            print(f"[seed_module] 种子：{seed.module_key}（{seed.name} / {seed.table_prefix}）（dry-run）")
        for product in PRODUCT_CATALOG:
            print(f"[seed_module] 产品档案：{product.product_key}（{product.name} / {product.status}）（dry-run）")
        return 0
    created, updated = asyncio.run(seed_modules(url))
    print(f"[seed_module] 服务目录 + 产品档案 新增 {created} 行 / 更新 {updated} 行（幂等；重复执行输出 0 / 0）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
