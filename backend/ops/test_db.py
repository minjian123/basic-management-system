"""三库测试库流程占位：`plan` / `create` / `migrate` / `drop`（真实执行归落库阶段）。

用法：

```bash
# 计划（无副作用；CI 常跑 job 与本地核对用）
uv run python -m ops.test_db plan --engine mysql
# 真库阶段串联（占位期一律只打印计划）
uv run python -m ops.test_db create --engine mysql --execute
```

占位口径（见《项目骨架 · 04_02 详细设计》§4.2）：默认计划模式；带 `--execute` 也仅打印占位提示，
**不建库、不迁移、不删库**；真实执行随首个落库阶段填实现（同时接通 Alembic `env.py` 在线分支）。

库清单为**唯一事实源**，须与 `.gitlab-ci.yml` 中 `BMS_TEST_DB_URL` 的库名逐字一致。
调用一律用**模块方式**（`uv run python -m ops.test_db`）：直接 `python ops/test_db.py` 时
`sys.path[0]` 为脚本目录，脚本内引用 `app.*`（如读配置基座）会 `ModuleNotFoundError`
（与 `ops/check_modules.py` 同一坑，04_01 已实测）。
"""

import argparse
from collections.abc import Sequence

#: 测试库 / 模式名（唯一事实源；与 .gitlab-ci.yml 的 BMS_TEST_DB_URL 逐字一致）
TEST_DATABASES: dict[str, str] = {
    "mysql": "bms_test_mysql",
    "postgres": "bms_test_pg",
    "dm8": "BMS_TEST_DM",
}

#: 流程步骤（建库 → 迁移 → 集成用例 → 删库清理；job 内独立、互不污染）
FLOW_STEPS: tuple[str, ...] = ("建库", "迁移", "集成用例", "删库清理")

#: 占位提示（真实执行归落库阶段）
PLACEHOLDER_NOTICE = "真实执行归落库阶段（本阶段占位）"

ENGINE_CHOICES: tuple[str, ...] = ("mysql", "postgres", "dm8")


def resolve_test_database(engine: str) -> str:
    """按方言取测试库 / 模式名。

    Args:
        engine: `mysql` / `postgres` / `dm8`。

    Returns:
        str: 测试库（达梦为模式名）。
    """
    return TEST_DATABASES[engine]


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="三库测试库流程（占位）")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="输出固定库清单与执行步骤（无副作用）")
    plan.add_argument("--engine", required=True, choices=ENGINE_CHOICES)

    for name, help_text in (
        ("create", "建库（真实执行归落库阶段）"),
        ("migrate", "Alembic 迁移（真实执行归落库阶段）"),
        ("drop", "删库清理（真实执行归落库阶段）"),
    ):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("--engine", required=True, choices=ENGINE_CHOICES)
        sub.add_argument(
            "--execute",
            action="store_true",
            help="请求真实执行（占位期仅打印占位提示，不产生副作用）",
        )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码（计划 / 占位均为 0；参数非法由 argparse 以 2 退出）。
    """
    args = build_parser().parse_args(argv)
    database = resolve_test_database(args.engine)

    if args.command == "plan":
        print(f"[test-db] {args.engine} → {database}")
        for step in FLOW_STEPS:
            print(f"[test-db] {step}（plan）")
        return 0

    mode = "计划模式" if not args.execute else "占位（--execute）"
    print(f"[test-db] {args.command} {args.engine} → {database}（{mode}）")
    if not args.execute:
        for step in FLOW_STEPS:
            print(f"[test-db] {step}（plan）")
    else:
        print(f"[test-db] {PLACEHOLDER_NOTICE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
