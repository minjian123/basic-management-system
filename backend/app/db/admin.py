"""库级建删能力：MySQL / PostgreSQL 建删数据库、SQLite 建删文件、达梦建删模式。

- 供 `ops/db_admin.py`（迁移演练）、`ops/init_tenant.py`（新租户建库）与后续
  `ops/test_db.py`（三库测试库流程，01_05）复用；迁移本身走 Alembic（结构变更唯一入口）。
- 管理连接串：显式 `admin_url` 优先；未提供时按方言推导（MySQL 去库名、PG 用 `postgres` 库、
  SQLite / 达梦回落目标连接串）。
- **幂等且不擅动**：`create` 命中已存在即跳过（不重建、不清空）；`drop` 目标不存在即跳过。
- 达梦无 `CREATE DATABASE`：以**模式**为库级隔离单位（`CREATE SCHEMA` / `DROP SCHEMA ... CASCADE`），
  模式切换由迁移环境经 `-x schema=` 完成（见 `alembic/env.py`）。
- 管理连接串含密码：**一律不写入日志**，仅以脱敏形态展示。
"""

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.base import BaseObject
from app.core.exceptions import ConfigError

_SQLITE = "sqlite"
_DM = "dm"
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
"""库名 / 模式名合法形态（防拼接注入；长度限 63 字符）。"""

_SQLITE_SUFFIXES = ("", "-journal", "-wal", "-shm")
"""SQLite 删库时一并清理的附属文件后缀。"""

_PG_ADMIN_DATABASE = "postgres"
"""PostgreSQL 管理连接默认库。"""


@dataclass(frozen=True)
class DatabaseTarget(BaseObject):
    """建删库目标解析结果（方言 / 目标名 / 目标连接串 / 管理连接串）。"""

    dialect: str
    """方言名（`mysql` / `postgresql` / `sqlite` / `dm`）。"""

    name: str
    """目标名：MySQL / PG 为库名；SQLite 为文件路径；达梦为模式名（大写）。"""

    url: str
    """目标连接串（含密码；禁止写入日志）。"""

    admin_url: str
    """管理连接串（含密码；禁止写入日志）。"""

    @property
    def is_file(self) -> bool:
        """是否 SQLite 文件型目标。

        Returns:
            bool: 文件型 True。
        """
        return self.dialect == _SQLITE

    def describe(self) -> str:
        """脱敏描述（日志与命令行输出用）。

        Returns:
            str: 形如 `mysql bms_migrcheck` 的脱敏描述。
        """
        return f"{self.dialect} {self.name}"


def database_name_of(url: str) -> str:
    """取连接串目标名（库名 / 文件路径 / 模式名占位）。

    Args:
        url: 数据库连接串。

    Returns:
        str: 目标名。

    Raises:
        ConfigError: SQLite 连接串缺文件路径。
    """
    parsed = make_url(url)
    dialect = parsed.get_backend_name()
    if dialect == _SQLITE:
        if not parsed.database:
            raise ConfigError("SQLite 连接串缺少数据库文件路径")
        return parsed.database
    return parsed.database or ""


def admin_url_for(url: str, *, override: str = "") -> str:
    """推导管理连接串（显式覆盖优先；SQLite / 达梦回落目标连接串）。

    Args:
        url: 目标连接串。
        override: 显式管理连接串（空串表示未指定）。

    Returns:
        str: 管理连接串（含密码）。
    """
    if override:
        return override
    parsed = make_url(url)
    dialect = parsed.get_backend_name()
    if dialect in (_SQLITE, _DM):
        return url
    if dialect == "postgresql":
        return parsed.set(database=_PG_ADMIN_DATABASE).render_as_string(hide_password=False)
    # MySQL 管理连接不带库名（`URL.set(database=None)` 不会清库，须用 `_replace`）
    return parsed._replace(database=None).render_as_string(hide_password=False)  # pyright: ignore[reportPrivateUsage]


def resolve_target(url: str, *, name: str | None = None, admin_url: str = "") -> DatabaseTarget:
    """解析建删库目标（方言 / 目标名 / 连接串 / 管理连接串）。

    Args:
        url: 目标连接串。
        name: 显式目标名（缺省取连接串内库名 / 文件路径）。
        admin_url: 显式管理连接串。

    Returns:
        DatabaseTarget: 目标解析结果。

    Raises:
        ConfigError: 目标名为空或形态非法。
    """
    parsed = make_url(url)
    dialect = parsed.get_backend_name()
    resolved_name = (name or database_name_of(url)).strip()
    if not resolved_name:
        raise ConfigError(f"未指定建库 / 建模式目标名（连接串：{parsed.render_as_string(hide_password=True)}）")
    if dialect == _SQLITE:
        final_name = _normalize_sqlite_path(resolved_name)
    else:
        final_name = resolved_name.upper() if dialect == _DM else resolved_name
        if not _IDENTIFIER_PATTERN.match(final_name):
            raise ConfigError(f"库名 / 模式名形态非法：{final_name}（允许字母 / 数字 / 下划线且不以数字开头）")
    return DatabaseTarget(
        dialect=dialect,
        name=final_name,
        url=url,
        admin_url=admin_url_for(url, override=admin_url),
    )


