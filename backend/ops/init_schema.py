"""ops 显式建表入口：按「服务 × 数据源 × 库」逐库幂等建表（与启动期同一表集派生点）。

用法（与 `ops.migrate_tenants` 同构）：

```bash
cd backend
uv run python -m ops.init_schema --dry-run                      # 清单预演（不建连）
uv run python -m ops.init_schema                                # 全部启用服务 × 各租户 + 归档
uv run python -m ops.init_schema --service platform --target platform
uv run python -m ops.init_schema --target tenants --code demo --code acme
uv run python -m ops.init_schema --target tenant --url "sqlite+aiosqlite:///./bms_platform_demo.db"
uv run python -m ops.init_schema --target tenant \
    --url "dm+dmPython://SYSDBA:pass@host:5236" --schema BMS_MIGRCHECK   # 达梦目标模式
```

- **表集单一来源**：与启动期建表（`db/bootstrap.py::ensure_service_schema`）共用
  `chain_metadata(chain)`（表归属登记派生 ∩ 已有模型），避免两处表集漂移；
- **任务清单同构**：服务 / 租户 / 单库维度与 `ops.migrate_tenants` 完全一致（复用其任务构建）；
- **幂等**：`create_all(checkfirst=True)`，重复执行无副作用；逐库输出「新建 N 表 / 已存在 M 表」；
- **失败不中断**：单库失败记 ERROR 并继续下一库，末尾汇总；存在失败时退出码 1；
- **方言**：SQLite / MySQL / PostgreSQL / 达梦一律支持（达梦建表前切到 `--schema` 或连接串
  `database` 段指定的模式）；
- **`--dry-run`**：仅打印清单（连接串脱敏）与库数量统计，不建连、不建表。
"""

import argparse
import asyncio
from collections import Counter
from dataclasses import dataclass

from sqlalchemy.engine import make_url

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ConfigError
from bms_core.core.objects import BaseValueObject
from bms_core.db.bootstrap import apply_chain_schema
from bms_core.db.migration import DATASOURCE_ARCHIVE, DATASOURCE_PLATFORM, DATASOURCE_TENANT
from ops.migrate_tenants import MigrationTask, build_task_parser, build_tasks

_LABELS = {
    DATASOURCE_PLATFORM: "平台服务库",
    DATASOURCE_TENANT: "服务租户库",
    DATASOURCE_ARCHIVE: "归档库",
}


@dataclass(frozen=True)
class SchemaSummary(BaseValueObject):
    """批量建表结果汇总（成功 / 跳过 / 失败 + 新建与已存在表数）。"""

    succeeded: tuple[str, ...]
    skipped: tuple[str, ...]
    failed: tuple[str, ...]
    created: int
    existing: int

    @property
    def exit_code(self) -> int:
        """退出码（存在失败为 1）。

        Returns:
            int: 0 全成功 / 1 存在失败。
        """
        return 1 if self.failed else 0


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器（任务清单参数与批量迁移同构）。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    return build_task_parser("ops 显式建表入口（服务 × 数据源 × 库；幂等）")


def _masked(url: str) -> str:
    """连接串脱敏（隐藏密码）。

    Args:
        url: 连接串。

    Returns:
        str: 脱敏连接串。
    """
    return make_url(url).render_as_string(hide_password=True)


def _counts(tasks: ConcurrentStableList[MigrationTask]) -> str:
    """库数量统计（按库类别）。

    Args:
        tasks: 任务清单。

    Returns:
        str: 统计文案（如「平台服务库 9 / 服务租户库 18」）。
    """
    by_datasource = Counter(task.chain.datasource for task in tasks)
    detail = "、".join(f"{_LABELS.get(name, name)} {count}" for name, count in sorted(by_datasource.items()))
    return f"共 {len(tasks)} 个目标（{detail}）"


async def run_tasks(tasks: ConcurrentStableList[MigrationTask]) -> SchemaSummary:
    """逐库幂等建表（单库失败不中断）。

    Args:
        tasks: 任务清单。

    Returns:
        SchemaSummary: 结果汇总（含新建 / 已存在表数）。
    """
    succeeded: ConcurrentStableList[str] = ConcurrentStableList()
    skipped: ConcurrentStableList[str] = ConcurrentStableList()
    failed: ConcurrentStableList[str] = ConcurrentStableList()
    created = 0
    existing = 0
    for task in tasks:
        try:
            outcome = await apply_chain_schema(task.chain, task.url, target=task.label, schema=task.schema)
        except Exception as exc:  # 单库失败不中断整批（缺库 / 权限 / 驱动异常）
            failed.add(task.label)
            print(f"[init_schema] {task.chain.name} {task.label} → 失败：{type(exc).__name__}: {exc}")
            continue
        if not outcome.total:
            skipped.add(task.label)
            print(f"[init_schema] {task.chain.name} {task.label} → 无表集（跳过）")
            continue
        created += outcome.created
        existing += outcome.existing
        succeeded.add(task.label)
        print(
            f"[init_schema] {task.chain.name} {task.label} → 新建 {outcome.created} / "
            f"已存在 {outcome.existing}（共 {outcome.total}）"
        )
    return SchemaSummary(
        succeeded=tuple(succeeded), skipped=tuple(skipped), failed=tuple(failed), created=created, existing=existing
    )


def report(summary: SchemaSummary, tasks: ConcurrentStableList[MigrationTask]) -> int:
    """输出汇总与库数量统计，返回退出码。

    Args:
        summary: 结果汇总。
        tasks: 任务清单（统计库数量）。

    Returns:
        int: 退出码（存在失败为 1）。
    """
    print(
        f"[init_schema] 汇总：成功 {len(summary.succeeded)}、跳过 {len(summary.skipped)}、"
        f"失败 {len(summary.failed)}；建表新建 {summary.created} / 已存在 {summary.existing}"
        + (f"（失败：{', '.join(summary.failed)}）" if summary.failed else "")
    )
    print(f"[init_schema] 库数量：{_counts(tasks)}")
    return summary.exit_code


async def run(args: argparse.Namespace) -> int:
    """执行批量建表。

    Args:
        args: 命令行参数。

    Returns:
        int: 退出码（存在失败为 1）。
    """
    tasks = await build_tasks(args)
    print(f"[init_schema] 待建表 {len(tasks)} 个目标（target={args.target}）")
    for task in tasks:
        suffix = f" schema={task.schema}" if task.schema else ""
        print(f"[init_schema] {task.chain.name:<22} {task.label:<28} {_masked(task.url)}{suffix}")
    if args.dry_run:
        print(f"[init_schema] 库数量：{_counts(tasks)}")
        print("[init_schema] dry-run：不建连、不建表")
        return 0
    return report(await run_tasks(tasks), tasks)


def main(argv: ConcurrentStableList[str] | None = None) -> int:
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
        print(f"[init_schema] 失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
