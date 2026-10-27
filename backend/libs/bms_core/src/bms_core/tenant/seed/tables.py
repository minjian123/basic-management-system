"""表归属登记种子脚本（幂等）：平台服务库 `sys_table_ownership` 幂等 upsert 全量归属清单并清退退役行（06_02）。

用法：

```bash
cd backend
uv run python -m ops.seed_tables
uv run python -m ops.seed_tables --dry-run
```

- URL 解析复用 `ops.seed_tenant.resolve_url(service="platform")`（`--url` > `BMS_MIGRATION_URL` >
  按库键 `platform_platform` 解析：`sys_table_ownership` 归 `platform` 服务）；
- 单一来源取表归属**合并视图**（`bms_core/services/table_registry.py::table_ownership_view()`——平台清单 +
  产品注入记录；与启动 / CI 对账清单同源，避免漂移）；
- 幂等：按 `table_name` + 未软删除判存——不存在插入、存在则更新清单字段（归属 / 库类别 / 状态 / 说明）；
- **清退**：库中「未软删且不在清单」的登记行一律软删除（`deleted_at`）——清单即归属单一来源，退役表
  （如 2026-10-11 拆除的字典六表）随清单移除而清退；漏清退会让 `platform` 启动期接库对账因
  「库中登记行不在清单」拒启（表实体本身由所属链迁移拆除，登记行由本脚本对齐）；
- 建表分支兼容保留（Alembic 落库后由 `alembic -n alembic:platform:platform upgrade head` 建表；
  SQLite 开发库由启动期自动建表）。
"""

import argparse
import asyncio
from collections.abc import Iterable
from typing import cast

from sqlalchemy import Table, select
from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.db.keys import PLATFORM_SERVICE_KEY
from bms_core.db.migration import apply_session_schema
from bms_core.db.sync import is_sync_only_url
from bms_core.models.ownership import SysTableOwnership
from bms_core.services.table_registry import TableRecord, table_ownership_view
from bms_core.tenant.seed.contract import ExpectedRow
from bms_core.tenant.seed.tenant import resolve_url

RUN_IMAGE = "*"
"""本脚本只依赖 `bms_core` 与 `ops`（不导入任何服务包），任意服务镜像均可运行。"""


def expected_rows() -> ConcurrentStableList[ExpectedRow]:
    """表归属登记的期望行（冲突预检用；详设 §3.5）。

    **纯函数**：只读合并视图 `table_ownership_view()`，不连库、不写库。比对字段取
    `_fields` 写入的归属 / 库类别 / 状态三列。

    Returns:
        ConcurrentStableList[ExpectedRow]: 期望行（每张表一条）。
    """
    rows: ConcurrentStableList[ExpectedRow] = ConcurrentStableList()
    for seed in table_ownership_view():
        rows.add(
            ExpectedRow(
                table="sys_table_ownership",
                key=ConcurrentStableFrozenDict({"table_name": seed.table_name}),
                values=ConcurrentStableFrozenDict(
                    {"owner": seed.owner, "datasource": seed.datasource, "status": seed.status}
                ),
            )
        )
    return rows


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(
        description="表归属登记种子（平台服务库 sys_table_ownership，幂等 upsert + 退役行清退）"
    )
    parser.add_argument("--url", default="", help="平台服务库连接串（缺省读 BMS_MIGRATION_URL / 配置）")
    parser.add_argument("--schema", default="", help="目标模式名（达梦等同步方言必填，如 BMS_DEV）")
    parser.add_argument("--dry-run", action="store_true", help="仅输出目标库与种子清单")
    return parser


def _fields(seed: TableRecord) -> ConcurrentStableDict[str, object]:
    """取种子的可写字段（与 `sys_table_ownership` 列对齐）。

    Args:
        seed: 归属登记记录。

    Returns:
        ConcurrentStableDict[str, object]: 字段值。
    """
    return ConcurrentStableDict(
        {
            "table_name": seed.table_name,
            "owner": seed.owner,
            "domain": seed.domain,
            "datasource": seed.datasource,
            "status": seed.status,
            "note": seed.note,
        }
    )


def _retire_absent(rows: Iterable[SysTableOwnership], known: ConcurrentStableSet[str]) -> int:
    """清退不在清单的登记行（软删除，幂等）。

    Args:
        rows: 库中未软删除的登记行。
        known: 清单表名集合（`table_ownership_view()`）。

    Returns:
        int: 本次清退行数（重复执行为 0）。
    """
    retired = 0
    for row in rows:
        if row.table_name in known:
            continue
        row.soft_delete()
        retired += 1
    return retired


