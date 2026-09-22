"""批量迁移：平台库 + 各租户库 + 归档库（按链执行 Alembic 迁移，幂等）。

用法：

```bash
cd backend
uv run python -m ops.migrate_tenants --target all --dry-run      # 清单预演（不建连）
uv run python -m ops.migrate_tenants --target all                # 平台 + 各租户 + 归档
uv run python -m ops.migrate_tenants --target platform           # 仅平台库
uv run python -m ops.migrate_tenants --target tenants            # 仅各租户库（平台库读 sys_tenant）
uv run python -m ops.migrate_tenants --target tenant \
    --url "dm+dmPython://SYSDBA:pass@host:5236" --schema BMS_MIGRCHECK   # 单库（演练 / 迁移演练）
```

- **清单**：`platform` / `archive` 各一库；`tenants` / `all` 从平台库读 `sys_tenant`（未软删）取各库键，
  经 `url_template` 解析租户库连接串；
- **执行**：逐库经 Alembic 程序化接口 `command.upgrade(cfg, "head")`（配置段 = 链名，
  版本目录 / 元数据子集取自 `app/db/migration.py` 链注册）；
- **幂等**：目标 `alembic_version` 已为链 head → 输出「已是最新（跳过）」；
- **失败不中断**：单库失败记 ERROR 并继续下一库，末尾汇总；存在失败时退出码 1；
- **`--dry-run`**：仅打印清单（连接串脱敏），不建连、不迁移；
- 平台库不可用直接报错退出（不静默空跑）；达梦目标经 `--schema` 指定模式（库级隔离）。
"""

import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.core.base import BaseObject
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.db.engine import PLATFORM_DB_KEY, EngineFactory
from bms_core.db.migration import (
    MigrationChain,
    chain_url,
    current_revision,
    head_revision,
    resolve_chain,
    upgrade_chain,
)
from bms_core.db.tenant import build_tenant_db_key
from bms_core.models.platform import SysTenant

_DM = "dm"
_TARGETS = ("all", "platform", "tenants", "tenant", "archive")


@dataclass(frozen=True)
class MigrationTask(BaseObject):
    """单个迁移任务（链 / 展示名 / 连接串 / 模式）。"""

    chain: MigrationChain
    label: str
    url: str
    schema: str = ""


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="批量迁移（平台库 + 各租户库 + 归档库；幂等）")
    parser.add_argument("--target", default="all", choices=_TARGETS, help="迁移目标（缺省 all）")
    parser.add_argument("--db-key", default="", help="指定单个租户库键（tenant_{code}）")
    parser.add_argument("--url", default="", help="显式连接串（单库模式；含密码，禁止写入日志）")
    parser.add_argument("--schema", default="", help="达梦目标模式（仅达梦生效）")
    parser.add_argument("--dry-run", action="store_true", help="仅打印清单（不建连）")
    return parser


def _masked(url: str) -> str:
    """连接串脱敏（隐藏密码）。

    Args:
        url: 连接串。

    Returns:
        str: 脱敏连接串。
    """
    return make_url(url).render_as_string(hide_password=True)


def _query_sync(url: str) -> list[tuple[str, str]]:
    """同步枚举租户（达梦等无异步方言驱动的平台库）。

    Args:
        url: 平台库连接串。

    Returns:
        list[tuple[str, str]]: （编码, 库键）列表。
    """
    engine: Engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            return list(
                connection.execute(select(SysTenant.code, SysTenant.db_key).where(SysTenant.deleted_at.is_(None))).all()
            )
    finally:
        engine.dispose()


async def _tenant_records(platform_url: str) -> list[tuple[str, str]]:
    """枚举租户注册记录（平台库查询；达梦走同步驱动线程）。

    Args:
        platform_url: 平台库连接串。

    Returns:
        list[tuple[str, str]]: （编码, 库键）列表。
    """
    if make_url(platform_url).get_backend_name() == _DM:
        rows = await asyncio.to_thread(_query_sync, platform_url)
        return [(str(code), str(db_key)) for code, db_key in rows]
    engine = create_async_engine(platform_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                select(SysTenant.code, SysTenant.db_key).where(SysTenant.deleted_at.is_(None))
            )
            return [(str(code), str(db_key)) for code, db_key in result.all()]
    finally:
        await engine.dispose()


