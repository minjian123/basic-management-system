"""服务目录仓储测试（Kiwi 2162 / 2163 / 2164）：只读查询、分页、软删过滤与只读护栏。"""

import ast
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.models.platform import SysModule
from bms_core.repositories import module_repository
from bms_core.repositories.module_repository import ModuleRepository
from bms_core.schemas.pagination import BasePageQuery

_WRITE_VERBS = frozenset({"create", "update", "delete", "save", "flush", "commit", "upsert", "insert"})
"""仓储自有方法名中的写动词（只读护栏：命中即失败）。"""

_SESSION_WRITES = frozenset({"add", "add_all", "flush", "commit", "delete"})
"""会话写调用（只读护栏：`self._session` 上出现即失败；读取经 `execute` 属只读语义）。"""


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


@pytest.mark.kiwi_id(2164)
async def test_page_catalog_filters_and_total(session: AsyncSession) -> None:
    """分页：筛选 / 排序 / 当前页与筛选后总数。"""
    await _seed(session)
    repository = ModuleRepository(session)
    rows, total = await repository.page_catalog(BasePageQuery(page=1, size=2))
    assert [row.module_key for row in rows] == ["sys", "identity"]
    assert total == 3

    rows, total = await repository.page_catalog(BasePageQuery(page=2, size=2))
    assert [row.module_key for row in rows] == ["pur"]
    assert total == 3

    rows, total = await repository.page_catalog(BasePageQuery(page=1, size=10), group="product")
    assert [row.module_key for row in rows] == ["pur"]
    assert total == 1

    rows, total = await repository.page_catalog(BasePageQuery(page=1, size=10), status="planned")
    assert [row.module_key for row in rows] == ["pur"]
    assert total == 1

    rows, _ = await repository.page_catalog(BasePageQuery(page=1, size=10, order_by="id", order=["desc"]))
    assert [row.module_key for row in rows] == ["pur", "identity", "sys"]

    rows, _ = await repository.page_catalog(BasePageQuery(page=1, size=10, order_by="module_key", order=["asc"]))
    assert [row.module_key for row in rows] == ["sys", "identity", "pur"]


@pytest.mark.kiwi_id(2164)
async def test_get_by_service_key(session: AsyncSession) -> None:
    """按服务键命中 / 缺失（产品模块行无服务键）；软删后不可见。"""
    await _seed(session)
    repository = ModuleRepository(session)
    row = await repository.get_by_service_key("platform")
    assert row is not None
    assert row.module_key == "sys"
    assert await repository.get_by_service_key("missing") is None
    assert await repository.get_by_service_key("pur") is None

    assert row is not None
    row.soft_delete()
    await session.commit()
    assert await repository.get_by_service_key("platform") is None


@pytest.mark.kiwi_id(2163)
def test_repository_read_only_surface() -> None:
    """只读护栏：仓储自有方法无写动词、无会话写调用，且只提供读方法（注册运行时只读边界）。"""
    source = Path(module_repository.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    methods = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)}
    assert {"list_catalog", "get_by_key", "page_catalog", "get_by_service_key"} <= methods
    assert not {name for name in methods if name.lstrip("_") in _WRITE_VERBS}
    session_writes = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "_session"
        and node.func.attr in _SESSION_WRITES
    ]
    assert session_writes == []
