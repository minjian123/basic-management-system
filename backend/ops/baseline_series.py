"""存量库切换到域清单：先结构对账，通过后**只写基线行、不执行 DDL**（07C `03_02` §3.6）。

```bash
cd backend
uv run python -m ops.baseline_series --datasource tenant --db-key tenant_platform_demo --dry-run
uv run python -m ops.baseline_series --unit platform --datasource tenant \\
    --url "sqlite+aiosqlite:///./database/bms/bms_platform_demo.db"
```

口径：

1. **期望表集** = 单元在某库类别的建表集（`bootstrap.unit_metadata`，与启动期建表 / 迁移元数据同一派生点）；
2. **结构对账**：`期望 − 实际`（缺表）与 `实际 − 期望`（多表）**任一非空即拒绝**，不写任何版本行（不落半改状态）；
   比对忽略 Alembic 版本记录表（`alembic_version*`）、SQLite 内部表与点分系统表；
3. **基线写入**：对账通过后，逐条**有脚本**的清单（`head_revision` 非空）写 `alembic_version_{domain}` 一行
   （先清空再写 head，幂等可重跑）；无脚本清单跳过、不建版本表；
4. **旧 `alembic_version`**：本命令**不读不改**（保留只读一版，后续清理由运维择机执行）；
5. **`--dry-run`**：只对账与打印计划，不写库。
"""

import argparse
import asyncio
import re
from dataclasses import dataclass

from sqlalchemy import Connection, MetaData, create_engine
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import Inspector, make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.config import get_settings
from bms_core.core.objects import BaseValueObject
from bms_core.db.bootstrap import unit_metadata
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import build_platform_db_key
from bms_core.db.migration import (
    DATASOURCES,
    MigrationSeries,
    apply_session_schema,
    head_revision,
    unit_key,
    unit_series,
)
from bms_core.db.sync import is_sync_only_url

RUN_IMAGE = "*"
"""本脚本只依赖 `bms_core` 与 `ops`（不导入服务包），任意服务镜像均可运行。"""

_ASYNC_DRIVERS = frozenset({"aiosqlite", "aiomysql", "asyncmy", "asyncpg"})
"""异步驱动名集合（其余驱动走同步路径）。"""

_IGNORED_TABLE_RE = re.compile(r"^(alembic_version.*|sqlite_sequence|sqlite_stat.*)$")
"""对账忽略项：Alembic 版本记录表（新旧）、SQLite 内部表。"""


@dataclass(frozen=True)
class BaselineOutcome(BaseValueObject):
    """单库基线写入结果（对账差异 + 已写 / 跳过）。"""

    unit: str
    datasource: str
    target: str
    expected: int
    missing: ConcurrentStableList[str]
    extra: ConcurrentStableList[str]
    written: ConcurrentStableList[str]
    skipped: ConcurrentStableList[str]
    dry_run: bool = False

    @property
    def ok(self) -> bool:
        """对账是否通过（无缺表 / 无多表）。

        Returns:
            bool: 通过 True。
        """
        return not self.missing and not self.extra


def _is_async_url(url: str) -> bool:
    """连接串是否异步驱动。

    Args:
        url: 数据库连接串。

    Returns:
        bool: 异步驱动 True。
    """
    return make_url(url).get_driver_name() in _ASYNC_DRIVERS


def _version_table_ddl(version_table: str) -> str:
    """取版本记录表建表语句（与 Alembic 默认结构一致；四库通用）。

    Args:
        version_table: 版本记录表名。

    Returns:
        str: DDL。
    """
    return (
        f"CREATE TABLE {version_table} ("
        f"version_num VARCHAR(32) NOT NULL, CONSTRAINT {version_table}_pk PRIMARY KEY (version_num))"
    )


def _reconcile(
    expected: ConcurrentStableSet[str], actual: ConcurrentStableSet[str]
) -> tuple[ConcurrentStableList[str], ConcurrentStableList[str]]:
    """对账：返回（缺表, 多表）——两者均按名排序，忽略 Alembic 版本表与 SQLite 内部表。

    Args:
        expected: 期望表集。
        actual: 实际表集。

    Returns:
        tuple[ConcurrentStableList[str], ConcurrentStableList[str]]: （缺表, 多表）。
    """
    kept_actual = ConcurrentStableSet(name for name in actual if not _IGNORED_TABLE_RE.match(name))
    missing = ConcurrentStableList(sorted(expected - kept_actual))
    extra = ConcurrentStableList(sorted(kept_actual - expected))
    return missing, extra


