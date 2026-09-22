"""服务目录仓储测试（Kiwi 2162）：按分组 / 状态 / 服务维度只读查询与软删过滤。"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.models.platform import SysModule
from bms_core.repositories.module_repository import ModuleRepository


@pytest.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    """SQLite 真库会话：仅建 `sys_module` 表。"""
    engine: AsyncEngine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'module_repo.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(cast("Table", SysModule.__table__).create)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed(session: AsyncSession) -> None:
    """写入代表性记录：平台服务 / 服务行 / 产品模块。"""
    session.add_all(
        [
            SysModule(
                module_key="sys",
                service_key="platform",
                name="平台地基与配置服务",
                table_prefix="sys_",
                errcode_segment="01",
                event_domain="sys",
                service_group="foundation",
                status="enabled",
            ),
            SysModule(
                module_key="identity",
                service_key="identity",
                name="认证与身份服务",
                table_prefix="identity_",
                event_domain="identity",
                service_group="foundation",
                status="enabled",
            ),
            SysModule(
                module_key="pur",
                name="采购",
                table_prefix="pur_",
                business_code="pur",
                errcode_segment="10",
                event_domain="pur",
                service_group="product",
                build_batch=3,
                product_key="biz",
                status="planned",
            ),
        ]
    )
    await session.commit()


@pytest.mark.kiwi_id(2162)
async def test_list_catalog_filters(session: AsyncSession) -> None:
    """按分组 / 状态 / 服务维度过滤。"""
    await _seed(session)
    repository = ModuleRepository(session)
    assert {module.module_key for module in await repository.list_catalog()} == {"sys", "identity", "pur"}
    assert [module.module_key for module in await repository.list_catalog(group="product")] == ["pur"]
    assert [module.module_key for module in await repository.list_catalog(status="planned")] == ["pur"]
    assert {module.module_key for module in await repository.list_catalog(service_only=True)} == {"sys", "identity"}


@pytest.mark.kiwi_id(2162)
async def test_get_by_key_and_soft_delete(session: AsyncSession) -> None:
    """单条命中 / 缺失；软删后不可见。"""
    await _seed(session)
    repository = ModuleRepository(session)
    sys_module = await repository.get_by_key("sys")
    assert sys_module is not None
    assert sys_module.service_key == "platform"
    assert await repository.get_by_key("missing") is None
    assert sys_module is not None
    sys_module.soft_delete()
    await session.commit()
    assert await repository.get_by_key("sys") is None
    assert {module.module_key for module in await repository.list_catalog()} == {"identity", "pur"}
