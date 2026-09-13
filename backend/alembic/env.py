"""Alembic 迁移环境骨架（真实迁移 / 种子 / 四库方言归落库阶段）。

本阶段仅落结构：URL 经配置基座 / 环境变量读取的口径在此预留；
在线迁移（引擎创建与连接）由落库阶段（认证 / RBAC）完善。
"""

from alembic import context
from app.core.config import get_settings

config = context.config


def _database_url() -> str:
    """取迁移目标 URL（平台库；租户库批量迁移由 ops 脚本指定）。

    Returns:
        str: 数据库 URL。
    """
    return get_settings().database.platform.url


def run_migrations_offline() -> None:
    """离线模式：仅生成 SQL，不连接数据库。"""
    context.configure(
        url=_database_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：真实连接与迁移执行（归落库阶段）。

    Raises:
        NotImplementedError: 本阶段占位。
    """
    raise NotImplementedError("Alembic 在线迁移由落库阶段（认证 / RBAC）交付")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