def _write_rows_sync(
    url: str, schema: str, series: ConcurrentStableList[MigrationSeries], heads: ConcurrentStableDict[str, str]
) -> None:
    """同步写基线行（达梦等；写前切换会话模式）。

    Args:
        url: 连接串。
        schema: 目标模式名（空串表示不切换）。
        series: 待写清单（仅有脚本者）。
        heads: 清单名 → head 版本号。
    """
    engine = create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            apply_session_schema(connection, schema)
            for item in series:
                table = item.version_table
                if not _has_table(connection, table):
                    connection.exec_driver_sql(_version_table_ddl(table))
                connection.exec_driver_sql(f"DELETE FROM {table}")
                connection.exec_driver_sql(f"INSERT INTO {table} (version_num) VALUES ('{heads[item.name]}')")
    finally:
        engine.dispose()


async def _write_rows_async(
    url: str, series: ConcurrentStableList[MigrationSeries], heads: ConcurrentStableDict[str, str]
) -> None:
    """异步写基线行（SQLite / MySQL / PostgreSQL 异步驱动）。

    Args:
        url: 连接串。
        series: 待写清单（仅有脚本者）。
        heads: 清单名 → head 版本号。
    """
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            existing = await connection.run_sync(_table_names_sync)
            for item in series:
                if item.version_table not in existing:
                    await connection.exec_driver_sql(_version_table_ddl(item.version_table))
                await connection.exec_driver_sql(f"DELETE FROM {item.version_table}")
                await connection.exec_driver_sql(
                    f"INSERT INTO {item.version_table} (version_num) VALUES ('{heads[item.name]}')"
                )
    finally:
        await engine.dispose()


def _table_names_sync(connection: Connection) -> ConcurrentStableSet[str]:
    """取连接上的表名集合（同步回调，供 `run_sync` 复用）。

    Args:
        connection: SQLAlchemy 同步连接。

    Returns:
        ConcurrentStableSet[str]: 表名集合。
    """
    inspector: Inspector = sa_inspect(connection)
    return ConcurrentStableSet(inspector.get_table_names())


def _has_table(connection: Connection, name: str) -> bool:
    """判定表是否存在（同步连接）。

    Args:
        connection: SQLAlchemy 同步连接。
        name: 表名。

    Returns:
        bool: 存在 True。
    """
    inspector: Inspector = sa_inspect(connection)
    return inspector.has_table(name)


async def _read_tables(url: str, schema: str) -> ConcurrentStableList[str]:
    """读目标库实际表名（按驱动分支；达梦切模式）。

    Args:
        url: 连接串。
        schema: 目标模式名（仅达梦生效）。

    Returns:
        ConcurrentStableList[str]: 表名列表（字符串化）。
    """
    if _is_async_url(url):
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                names = await connection.run_sync(_table_names_sync)
        finally:
            await engine.dispose()
        return ConcurrentStableList(sorted(names))
    engine = create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            apply_session_schema(connection, schema)
            names = _table_names_sync(connection)
    finally:
        engine.dispose()
    return ConcurrentStableList(sorted(names))


