"""批量迁移脚本占位：逐库执行 Alembic 迁移（真实迁移归落库阶段）。

用法：

```bash
uv run python ops/migrate_tenants.py --target all --db mysql --dry-run
```

本阶段 `--dry-run` 输出固定库清单；逐库执行 / 失败不中断 / 重跑幂等为约定口径。
"""

import argparse
from collections.abc import Sequence

PLATFORM_DB = "bms_platform"
TENANT_DB = "bms_tenant_demo"
ARCHIVE_DB = "bms_archive"
FIXED_DATABASES: tuple[str, ...] = (PLATFORM_DB, TENANT_DB, ARCHIVE_DB)


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="批量迁移租户库（占位）")
    parser.add_argument("--target", default="all", choices=("all", "platform", "tenant_demo"))
    parser.add_argument("--db", default="sqlite", choices=("mysql", "postgres", "dameng", "sqlite"))
    parser.add_argument("--dry-run", action="store_true", help="仅输出目标库清单")
    return parser


def resolve_databases(target: str) -> list[str]:
    """按目标解析待迁移库清单。

    Args:
        target: `all` / `platform` / `tenant_demo`。

    Returns:
        list[str]: 库名列表。
    """
    if target == "platform":
        return [PLATFORM_DB]
    if target == "tenant_demo":
        return [TENANT_DB]
    return list(FIXED_DATABASES)


def main(argv: Sequence[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码。
    """
    args = build_parser().parse_args(argv)
    databases = resolve_databases(args.target)
    if args.dry_run:
        for name in databases:
            print(f"[迁移] {args.db} → {name}（dry-run）")
        return 0
    print("[迁移] 真实迁移归落库阶段（本阶段占位）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