async def build_tasks(args: argparse.Namespace) -> list[MigrationTask]:
    """构建待迁移任务清单。

    Args:
        args: 命令行参数。

    Returns:
        list[MigrationTask]: 任务清单（保序：平台 → 各租户 → 归档）。

    Raises:
        ConfigError: 目标与参数组合非法 / 平台库枚举失败。
    """
    settings = get_settings()
    factory = EngineFactory(settings)
    platform_chain = resolve_chain("platform")
    archive_chain = resolve_chain("archive")
    tenant_chain = resolve_chain("tenant")

    tasks: list[MigrationTask] = []

    def add_tenant(label: str, url: str, schema: str = "") -> None:
        """追加租户链任务。"""
        tasks.append(MigrationTask(chain=tenant_chain, label=label, url=url, schema=schema))

    if args.target in ("all", "platform"):
        platform_url = args.url if args.url and args.target == "platform" else chain_url(platform_chain, settings)
        tasks.append(
            MigrationTask(
                chain=platform_chain,
                label=PLATFORM_DB_KEY,
                url=platform_url,
                schema=args.schema if args.target == "platform" else "",
            )
        )
    if args.target == "tenant":
        if not args.url:
            raise ConfigError("`--target tenant` 需显式 `--url`（单库模式：演练 / 指定库）")
        add_tenant(args.db_key or "tenant", args.url, args.schema)
    elif args.target in ("all", "tenants"):
        if args.db_key:
            add_tenant(args.db_key, args.url or factory.resolved_url(args.db_key), args.schema)
        else:
            platform_url = chain_url(platform_chain, settings)
            records = await _tenant_records(platform_url)
            if not records:
                print("[migrate_tenants] 平台库未注册租户（sys_tenant 为空）")
            for code, db_key in records:
                key = db_key or build_tenant_db_key(code)
                add_tenant(key, factory.resolved_url(key), args.schema)
    if args.target in ("all", "archive"):
        tasks.append(
            MigrationTask(
                chain=archive_chain,
                label="archive",
                url=args.url if args.url and args.target == "archive" else chain_url(archive_chain, settings),
            )
        )
    return tasks


async def run(args: argparse.Namespace) -> int:
    """执行批量迁移。

    Args:
        args: 命令行参数。

    Returns:
        int: 退出码（存在失败为 1）。
    """
    tasks = await build_tasks(args)
    print(f"[migrate_tenants] 待迁移 {len(tasks)} 个目标（target={args.target}）")
    for task in tasks:
        suffix = f" schema={task.schema}" if task.schema else ""
        print(f"[migrate_tenants] {task.chain.name:<8} {task.label:<20} {_masked(task.url)}{suffix}")
    if args.dry_run:
        print("[migrate_tenants] dry-run：不建连、不迁移")
        return 0

    succeeded: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    for task in tasks:
        try:
            head = head_revision(task.chain)
            current = await current_revision(task.url, schema=task.schema)
            if head is not None and current == head:
                skipped.append(task.label)
                print(f"[migrate_tenants] {task.chain.name} {task.label} → 已是最新（跳过）")
                continue
            await asyncio.to_thread(upgrade_chain, task.chain, task.url, schema=task.schema)
        except Exception as exc:  # 单库失败不中断整批
            failed.append(task.label)
            print(f"[migrate_tenants] {task.chain.name} {task.label} → 失败：{type(exc).__name__}: {exc}")
            continue
        succeeded.append(task.label)
        print(
            f"[migrate_tenants] {task.chain.name} {task.label} → 迁移完成（{current or '未迁移'} → {head or '无脚本'}）"
        )

    print(
        f"[migrate_tenants] 汇总：成功 {len(succeeded)}、跳过 {len(skipped)}、失败 {len(failed)}"
        + (f"（失败：{', '.join(failed)}）" if failed else "")
    )
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码。
    """
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(run(args))
    except ConfigError as exc:
        print(f"[migrate_tenants] 失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