async def write_baseline(
    unit: str, datasource: str, url: str, *, target: str = "", schema: str = "", dry_run: bool = False
) -> BaselineOutcome:
    """对账并写基线（对账不通过即拒绝，不写任何行）。

    Args:
        unit: 部署单元标识。
        datasource: 数据源段。
        url: 目标连接串（含密码；禁止写入日志）。
        target: 目标标签（日志用；缺省 `{unit}:{datasource}`）。
        schema: 达梦目标模式名（空串表示不切换）。
        dry_run: 只对账、不写库。

    Returns:
        BaselineOutcome: 结果（对账差异 + 已写 / 跳过清单）。
    """
    label = target or f"{unit}:{datasource}"
    metadata: MetaData = unit_metadata(unit, datasource)
    expected = ConcurrentStableSet(metadata.tables)
    actual = ConcurrentStableSet(await _read_tables(url, schema))
    missing, extra = _reconcile(expected, actual)
    outcome = BaselineOutcome(
        unit=unit,
        datasource=datasource,
        target=label,
        expected=len(expected),
        missing=missing,
        extra=extra,
        written=ConcurrentStableList(),
        skipped=ConcurrentStableList(),
        dry_run=dry_run,
    )
    if not outcome.ok:
        return outcome
    series: ConcurrentStableList[MigrationSeries] = ConcurrentStableList()
    heads: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for item in unit_series(unit, datasource):
        head = head_revision(item)
        if head is None:
            outcome.skipped.add(item.name)
            continue
        series.add(item)
        heads[item.name] = head
    if series and not dry_run:
        if _is_async_url(url):
            await _write_rows_async(url, series, heads)
        else:
            await asyncio.to_thread(_write_rows_sync, url, schema if is_sync_only_url(url) else "", series, heads)
    if not dry_run:
        outcome.written.update(heads)
    return outcome


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="存量库切换到域清单：结构对账 + 基线写入（不执行 DDL）")
    parser.add_argument("--unit", default="", help="部署单元标识（缺省取 [app].unit / [app].service）")
    parser.add_argument("--datasource", required=True, choices=DATASOURCES, help="数据源段")
    parser.add_argument("--db-key", default="", help="库键（经 url_template 解析；与 --url 二选一）")
    parser.add_argument("--url", default="", help="显式连接串（含密码，禁止写入日志）")
    parser.add_argument("--schema", default="", help="达梦目标模式（仅达梦生效）")
    parser.add_argument("--dry-run", action="store_true", help="只对账与打印计划，不写库")
    return parser


def _masked(url: str) -> str:
    """连接串脱敏。

    Args:
        url: 连接串。

    Returns:
        str: 脱敏连接串。
    """
    return make_url(url).render_as_string(hide_password=True)


def _resolve_url(args: argparse.Namespace, unit: str) -> str:
    """解析目标连接串（显式 `--url` 优先，其次库键）。

    Args:
        args: 命令行参数。
        unit: 部署单元标识。

    Returns:
        str: 连接串。
    """
    if args.url:
        return str(args.url)
    key = args.db_key or build_platform_db_key(unit)
    return EngineFactory(get_settings(), allow_cross_service=True).resolved_url(key)


async def run(args: argparse.Namespace) -> int:
    """执行基线写入。

    Args:
        args: 命令行参数。

    Returns:
        int: 退出码（对账不通过为 1）。
    """
    unit = args.unit or unit_key()
    if not unit:
        print("[baseline] 失败：需 --unit 或 [app].unit / [app].service")
        return 1
    url = _resolve_url(args, unit)
    suffix = "（dry-run）" if args.dry_run else ""
    print(f"[baseline] {unit}:{args.datasource} → {_masked(url)}{suffix}")
    outcome = await write_baseline(
        unit,
        args.datasource,
        url,
        target=str(args.db_key or unit),
        schema=str(args.schema),
        dry_run=bool(args.dry_run),
    )
    if not outcome.ok:
        print(
            f"[baseline] 对账不通过：期望 {outcome.expected} 张表，缺 {len(outcome.missing)} / 多 {len(outcome.extra)}"
        )
        for name in outcome.missing:
            print(f"  - 缺表：{name}")
        for name in outcome.extra:
            print(f"  + 多表：{name}")
        print("[baseline] 未写入任何版本行（先补结构差异或修正表归属登记后重跑）")
        return 1
    print(f"[baseline] 对账通过：{outcome.expected} 张表一致")
    for name in outcome.written:
        print(f"  · 基线：{name}")
    for name in outcome.skipped:
        print(f"  · 跳过（无脚本）：{name}")
    print(f"[baseline] 完成：写基线 {len(outcome.written)} 条、跳过 {len(outcome.skipped)} 条")
    return 0


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码。
    """
    return asyncio.run(run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
