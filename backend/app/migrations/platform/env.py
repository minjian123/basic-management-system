"""Alembic 迁移环境：平台库。

URL 不从 alembic.ini 读取，统一经 app.core.config 加载（config.toml 公共段 + 环境段 + 环境变量）。
同步引擎用于执行迁移（aiosqlite→pysqlite、aiomysql→pymysql 方言映射见 _sync_url）。
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app import models  # noqa: F401  pyright: ignore[reportUnusedImport]  注册模型元数据
from app.core.config import get_settings
from app.db.base import Base

_ = models

config = context.config
target_metadata = Base.metadata


def _sync_url(url: str) -> str:
    """异步连接串 → 同步连接串（Alembic 用同步驱动执行迁移）。"""
    return (
        url.replace("sqlite+aiosqlite", "sqlite+pysqlite")
        .replace("mysql+aiomysql", "mysql+pymysql")
        .replace("postgresql+psycopg", "postgresql+psycopg")
    )


def run_migrations_offline() -> None:
    """离线模式：不连接数据库生成 SQL。"""
    context.configure(
        url=_sync_url(get_settings().database.platform_url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接平台库执行迁移。"""
    connectable = create_engine(_sync_url(get_settings().database.platform_url), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
