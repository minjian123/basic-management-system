"""库级建删 CLI（迁移演练 / 三库流程复用）：`exists` / `create` / `drop`。

用法：

```bash
cd backend
# 存在性检查
uv run python -m ops.db_admin exists --url "mysql+aiomysql://user:pass@host:3306/bms_migrcheck"
# 建库 / 建模式（幂等：已存在跳过）
uv run python -m ops.db_admin create --url "postgresql+psycopg://user:pass@host:5432/bms_migrcheck"
uv run python -m ops.db_admin create --url "dm+dmPython://SYSDBA:pass@host:5236" --name BMS_MIGRCHECK
# 删库 / 删模式（幂等：不存在跳过）
uv run python -m ops.db_admin drop --url "sqlite+aiosqlite:////tmp/bms_migrcheck.db"
```

- 目标名缺省取连接串内库名（SQLite 为文件路径；达梦为模式名，名称大写归一）；
- 管理连接串缺省按方言推导（MySQL 去库名、PG 用 `postgres` 库、SQLite / 达梦回落目标连接串），
  可用 `--admin-url` 显式指定（凭据见本地资源文档，不入库）；
- 建删能力在 `app/db/admin.py`（幂等、不擅动既有对象）：已存在跳过、不存在跳过；
- `--dry-run` 仅解析并打印目标（连接串脱敏），不建连。
"""

import argparse
import asyncio
from collections.abc import Sequence

from sqlalchemy.engine import make_url

from bms_core.core.exceptions import ConfigError
from bms_core.db.admin import (
    DatabaseTarget,
    create_database,
    database_exists,
    drop_database,
    resolve_target,
)


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="库级建删（库 / 模式 / 文件；幂等）")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("exists", "存在性检查"),
        ("create", "建库 / 建模式 / 建文件（幂等）"),
        ("drop", "删库 / 删模式 / 删文件（幂等）"),
    ):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("--url", required=True, help="目标连接串（含密码；禁止写入日志）")
        sub.add_argument("--name", default="", help="目标名（缺省取连接串内库名 / 文件路径）")
        sub.add_argument("--admin-url", default="", help="管理连接串（缺省按方言推导）")
        sub.add_argument("--dry-run", action="store_true", help="仅解析并打印目标（不建连）")
    return parser


def _describe(target: DatabaseTarget) -> str:
    """脱敏描述目标（连接串隐藏密码）。

    Args:
        target: 目标解析结果。

    Returns:
        str: 脱敏描述。
    """
    url = make_url(target.url).render_as_string(hide_password=True)
    admin = make_url(target.admin_url).render_as_string(hide_password=True)
    return f"{target.describe()} | 目标 {url} | 管理 {admin}"


async def _run(args: argparse.Namespace) -> int:
    """执行子命令。

    Args:
        args: 命令行参数。

    Returns:
        int: 退出码。
    """
    target = resolve_target(args.url, name=args.name or None, admin_url=args.admin_url)
    print(f"[db_admin] 目标：{_describe(target)}")
    if args.dry_run:
        print(f"[db_admin] {args.command}（dry-run：不建连）")
        return 0
    if args.command == "exists":
        exists = await database_exists(target)
        print(f"[db_admin] exists → {'存在' if exists else '不存在'}")
        return 0
    if args.command == "create":
        created = await create_database(target)
        print(f"[db_admin] create → {'新建' if created else '已存在（跳过）'}")
        return 0
    dropped = await drop_database(target)
    print(f"[db_admin] drop → {'已删除' if dropped else '不存在（跳过）'}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码（解析 / 连接失败为 1）。
    """
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except ConfigError as exc:
        print(f"[db_admin] 失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
