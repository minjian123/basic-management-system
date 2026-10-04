"""菜单元数据测试替身（Kiwi 2242）：直插业务 / 动作码与表单、清场与发件箱读取。

业务 / 动作权限码无写接口（平台只读口径），用例内直插以构造授权对象；菜单元数据表位于
平台服务库，逐用例清场以隔离数据（会话级平台库共享）。
"""

import os
from typing import cast

import pytest_asyncio
from sqlalchemy import Table, delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.models.base import Base
from bms_core.models.outbox import SysOutbox
from bms_platform.models.menu import (
    SysAction,
    SysActionI18n,
    SysBusiness,
    SysBusinessI18n,
    SysButton,
    SysField,
    SysFieldI18n,
    SysForm,
    SysMenu,
    SysMenuI18n,
)

MENU_MODELS: tuple[type[object], ...] = (
    SysMenuI18n,
    SysMenu,
    SysButton,
    SysFieldI18n,
    SysField,
    SysForm,
    SysActionI18n,
    SysAction,
    SysBusinessI18n,
    SysBusiness,
)
"""菜单元数据十表（清场顺序：先子后父）。"""


def platform_url() -> str:
    """当前用例的平台库连接串（由平台服务 conftest 的 `platform_db` 夹具注入）。

    Returns:
        str: 平台库连接串。
    """
    return os.environ["BMS_DATABASE__PLATFORM__URL"]


async def seed_business(code: str, name: str = "测试业务") -> int:
    """直插业务权限码。

    Args:
        code: 业务码。
        name: 名称。

    Returns:
        int: 业务码主键。
    """
    engine = create_async_engine(platform_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = SysBusiness(code=code, name=name, status="enabled")
            session.add(row)
            await session.flush()
            business_id = row.id
            await session.commit()
        return business_id
    finally:
        await engine.dispose()


async def set_business_status(business_id: int, status: str) -> None:
    """改业务码状态（构造挂接链断裂 / 停用场景）。

    Args:
        business_id: 业务码主键。
        status: 目标状态。
    """
    engine = create_async_engine(platform_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = (await session.execute(select(SysBusiness).where(SysBusiness.id == business_id))).scalars().first()
            if row is not None:
                row.status = status
            await session.commit()
    finally:
        await engine.dispose()


async def seed_action(business_id: int, code: str, name: str = "查询") -> int:
    """直插动作权限码。

    Args:
        business_id: 归属业务码主键。
        code: 动作码。
        name: 名称。

    Returns:
        int: 动作码主键。
    """
    engine = create_async_engine(platform_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = SysAction(business_id=business_id, code=code, name=name, status="enabled")
            session.add(row)
            await session.flush()
            action_id = row.id
            await session.commit()
        return action_id
    finally:
        await engine.dispose()


async def insert_form(menu_id: int, business_id: int, status: str = "enabled") -> int:
    """直插表单（绕过接口校验，用于构造断裂 / 停用场景）。

    Args:
        menu_id: 菜单主键。
        business_id: 业务码主键。
        status: 表单状态。

    Returns:
        int: 表单主键。
    """
    engine = create_async_engine(platform_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = SysForm(menu_id=menu_id, business_id=business_id, component=None, status=status)
            session.add(row)
            await session.flush()
            form_id = row.id
            await session.commit()
        return form_id
    finally:
        await engine.dispose()


async def outbox_types(aggregate_key: str) -> list[str]:
    """取指定聚合键的发件箱事件类型清单。

    Args:
        aggregate_key: 聚合 / 分区键。

    Returns:
        list[str]: 事件类型清单。
    """
    engine = create_async_engine(platform_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            statement = select(SysOutbox.event_type).where(SysOutbox.aggregate_key == aggregate_key)
            rows = (await session.execute(statement)).scalars().all()
        return [str(item) for item in rows]
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_menu_tables(platform_db: None) -> None:
    """菜单元数据表逐用例清场（会话级平台库共享）。

    Args:
        platform_db: 平台库夹具（确保平台库连接串已注入）。
    """
    tables = [cast("Table", model.__table__) for model in MENU_MODELS]  # type: ignore[attr-defined]
    engine = create_async_engine(platform_url())
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables))
            for table in tables:
                await connection.execute(delete(table))
    finally:
        await engine.dispose()