async def run_statements(admin_url: str, statements: str) -> None:
    """执行单条管理语句（公开入口；自动提交，达梦走同步线程）。

    供 `ops/test_db.py` 建测试账号与授权等管理操作复用（与建删库共用同一执行路径）。

    Args:
        admin_url: 管理连接串（含密码；禁止写入日志）。
        statements: 管理语句。
    """
    await _execute(admin_url, statements)


async def fetch_rows(admin_url: str, statement: str, *, name: str) -> Sequence[object]:
    """执行带 `:name` 绑定的管理查询（公开入口；自动提交，达梦走同步线程）。

    Args:
        admin_url: 管理连接串（含密码；禁止写入日志）。
        statement: 查询语句（含 `:name` 绑定）。
        name: 绑定值（如角色名 / 库名）。

    Returns:
        Sequence[object]: 结果行列表。
    """
    return await _fetch(admin_url, statement, name=name)


def _normalize_sqlite_path(name: str) -> str:
    """SQLite 目标路径归一（相对路径按当前工作目录解析）。

    Args:
        name: 连接串中的文件路径。

    Returns:
        str: 归一化后的路径字符串。
    """
    path = Path(name)
    return str(path if path.is_absolute() else path.resolve())


async def database_exists(target: DatabaseTarget) -> bool:
    """目标库 / 模式 / 文件是否存在。

    Args:
        target: 目标解析结果。

    Returns:
        bool: 存在 True。
    """
    if target.is_file:
        return Path(target.name).is_file()
    statement = {
        "mysql": "SELECT 1 FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = :name",
        "postgresql": "SELECT 1 FROM pg_database WHERE datname = :name",
        # 达梦：`ALL_USERS` 只含用户、不含 `CREATE SCHEMA` 建出的模式 → 查系统对象表
        _DM: "SELECT 1 FROM SYS.SYSOBJECTS WHERE TYPE$ = 'SCH' AND NAME = :name",
    }[target.dialect]
    rows = await _fetch(target.admin_url, statement, name=target.name)
    return bool(rows)


async def create_database(target: DatabaseTarget) -> bool:
    """幂等建库 / 建模式 / 建文件（已存在即跳过）。

    Args:
        target: 目标解析结果。

    Returns:
        bool: 新建 True；已存在（跳过）False。
    """
    if target.is_file:
        if await database_exists(target):
            return False
        path = Path(target.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        return True
    if await database_exists(target):
        return False
    statements = {
        "mysql": (
            f"CREATE DATABASE IF NOT EXISTS `{target.name}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
        ),
        "postgresql": f"CREATE DATABASE \"{target.name}\" ENCODING 'UTF8'",
        _DM: f"CREATE SCHEMA {target.name}",
    }[target.dialect]
    await _execute(target.admin_url, statements)
    return True


async def drop_database(target: DatabaseTarget) -> bool:
    """幂等删库 / 删模式 / 删文件（不存在即跳过）。

    Args:
        target: 目标解析结果。

    Returns:
        bool: 删除 True；不存在（跳过）False。
    """
    if target.is_file:
        path = Path(target.name)
        if not path.exists() and not any(Path(f"{target.name}{suffix}").exists() for suffix in _SQLITE_SUFFIXES):
            return False
        for suffix in _SQLITE_SUFFIXES:
            Path(f"{target.name}{suffix}").unlink(missing_ok=True)
        return True
    if not await database_exists(target):
        return False
    statements = {
        "mysql": f"DROP DATABASE IF EXISTS `{target.name}`",
        "postgresql": f'DROP DATABASE IF EXISTS "{target.name}"',
        _DM: f"DROP SCHEMA {target.name} CASCADE",
    }[target.dialect]
    await _execute(target.admin_url, statements)
    return True


async def _execute(admin_url: str, statements: str) -> None:
    """执行管理语句（自动提交；达梦走同步驱动线程）。

    Args:
        admin_url: 管理连接串。
        statements: 单条管理语句。
    """
    if make_url(admin_url).get_backend_name() == _DM:
        await asyncio.to_thread(_execute_sync, admin_url, statements)
        return
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(text(statements))
    finally:
        await engine.dispose()


def _execute_sync(admin_url: str, statements: str) -> None:
    """同步执行管理语句（达梦等无异步方言的驱动）。

    Args:
        admin_url: 管理连接串。
        statements: 单条管理语句。
    """
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        with engine.connect() as connection:
            connection.execute(text(statements))
    finally:
        engine.dispose()


async def _fetch(admin_url: str, statement: str, *, name: str) -> Sequence[object]:
    """执行存在性查询（自动提交；达梦走同步驱动线程）。

    Args:
        admin_url: 管理连接串。
        statement: 查询语句（含 `:name` 绑定）。
        name: 目标名。

    Returns:
        Sequence[object]: 结果行列表。
    """
    if make_url(admin_url).get_backend_name() == _DM:
        return await asyncio.to_thread(_fetch_sync, admin_url, statement, name)
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text(statement), {"name": name})
            return list(result.all())
    finally:
        await engine.dispose()


def _fetch_sync(admin_url: str, statement: str, name: str) -> Sequence[object]:
    """同步执行存在性查询（达梦等无异步方言的驱动）。

    Args:
        admin_url: 管理连接串。
        statement: 查询语句（含 `:name` 绑定）。
        name: 目标名。

    Returns:
        Sequence[object]: 结果行列表。
    """
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        with engine.connect() as connection:
            return list(connection.execute(text(statement), {"name": name}).all())
    finally:
        engine.dispose()
