"""平台内建字典数据源路径补齐用例（`bms_platform/sources/dict_source.py`）。

覆盖：角色数据源加载启用行（软删除 / 停用过滤）、未支持标识返回空元组。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.config import get_settings
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.models.platform.role import SysRole
from bms_platform.sources.dict_source import PlatformDictDataSource


@pytest_asyncio.fixture
async def dict_source(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[PlatformDictDataSource]:
    """临时租户库（`sys_role`）+ 平台内建字典数据源。

    Args:
        tmp_path_factory: 临时目录工厂。
        monkeypatch: 环境变量覆盖。

    Yields:
        PlatformDictDataSource: 平台内建数据源（角色）。
    """
    url = f"sqlite+aiosqlite:///{tmp_path_factory.mktemp('dict_source') / 'tenant.db'}"
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", url)
    get_settings.cache_clear()

    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda conn: SysRole.metadata.create_all(conn, tables=[cast("Table", SysRole.__table__)])
        )
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all(
            [
                SysRole(code="ops", name="运维角色", status="enabled"),
                SysRole(code="off", name="停用角色", status="disabled"),
            ]
        )
        removed = SysRole(code="gone", name="已删角色", status="enabled")
        removed.soft_delete()
        session.add(removed)
        await session.commit()
    await engine.dispose()

    registry = EngineRegistry(EngineFactory(get_settings()))
    try:
        yield PlatformDictDataSource(engines=registry)
    finally:
        await registry.aclose()
        get_settings.cache_clear()


async def test_platform_dict_source_loads_enabled_roles(dict_source: PlatformDictDataSource) -> None:
    """角色数据源：仅返回启用且未软删的行；未支持标识返回空元组。"""
    assert dict_source.data_source == "platform"

    items = await dict_source.load("role", "zh-CN")
    assert [item.value for item in items] == ["ops"]
    assert items[0].label == "运维角色"
    assert items[0].code == "ops"

    assert await dict_source.load("ghost", "zh-CN") == ()
