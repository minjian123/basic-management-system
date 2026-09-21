"""Alembic 迁移环境：离线 / 在线两模式（首个迁移随字典真实取数与缓存落地，02-4-27）。

- URL 解析优先级：`-x url=<URL>`（显式覆盖）> `BMS_MIGRATION_URL` 环境变量 > 配置（缺省租户库模板
  `database.tenants.url`）。租户库批量迁移随阶段二窗口（`ops/migrate_tenants.py`）。
- 在线模式：异步引擎（`create_async_engine`）+ `connection.run_sync(context.run_migrations)`；
  四库（SQLite / MySQL / PostgreSQL / 达梦）共用本环境，方言差异由模型与迁移脚本兼容口径承载。
- 目标元数据：`Base.metadata`（导入模型包以注册全部表；新模型包需在此导入）。
"""

import asyncio
import os
from collections.abc import Mapping

from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

import app.dict.models
import app.listing.models  # noqa: F401 - 导入以注册查询方案表元数据
from alembic import context
from app.core.config import get_settings
from app.models.base import Base

config = context.config

target_metadata = Base.metadata


def _database_url() -> str:
    """取迁移目标 URL（显式参数 > 环境变量 > 配置租户库模板）。

    Returns:
        str: 数据库 URL。
    """
    x_args: Mapping[str, str] = context.get_x_argument(as_dictionary=True)
    explicit = x_args.get("url")
    if explicit:
        return explicit
    env_url = os.environ.get("BMS_MIGRATION_URL", "")
    if env_url:
        return env_url
    return get_settings().database.tenants.url


def run_migrations_offline() -> None:
    """离线模式：仅生成 SQL，不连接数据库。"""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    """在线迁移主体（同步回调，由 `run_sync` 调用）。

    Args:
        connection: 同步连接（异步连接的同步封装）。
    """
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    """在线模式：异步引擎连接并执行迁移。"""
    engine = create_async_engine(_database_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    """在线模式入口。"""
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
