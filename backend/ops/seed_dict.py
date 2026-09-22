"""字典种子脚本（幂等）：向租户库写入平台常用字典（需求 02-56 / 任务 02-4-27）。

用法：

```bash
cd backend
# 先迁移（首次）：
BMS_MIGRATION_URL="sqlite+aiosqlite:///./bms_tenant_demo.db" uv run alembic upgrade head
# 再种子（可重复执行）：
BMS_MIGRATION_URL="sqlite+aiosqlite:///./bms_tenant_demo.db" uv run python -m ops.seed_dict
```

- URL 解析：`BMS_MIGRATION_URL` 环境变量 > 配置租户库模板（`database.tenants.url`）；
- 幂等：存在即跳过；输出新增行数；不建表（建表走 Alembic 迁移）。
"""

import asyncio
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.config import get_settings
from bms_core.dict.seed import seed_dicts


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
            return await seed_dicts(session)
    finally:
        await engine.dispose()


def main() -> int:
    """入口。

    Returns:
        int: 退出码。
    """
    created = asyncio.run(_run())
    print(f"[seed_dict] 新增 {created} 行（幂等；重复执行输出 0）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
