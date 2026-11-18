"""首页工作台用例的数据库辅助（共享基座：**唯一允许建引擎的位置**）。

为什么放在 `tests_support`：测试库隔离护栏（`base test-db-isolation`）把「用例自建 SQLite 引擎」
列为违规（单库叠加口径），只放行共享基座模块；本模块即该基座（与 `tests_support/form_design.py` 同口径）。

**隔离口径**：单库叠加下全 worker 共用一份租户库，整表 delete 会删掉并行中他人用例的行——本域的隔离
靠**用例命名空间**（卡片 `code` / 角色 `code` 由 `ns.prefix` 派生）；唯一按主体清理的是**个人布局偏好**
（同一测试主体共用固定键 `dashboard.layout`，用例前后按 `(user_id, pref_key)` 精确清除，不清整表）。
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator, Callable, Iterable
from contextlib import asynccontextmanager
from typing import Any, cast

from sqlalchemy import Table, delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.base import Base
from bms_core.models.platform.dashboard import (
    SCOPE_PLATFORM,
    SysDashboardCard,
    SysDashboardCardI18n,
    SysDashboardTemplate,
)
from bms_core.models.platform.role import SysRole, SysUserRole

__all__ = [
    "DASHBOARD_MODELS",
    "PREF_KEY",
    "assign_role",
    "clear_dashboard_pref",
    "delete_role",
    "ensure_card",
    "ensure_dashboard_tables",
    "find_platform_template",
    "memory_dashboard_session",
    "read_pref",
    "role_id_by_code",
    "seed_card",
    "seed_role",
    "seed_template",
    "set_card_status",
    "tenant_url",
]

DASHBOARD_MODELS: ConcurrentStableList[Any] = ConcurrentStableList(
    (SysDashboardCard, SysDashboardCardI18n, SysDashboardTemplate)
)
"""工作台三表（只用于「确保存在」，不做清场）。"""

PREF_KEY = "dashboard.layout"


def _plain(value: object) -> object:
    """把基座并发集合递归转内置容器（`json.dumps` 不接受非内置容器）。

    Args:
        value: 任意值。

    Returns:
        object: 可 JSON 序列化的等价结构。
    """
    if value is None or isinstance(value, str | int | float | bool):
        return value
    entries = getattr(value, "items", None)
    if callable(entries):
        pairs = cast("Callable[[], Iterable[tuple[object, object]]]", entries)()
        return {str(key): _plain(item) for key, item in pairs}
    if hasattr(value, "__iter__"):
        return [_plain(item) for item in cast("Iterable[object]", value)]
    return value
"""个人布局偏好键（与本域常量一致）。"""


def tenant_url() -> str:
    """当前用例的共享测试租户库连接串。

    Returns:
        str: 租户库连接串。
    """
    return os.environ["BMS_DATABASE__TENANTS__URL"]


@asynccontextmanager
async def memory_dashboard_session() -> AsyncGenerator[AsyncSession]:
    """进程内内存库会话（工作台三表已建；种子类用例专用，避免污染共享测试库）。

    Yields:
        AsyncSession: 会话（退出时释放引擎）。
    """
    engine = create_async_engine(  # own_db: 共享基座模块内建引擎（测试库隔离护栏放行点）
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    try:
        tables = [cast("Table", model.__table__) for model in DASHBOARD_MODELS]
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


async def ensure_dashboard_tables(url: str) -> None:
    """确保工作台三表存在（缺则建；不清空）。

    Args:
        url: 数据库连接串。
    """
    engine = create_async_engine(url)  # own_db: 共享基座模块内建引擎（测试库隔离护栏放行点）
    try:
        tables = [cast("Table", model.__table__) for model in DASHBOARD_MODELS]
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables, checkfirst=True))
    finally:
        await engine.dispose()


async def seed_card(url: str, code: str, **overrides: object) -> int:
    """直插一张卡片。

    Args:
        url: 数据库连接串。
        code: 卡片标识。
        **overrides: 覆盖字段（`card_type` / `status` / `name` / `render_key` / `dataset_id` /
            `chart_type` / `chart_config` / `default_width` / `default_height` / `sort` /
            `data_endpoint` / `mobile_supported`）。

    Returns:
        int: 卡片主键。
    """
    values: dict[str, object] = {
        "code": code,
        "name": str(overrides.get("name", code)),
        "card_type": str(overrides.get("card_type", "builtin")),
        "render_key": str(overrides.get("render_key", code)),
        "data_endpoint": str(overrides.get("data_endpoint", "")),
        "default_width": int(cast("int", overrides.get("default_width", 4))),
        "default_height": int(cast("int", overrides.get("default_height", 2))),
        "mobile_supported": bool(overrides.get("mobile_supported", True)),
        "sort": int(cast("int", overrides.get("sort", 10))),
        "status": str(overrides.get("status", "enabled")),
    }
    if "dataset_id" in overrides:
        values["dataset_id"] = overrides["dataset_id"]
    if "chart_type" in overrides:
        values["chart_type"] = overrides["chart_type"]
    if "chart_config" in overrides:
        values["chart_config"] = overrides["chart_config"]
    engine = create_async_engine(url)  # own_db: 共享基座模块内建引擎（测试库隔离护栏放行点）
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            row = SysDashboardCard(**values)
            session.add(row)
            await session.flush()
            card_id = int(row.id)
            await session.commit()
        return card_id
    finally:
        await engine.dispose()


async def ensure_card(url: str, code: str, **overrides: object) -> int:
    """确保某卡片存在（已有活行返回其主键，否则按给定字段新建）。

    Args:
        url: 数据库连接串。
        code: 卡片标识。
        **overrides: 新建时的覆盖字段（同 `seed_card`）。

    Returns:
        int: 卡片主键。
    """
    engine = create_async_engine(url)  # own_db: 共享基座模块内建引擎（测试库隔离护栏放行点）
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    select(SysDashboardCard.id).where(
                        SysDashboardCard.code == code, SysDashboardCard.deleted_at.is_(None)
                    )
                )
            ).first()
        if row is not None:
            return int(row[0])
    finally:
        await engine.dispose()
    return await seed_card(url, code, **overrides)


async def find_platform_template(url: str) -> int | None:
    """取平台默认模板主键（未配置返回 None）。

    Args:
        url: 数据库连接串。

    Returns:
        int | None: 模板主键。
    """
    engine = create_async_engine(url)  # own_db: 共享基座模块内建引擎（测试库隔离护栏放行点）
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    select(SysDashboardTemplate.id).where(
                        SysDashboardTemplate.scope == SCOPE_PLATFORM,
                        SysDashboardTemplate.deleted_at.is_(None),
                    )
                )
            ).first()
        return None if row is None else int(row[0])
    finally:
        await engine.dispose()


async def seed_template(
    url: str,
    *,
    scope: str = SCOPE_PLATFORM,
    role_id: int = 0,
    name: str = "模板",
    layout: object | None = None,
    status: str = "enabled",
) -> int:
    """直插一份模板（布局缺省为空布局）。

    Args:
        url: 数据库连接串。
        scope: 层级（`platform` / `role`）。
        role_id: 角色主键（平台层级固定 0）。
        name: 模板名称。
        layout: 布局配置（缺省 `{"cards": []}`）。
        status: 状态。

    Returns:
        int: 模板主键。
    """
    payload: object = {"cards": []} if layout is None else layout
    engine = create_async_engine(url)  # own_db: 共享基座模块内建引擎（测试库隔离护栏放行点）
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            row = SysDashboardTemplate(
                scope=scope,
                role_id=role_id,
                name=name,
                layout_config=json.dumps(_plain(payload), ensure_ascii=False),
                status=status,
            )
            session.add(row)
            await session.flush()
            template_id = int(row.id)
            await session.commit()
        return template_id
    finally:
        await engine.dispose()


async def set_card_status(url: str, code: str, status: str) -> None:
    """直接改卡片状态（停用场景造数）。

    Args:
        url: 数据库连接串。
        code: 卡片标识。
        status: 目标状态。
    """
    engine = create_async_engine(url)  # own_db: 共享基座模块内建引擎（测试库隔离护栏放行点）
    try:
        async with engine.begin() as connection:
            await connection.execute(
                update(SysDashboardCard).where(SysDashboardCard.code == code).values(status=status)
            )
    finally:
        await engine.dispose()


async def clear_dashboard_pref(url: str, user_id: int = 1001) -> None:
    """精确清除某用户的个人布局偏好（不清整表）。

    Args:
        url: 数据库连接串。
        user_id: 用户主键。
    """
    engine = create_async_engine(url)  # own_db: 共享基座模块内建引擎（测试库隔离护栏放行点）
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM sys_user_preference WHERE CAST(user_id AS INTEGER) = :user_id AND pref_key = :key"),
                {"user_id": user_id, "key": PREF_KEY},
            )
    finally:
        await engine.dispose()


async def read_pref(url: str, user_id: int = 1001) -> str | None:
    """读取某用户的个人布局偏好原文（未设置为 None）。

    Args:
        url: 数据库连接串。
        user_id: 用户主键。

    Returns:
        str | None: `pref_value` 原文。
    """
    engine = create_async_engine(url)  # own_db: 共享基座模块内建引擎（测试库隔离护栏放行点）
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "SELECT pref_value FROM sys_user_preference "
                        "WHERE CAST(user_id AS INTEGER) = :user_id AND pref_key = :key AND deleted_at IS NULL"
                    ),
                    {"user_id": user_id, "key": PREF_KEY},
                )
            ).first()
        return None if row is None else str(row[0])
    finally:
        await engine.dispose()


async def seed_role(url: str, code: str, *, role_type: str = "custom", status: str = "enabled") -> int:
    """直插一个角色（用例命名空间派生 `code`）。

    Args:
        url: 数据库连接串。
        code: 角色码。
        role_type: 角色类型（`custom` / `system` / `platform_admin` 等）。
        status: 状态。

    Returns:
        int: 角色主键。
    """
    engine = create_async_engine(url)  # own_db: 共享基座模块内建引擎（测试库隔离护栏放行点）
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            row = SysRole(form_key=code, code=code, name=code, role_type=role_type, status=status)
            session.add(row)
            await session.flush()
            role_id = int(row.id)
            await session.commit()
        return role_id
    finally:
        await engine.dispose()


async def assign_role(url: str, role_id: int, user_id: int) -> None:
    """把角色分配给用户（`(role_id, user_id)` 已存在则跳过）。

    Args:
        url: 数据库连接串。
        role_id: 角色主键。
        user_id: 用户主键。
    """
    engine = create_async_engine(url)  # own_db: 共享基座模块内建引擎（测试库隔离护栏放行点）
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            existing = (
                await session.execute(
                    select(SysUserRole).where(SysUserRole.role_id == role_id, SysUserRole.user_id == user_id)
                )
            ).scalars().first()
            if existing is None:
                session.add(SysUserRole(role_id=role_id, user_id=user_id))
                await session.commit()
    finally:
        await engine.dispose()


async def role_id_by_code(url: str, code: str) -> int:
    """按角色码取角色主键。

    Args:
        url: 数据库连接串。
        code: 角色码。

    Returns:
        int: 角色主键。

    Raises:
        LookupError: 角色码不存在。
    """
    engine = create_async_engine(url)  # own_db: 共享基座模块内建引擎（测试库隔离护栏放行点）
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(select(SysRole.id).where(SysRole.code == code, SysRole.deleted_at.is_(None)))
            ).first()
        if row is None:
            raise LookupError(f"角色码不存在：{code}")
        return int(row[0])
    finally:
        await engine.dispose()


async def delete_role(url: str, code: str) -> None:
    """按角色码物理删除角色与其分配（仅限用例自建角色，避免跨用例残留）。

    Args:
        url: 数据库连接串。
        code: 角色码。
    """
    engine = create_async_engine(url)  # own_db: 共享基座模块内建引擎（测试库隔离护栏放行点）
    try:
        async with engine.begin() as connection:
            row = (await connection.execute(select(SysRole.id).where(SysRole.code == code))).first()
            if row is None:
                return
            role_id = int(row[0])
            await connection.execute(delete(SysUserRole).where(SysUserRole.role_id == role_id))
            await connection.execute(delete(SysDashboardTemplate).where(SysDashboardTemplate.role_id == role_id))
            await connection.execute(delete(SysRole).where(SysRole.id == role_id))
    finally:
        await engine.dispose()
