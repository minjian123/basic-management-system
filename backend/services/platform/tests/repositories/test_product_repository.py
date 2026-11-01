"""产品档案仓储测试（Kiwi 2249 / 2250）：只读查询、状态筛选、分页、软删过滤与只读护栏。

单库叠加口径（04-6-2）：库用共享平台库、会话走 `rollback_session`（写入整体回滚），
产品键带命名空间前缀，断言只覆盖本用例自造的行（`biz/cw/mdm` 是平台种子行，不能再被独占断言）。
"""

import ast
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.platform.catalog import SysProduct
from bms_core.schemas.pagination import BasePageQuery
from bms_core.testing.namespace import Namespace
from bms_core.testing.transaction import rollback_session
from bms_platform.domains.platform_registry.repositories import product_repository
from bms_platform.domains.platform_registry.repositories.product_repository import ProductRepository

_WRITE_VERBS = frozenset({"create", "update", "delete", "save", "flush", "commit", "upsert", "insert"})
"""仓储自有方法名中的写动词（只读护栏：命中即失败）。"""

_SESSION_WRITES = frozenset({"add", "add_all", "flush", "commit", "delete"})
"""会话写调用（只读护栏：`self._session` 上出现即失败；读取经 `execute` 属只读语义）。"""


@pytest.fixture
async def session(shared_platform_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """共享平台库上的回滚会话（`sys_product` 表幂等补齐）。"""
    async with shared_platform_engine.begin() as connection:
        await connection.run_sync(lambda conn: cast("Table", SysProduct.__table__).create(conn, checkfirst=True))
    async with rollback_session(shared_platform_engine) as session:
        yield session


async def _seed(session: AsyncSession, ns: Namespace) -> ConcurrentStableList[str]:
    """写入三行本用例专属产品档案（键带命名空间前缀）。

    Args:
        session: 回滚会话。
        ns: 用例命名空间。

    Returns:
        ConcurrentStableList[str]: 三行产品键（顺序：enabled、enabled、planned）。
    """
    keys: ConcurrentStableList[str] = ConcurrentStableList([ns.code("biz"), ns.code("cw"), ns.code("mdm")])
    session.add_all(
        [
            SysProduct(product_key=keys[0], name="企业运营管理", status="enabled"),
            SysProduct(product_key=keys[1], name="创作系统", status="enabled"),
            SysProduct(product_key=keys[2], name="主数据管理", status="planned"),
        ]
    )
    await session.commit()
    return keys


@pytest.mark.kiwi_id(2249)
async def test_list_products_filters(session: AsyncSession, ns: Namespace) -> None:
    """按状态过滤（默认全部、`id` 升序；无匹配返回空）。"""
    keys = await _seed(session, ns)
    repository = ProductRepository(session)

    listed = [product.product_key for product in await repository.list_products()]
    assert [key for key in listed if key in keys] == keys

    planned = [product.product_key for product in await repository.list_products(status="planned")]
    assert [key for key in planned if key in keys] == [keys[2]]

    retired = [product.product_key for product in await repository.list_products(status="retired")]
    assert [key for key in retired if key in keys] == []


@pytest.mark.kiwi_id(2249)
async def test_get_by_key_and_soft_delete(session: AsyncSession, ns: Namespace) -> None:
    """单条命中 / 缺失；软删后不可见（列表同步收敛）。"""
    keys = await _seed(session, ns)
    repository = ProductRepository(session)
    product = await repository.get_by_key(keys[2])
    assert product is not None
    assert product.status == "planned"
    assert product.frontend_package_source is None
    assert await repository.get_by_key(ns.code("missing")) is None

    product.soft_delete()
    await session.commit()
    assert await repository.get_by_key(keys[2]) is None
    remaining = [item.product_key for item in await repository.list_products()]
    assert [key for key in remaining if key in keys] == [keys[0], keys[1]]


@pytest.mark.kiwi_id(2250)
async def test_page_products_filters_and_total(session: AsyncSession, ns: Namespace) -> None:
    """分页查询：筛选 + 当前页 + 筛选后总数；排序白名单仅 `id`（非法字段忽略、命中排序生效）。"""
    keys = await _seed(session, ns)
    repository = ProductRepository(session)

    ordered, total = await repository.page_products(BasePageQuery(page=1, size=200))
    assert total >= 3
    assert [row.product_key for row in ordered if row.product_key in keys] == keys

    planned, _ = await repository.page_products(BasePageQuery(page=1, size=200), status="planned")
    planned_keys = [row.product_key for row in planned]
    assert [key for key in planned_keys if key in keys] == [keys[2]]

    ignored, _ = await repository.page_products(BasePageQuery(page=1, size=200, order_by="product_key"))
    ignored_keys = [row.product_key for row in ignored if row.product_key in keys]
    assert ignored_keys == keys

    descending, _ = await repository.page_products(
        BasePageQuery(page=1, size=200, order_by="id", order=ConcurrentStableList(["desc"]))
    )
    descending_keys = [row.product_key for row in descending if row.product_key in keys]
    assert descending_keys == list(reversed(keys))

    beyond, _ = await repository.page_products(BasePageQuery(page=50, size=200))
    assert [row.product_key for row in beyond if row.product_key in keys] == []


@pytest.mark.kiwi_id(2249)
def test_repository_read_only_surface() -> None:
    """只读护栏：仓储自有方法无写动词、无会话写调用，且只提供读方法（注册运行时只读边界）。"""
    source = Path(product_repository.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    methods = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)}
    assert {"list_products", "page_products", "get_by_key"} <= methods
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
