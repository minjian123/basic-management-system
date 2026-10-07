"""产品档案仓储测试（Kiwi 2249）：只读查询、状态筛选、软删过滤与只读护栏。"""

import ast
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_platform.models.catalog import SysProduct
from bms_platform.repositories import product_repository
from bms_platform.repositories.product_repository import ProductRepository

_WRITE_VERBS = frozenset({"create", "update", "delete", "save", "flush", "commit", "upsert", "insert"})
"""仓储自有方法名中的写动词（只读护栏：命中即失败）。"""

_SESSION_WRITES = frozenset({"add", "add_all", "flush", "commit", "delete"})
"""会话写调用（只读护栏：`self._session` 上出现即失败；读取经 `execute` 属只读语义）。"""


@pytest.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    """SQLite 真库会话：仅建 `sys_product` 表。"""
    engine: AsyncEngine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'product_repo.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(cast("Table", SysProduct.__table__).create)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed(session: AsyncSession) -> None:
    """写入产品档案三行（与 `PRODUCT_CATALOG` 同构）。"""
    session.add_all(
        [
            SysProduct(product_key="biz", name="企业运营管理", status="enabled"),
            SysProduct(product_key="cw", name="创作系统", status="enabled"),
            SysProduct(product_key="mdm", name="主数据管理", status="planned"),
        ]
    )
    await session.commit()


@pytest.mark.kiwi_id(2249)
async def test_list_products_filters(session: AsyncSession) -> None:
    """按状态过滤（默认全部、`id` 升序；无匹配返回空）。"""
    await _seed(session)
    repository = ProductRepository(session)
    assert [product.product_key for product in await repository.list_products()] == ["biz", "cw", "mdm"]
    assert [product.product_key for product in await repository.list_products(status="planned")] == ["mdm"]
    assert await repository.list_products(status="retired") == []


@pytest.mark.kiwi_id(2249)
async def test_get_by_key_and_soft_delete(session: AsyncSession) -> None:
    """单条命中 / 缺失；软删后不可见（列表同步收敛）。"""
    await _seed(session)
    repository = ProductRepository(session)
    product = await repository.get_by_key("mdm")
    assert product is not None
    assert product.status == "planned"
    assert product.frontend_package_source is None
    assert await repository.get_by_key("missing") is None

    product.soft_delete()
    await session.commit()
    assert await repository.get_by_key("mdm") is None
    assert {item.product_key for item in await repository.list_products()} == {"biz", "cw"}


@pytest.mark.kiwi_id(2249)
def test_repository_read_only_surface() -> None:
    """只读护栏：仓储自有方法无写动词、无会话写调用，且只提供读方法（注册运行时只读边界）。"""
    source = Path(product_repository.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    methods = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)}
    assert {"list_products", "get_by_key"} <= methods
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
