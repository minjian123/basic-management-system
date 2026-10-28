"""服务目录与产品档案种子脚本（幂等）：平台库 `sys_module` + `sys_product` 幂等 upsert（需求 03-1 / 12-1）。

用法：

```bash
cd backend
uv run python -m ops.seed_module
uv run python -m ops.seed_module --dry-run
```

- URL 解析复用 `ops.seed_tenant.resolve_url(service="platform")`（`--url` > `BMS_MIGRATION_URL` >
  按库键 `platform_platform` 解析：`sys_module` / `sys_product` 归平台服务，06_01 起平台服务库按服务拆分）；
- 单一来源：服务目录取**合并视图** `service_catalog_view()`（平台常量 + 已装载产品清单）、
  产品档案取 `product_catalog_view()`——与启动接库校验同源，避免「库中缺产品登记行」；
  产品清单按 `[registry].product_manifests` 装载（未配置 = 只播种平台清单，行为与旧版一致）；
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
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableList,
)
from bms_core.core.config import get_settings
from bms_core.db.keys import PLATFORM_SERVICE_KEY
from bms_core.models.platform.catalog import SysModule, SysProduct
from bms_core.registry.products import load_product_manifests
from bms_core.services.module_registry import (
    ModuleRecord,
    ProductRecord,
    product_catalog_view,
    service_catalog_view,
    validate_catalog,
    validate_products,
)
from bms_core.tenant.seed.contract import ExpectedRow
from bms_core.tenant.seed.tenant import resolve_url

RUN_IMAGE = "*"
"""本脚本只依赖 `bms_core` 与 `ops`（不导入任何服务包），任意服务镜像均可运行。"""


def expected_rows() -> ConcurrentStableList[ExpectedRow]:
    """服务目录与产品档案的期望行（冲突预检用；详设 §3.5）。

    **纯函数**：只读合并视图（`service_catalog_view` / `product_catalog_view`），不连库、不写库。
    比对字段取「幂等 upsert 会写入的那些列」，与 `_fields` / `_product_fields` 同源。

    Returns:
        ConcurrentStableList[ExpectedRow]: 期望行（服务目录 + 产品档案）。
    """
    rows: ConcurrentStableList[ExpectedRow] = ConcurrentStableList()
    for seed in service_catalog_view():
        rows.add(
            ExpectedRow(
                table="sys_module",
                key=ConcurrentStableFrozenDict({"module_key": seed.module_key}),
                values=ConcurrentStableFrozenDict(
                    {
                        "name": seed.name,
                        "table_prefix": seed.table_prefix,
                        "event_domain": seed.event_domain,
                    }
                ),
            )
        )
    for product in product_catalog_view():
        rows.add(
            ExpectedRow(
                table="sys_product",
                key=ConcurrentStableFrozenDict({"product_key": product.product_key}),
                values=ConcurrentStableFrozenDict({"name": product.name}),
            )
        )
    return rows


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="服务目录与产品档案的引导性校验（默认只校验；写库由平台启动注册完成）")
    parser.add_argument("--url", default="", help="平台库连接串（缺省读 BMS_MIGRATION_URL / 配置）")
    parser.add_argument("--dry-run", action="store_true", help="仅输出目标库与种子清单")
    parser.add_argument(
        "--write",
        action="store_true",
        help="兼容空库 / 回滚场景：按登记视图幂等 upsert 服务目录与产品档案（注册取代种子写库后仅作应急）",
    )
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
            "tenant_base": seed.tenant_base,
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
    load_product_manifests(get_settings().registry.product_manifests)
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


async def seed_modules_entry(session: AsyncSession, args: ConcurrentStableDict[str, object]) -> None:
    """XA 分支入口（07B `02_03`）：在编排器传入的分支会话内幂等 upsert 服务目录与产品档案。

    **与 `seed_modules(url)` 的分工**：那个是内部单步（自建 engine，排障用）；本入口不建连接，
    写入自动并入 XA 分支事务（由执行器统一 flush + prepare）。

    Args:
        session: 已绑定 XA 分支连接的会话。
        args: 分支参数（本种子不消费）。
    """
    del args
    load_product_manifests(get_settings().registry.product_manifests)
    await _upsert_modules(session)
    await _upsert_products(session)


async def _upsert_modules(session: AsyncSession) -> tuple[int, int]:
    """按 `module_key` 幂等 upsert 服务目录（既有行仅差异赋值）。

    Args:
        session: 平台库会话。

    Returns:
        tuple[int, int]: (新增行数, 更新行数)。
    """
    created = 0
    updated = 0
    for seed in service_catalog_view():
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
    for seed in product_catalog_view():
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


async def check_modules(url: str) -> ConcurrentStableList[str]:
    """引导性校验（07B `02_06`）：库中服务行 / 产品档案须与登记视图一致。

    `02_06` 起写库归**注册通道**（平台启动注册自身声明、产品启动上报）；本命令退化为校验：
    缺行 / 漂移都提示「由平台启动注册写入」，不再由种子代写（`--write` 仅作应急）。

    Args:
        url: 平台库连接串。

    Returns:
        ConcurrentStableList[str]: 差异明细（空表示一致；空库亦为明细，提示先启动平台）。
    """
    load_product_manifests(get_settings().registry.product_manifests)
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    errors: ConcurrentStableList[str] = ConcurrentStableList()
    module_rows: ConcurrentStableList[object] = ConcurrentStableList()
    product_rows: ConcurrentStableList[object] = ConcurrentStableList()
    try:
        async with factory() as session:
            module_rows.update(
                (await session.execute(select(SysModule).where(SysModule.deleted_at.is_(None)))).scalars().all()
            )
            product_rows.update(
                (await session.execute(select(SysProduct).where(SysProduct.deleted_at.is_(None)))).scalars().all()
            )
    except OperationalError as exc:
        # 未建表 / 未迁移：按「空库」处理（提示先启动平台注册，而不是抛栈）
        errors.add(f"平台库不可读（{type(exc).__name__}）：请先执行迁移并启动平台注册")
        return errors
    finally:
        await engine.dispose()
    if not module_rows:
        errors.add("服务目录为空：请先启动平台（注册通道会写入平台自身服务行），勿再用种子代写")
    else:
        errors.update(
            validate_catalog(
                service_catalog_view(),
                ConcurrentStableList(ModuleRecord.from_row(row) for row in module_rows),
            )
        )
    if not product_rows:
        errors.add("产品档案为空：请先启动平台（注册通道会写入产品档案）")
    else:
        errors.update(
            validate_products(
                product_catalog_view(),
                ConcurrentStableList(ProductRecord.from_row(row) for row in product_rows),
            )
        )
    return errors


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
        load_product_manifests(get_settings().registry.product_manifests)
        for seed in service_catalog_view():
            print(f"[seed_module] 种子：{seed.module_key}（{seed.name} / {seed.table_prefix}）（dry-run）")
        for product in product_catalog_view():
            print(f"[seed_module] 产品档案：{product.product_key}（{product.name} / {product.status}）（dry-run）")
        return 0
    if args.write:
        created, updated = asyncio.run(seed_modules(url))
        print(
            f"[seed_module] 应急写库：新增 {created} 行 / 更新 {updated} 行"
            "（注册通道才是权威写入口；仅在空库 / 回滚时使用）"
        )
        return 0
    errors = asyncio.run(check_modules(url))
    if errors:
        for error in errors:
            print(f"[seed_module] {error}")
        print(f"[seed_module] 引导性校验未通过（{len(errors)} 项）")
        return 1
    print("[seed_module] 引导性校验通过：库中服务目录与产品档案与登记视图一致")
    return 0


if __name__ == "__main__":  # pragma: no cover - 模块直跑入口（部署与用例都走 main()）
    raise SystemExit(main())
