"""表归属登记种子脚本（幂等）：平台服务库 `sys_table_ownership` 幂等 upsert 全量归属清单（06_02）。

用法：

```bash
cd backend
uv run python -m ops.seed_tables
uv run python -m ops.seed_tables --url sqlite+aiosqlite:///./bms_platform.db
uv run python -m ops.seed_tables --dry-run
```

- URL 解析复用 `ops.seed_tenant.resolve_url(service="platform")`（`--url` > `BMS_MIGRATION_URL` >
  按库键 `platform_platform` 解析：`sys_table_ownership` 归 `platform` 服务）；
- 单一来源取 `bms_core/services/table_registry.py::TABLE_OWNERSHIP`（与启动 / CI 对账清单同源，避免漂移）；
- 幂等：按 `table_name` + 未软删除判存——不存在插入、存在则更新清单字段（归属 / 库类别 / 状态 / 说明）；
- 建表分支兼容保留（Alembic 落库后由 `alembic -n alembic:platform:platform upgrade head` 建表；
  SQLite 开发库由启动期自动建表）。
"""

import argparse
import asyncio
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.db.keys import PLATFORM_SERVICE_KEY
from bms_core.models.ownership import SysTableOwnership
from bms_core.services.table_registry import TABLE_OWNERSHIP, TableRecord
from ops.seed_tenant import resolve_url


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="表归属登记种子（平台服务库 sys_table_ownership，幂等 upsert）")
    parser.add_argument("--url", default="", help="平台服务库连接串（缺省读 BMS_MIGRATION_URL / 配置）")
    parser.add_argument("--dry-run", action="store_true", help="仅输出目标库与种子清单")
    return parser


def _fields(seed: TableRecord) -> dict[str, object]:
    """取种子的可写字段（与 `sys_table_ownership` 列对齐）。

    Args:
        seed: 归属登记记录。

    Returns:
        dict[str, object]: 字段值。
    """
    return {
        "table_name": seed.table_name,
        "owner": seed.owner,
        "datasource": seed.datasource,
        "status": seed.status,
        "note": seed.note,
    }


async def seed_tables(url: str) -> tuple[int, int]:
    """建表并按 `table_name` 幂等 upsert 归属登记。

    Args:
        url: 平台服务库连接串。

    Returns:
        tuple[int, int]: (新增行数, 更新行数)；重复执行为 (0, 0)。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    created = 0
    updated = 0
    try:
        async with engine.begin() as connection:
            await connection.run_sync(SysTableOwnership.__table__.create, checkfirst=True)
        async with factory() as session:
            for seed in TABLE_OWNERSHIP:
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
            await session.commit()
    finally:
        await engine.dispose()
    return created, updated


def main(argv: Sequence[str] | None = None) -> int:
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
        for seed in TABLE_OWNERSHIP:
            print(f"[seed_tables] 种子：{seed.table_name} → {seed.owner} / {seed.datasource}（dry-run）")
        return 0
    created, updated = asyncio.run(seed_tables(url))
    print(f"[seed_tables] 新增 {created} 行 / 更新 {updated} 行（幂等；重复执行输出 0 / 0）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
