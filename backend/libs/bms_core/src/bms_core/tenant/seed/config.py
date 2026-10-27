"""系统参数种子脚本（幂等）：向租户库写入平台默认参数（需求 03-8）。

用法：

```bash
cd backend
# 先迁移（首次；读配置解析租户库）：
uv run alembic -n alembic:platform:tenant upgrade head
# 再种子（可重复执行）：
uv run python -m ops.seed_config
```

- URL 解析：`BMS_MIGRATION_URL` 环境变量 > 配置租户库模板（`database.tenants.url`）；
- 幂等：存在即跳过；输出新增行数；不建表（建表走 Alembic 迁移）。
"""

import argparse
import asyncio
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.config.seed import PLATFORM_CONFIG_DEFAULTS, seed_configs
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableList,
)
from bms_core.core.config import get_settings
from bms_core.tenant.seed.contract import ExpectedRow

RUN_IMAGE = "*"
"""本脚本只依赖 `bms_core` 与 `ops`（不导入任何服务包），任意服务镜像均可运行。"""


async def seed_configs_entry(session: AsyncSession, args: ConcurrentStableDict[str, object]) -> None:
    """XA 分支入口（07B `02_03`）：在分支会话内幂等写入系统参数默认值。

    **与 `main()` 的分工**：那个是内部单步（自建 engine，排障用）；本入口不建连接。

    Args:
        session: 已绑定 XA 分支连接的会话。
        args: 分支参数（本种子不消费）。
    """
    del args
    await seed_configs(session)


def _database_url() -> str:
    """取种子目标 URL（环境变量 > 配置租户库模板）。

    Returns:
        str: 数据库 URL。
    """
    env_url = os.environ.get("BMS_MIGRATION_URL", "")
    if env_url:
        return env_url
    return get_settings().database.tenants.url


async def _run() -> int:
    """执行种子写入。

    Returns:
        int: 新增行数。
    """
    engine = create_async_engine(_database_url())
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            return await seed_configs(session)
    finally:
        await engine.dispose()


def expected_rows() -> ConcurrentStableList[ExpectedRow]:
    """系统参数默认值的期望行（冲突预检用；详设 §3.5）。

    **纯函数**：只读常量 `PLATFORM_CONFIG_DEFAULTS`，不连库、不写库。比对字段为参数值
    （键相同但值被改过即视为冲突——参数默认值漂移必须显式处置，不静默覆盖）。

    Returns:
        ConcurrentStableList[ExpectedRow]: 期望行（每个默认参数一条）。
    """
    rows: ConcurrentStableList[ExpectedRow] = ConcurrentStableList()
    for seed in PLATFORM_CONFIG_DEFAULTS:
        rows.add(
            ExpectedRow(
                table="sys_config",
                key=ConcurrentStableFrozenDict({"config_key": seed.config_key}),
                values=ConcurrentStableFrozenDict({"value": seed.value}),
            )
        )
    return rows


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="系统参数种子（幂等）")
    parser.add_argument("--dry-run", action="store_true", help="仅输出目标库（不建连）")
    return parser


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码。
    """
    args = build_parser().parse_args(argv)
    if args.dry_run:
        print(f"[seed_config] 目标库：{_database_url()}（dry-run）")
        return 0
    created = asyncio.run(_run())
    print(f"[seed_config] 新增 {created} 行（幂等；重复执行输出 0）")
    return 0


if __name__ == "__main__":  # pragma: no cover - 模块直跑入口（部署与用例都走 main()）
    raise SystemExit(main())