def _seed_tables_sync(url: str, schema: str) -> tuple[int, int, int]:
    """同步方言（达梦）建表 + upsert 归属登记 + 清退退役行（阻塞驱动走线程池）。

    Args:
        url: 平台服务库连接串。
        schema: 目标模式名（达梦）。

    Returns:
        tuple[int, int, int]: (新增行数, 更新行数, 清退行数)。
    """
    engine = create_sync_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    created = 0
    updated = 0
    retired = 0
    seeds = table_ownership_view()
    known = ConcurrentStableSet(seed.table_name for seed in seeds)
    try:
        with engine.connect() as connection:
            apply_session_schema(connection, schema)
            cast("Table", SysTableOwnership.__table__).create(connection, checkfirst=True)
        with Session(engine) as session:
            for seed in seeds:
                statement = select(SysTableOwnership).where(
                    SysTableOwnership.table_name == seed.table_name,
                    SysTableOwnership.deleted_at.is_(None),
                )
                payload = _fields(seed)
                existing = session.execute(statement).scalar_one_or_none()
                if existing is None:
                    session.add(SysTableOwnership(**payload))
                    created += 1
                    continue
                changed = False
                for field, value in payload.items():
                    if getattr(existing, field) != value:
                        setattr(existing, field, value)
                        changed = True
                if changed:
                    updated += 1
            rows = (
                session.execute(select(SysTableOwnership).where(SysTableOwnership.deleted_at.is_(None))).scalars().all()
            )
            retired = _retire_absent(rows, known)
            session.commit()
    finally:
        engine.dispose()
    return created, updated, retired


async def seed_tables_entry(session: AsyncSession, args: ConcurrentStableDict[str, object]) -> None:
    """XA 分支入口（07B `02_03`）：在分支会话内幂等 upsert 表归属登记并清退退役行。

    **与 `seed_tables(url)` 的分工**：那个是内部单步（自建 engine，排障用）；本入口不建连接，
    写入自动并入 XA 分支事务。

    Args:
        session: 已绑定 XA 分支连接的会话。
        args: 分支参数（本种子不消费）。
    """
    del args
    seeds = table_ownership_view()
    known = ConcurrentStableSet(seed.table_name for seed in seeds)
    for seed in seeds:
        statement = select(SysTableOwnership).where(
            SysTableOwnership.table_name == seed.table_name,
            SysTableOwnership.deleted_at.is_(None),
        )
        payload = _fields(seed)
        existing = (await session.execute(statement)).scalar_one_or_none()
        if existing is None:
            session.add(SysTableOwnership(**payload))
            continue
        for field, value in payload.items():
            if getattr(existing, field) != value:
                setattr(existing, field, value)
    rows = (
        (await session.execute(select(SysTableOwnership).where(SysTableOwnership.deleted_at.is_(None)))).scalars().all()
    )
    _retire_absent(rows, known)


async def seed_tables(url: str, *, schema: str = "") -> tuple[int, int, int]:
    """建表并按 `table_name` 幂等 upsert 归属登记，并清退不在清单的退役行。

    Args:
        url: 平台服务库连接串。
        schema: 目标模式名（达梦；同步方言必填）。

    Returns:
        tuple[int, int, int]: (新增行数, 更新行数, 清退行数)；重复执行为 (0, 0, 0)。
    """
    if is_sync_only_url(url):
        return await asyncio.to_thread(_seed_tables_sync, url, schema)
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    created = 0
    updated = 0
    retired = 0
    seeds = table_ownership_view()
    known = ConcurrentStableSet(seed.table_name for seed in seeds)
    try:
        async with engine.begin() as connection:
            table = cast("Table", SysTableOwnership.__table__)
            await connection.run_sync(table.create, checkfirst=True)
        async with factory() as session:
            for seed in seeds:
                statement = select(SysTableOwnership).where(
                    SysTableOwnership.table_name == seed.table_name,
                    SysTableOwnership.deleted_at.is_(None),
                )
                payload = _fields(seed)
                existing = (await session.execute(statement)).scalar_one_or_none()
                if existing is None:
                    session.add(SysTableOwnership(**payload))
                    created += 1
                    continue
                changed = False
                for field, value in payload.items():
                    if getattr(existing, field) != value:
                        setattr(existing, field, value)
                        changed = True
                if changed:
                    updated += 1
            rows = (
                (await session.execute(select(SysTableOwnership).where(SysTableOwnership.deleted_at.is_(None))))
                .scalars()
                .all()
            )
            retired = _retire_absent(rows, known)
            await session.commit()
    finally:
        await engine.dispose()
    return created, updated, retired


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
        print(f"[seed_tables] 目标库：{target}")
        for seed in table_ownership_view():
            print(f"[seed_tables] 种子：{seed.table_name} → {seed.owner} / {seed.datasource}（dry-run）")
        return 0
    created, updated, retired = asyncio.run(seed_tables(url, schema=args.schema))
    print(f"[seed_tables] 新增 {created} 行 / 更新 {updated} 行 / 清退 {retired} 行（幂等；重复执行输出 0 / 0 / 0）")
    return 0


if __name__ == "__main__":  # pragma: no cover - 模块直跑入口（部署与用例都走 main()）
    raise SystemExit(main())
