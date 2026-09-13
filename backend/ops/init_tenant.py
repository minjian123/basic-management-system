"""新租户初始化脚本占位：建库 → 迁移 → 幂等种子（真实实现归落库阶段 / 租户管理阶段）。

用法：

```bash
uv run python ops/init_tenant.py --code demo --dry-run
```
"""

import argparse
from collections.abc import Sequence

STEPS: tuple[str, ...] = ("建库", "迁移", "幂等种子")


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="新租户初始化（占位）")
    parser.add_argument("--code", default="demo", help="租户编码（全小写）")
    parser.add_argument("--dry-run", action="store_true", help="仅输出初始化步骤")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码。
    """
    args = build_parser().parse_args(argv)
    if args.dry_run:
        for step in STEPS:
            print(f"[初始化 {args.code}] {step}（dry-run）")
        return 0
    print("[初始化] 真实实现归落库阶段 / 租户管理阶段")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
