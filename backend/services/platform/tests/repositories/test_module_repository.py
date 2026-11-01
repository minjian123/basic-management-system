"""服务目录仓储测试（Kiwi 2162 / 2163 / 2164）：只读查询、分页、软删过滤与只读护栏。

单库叠加口径（04-6-2）：库用共享平台库、会话走 `rollback_session`（写入整体回滚），
模块键 / 服务键 / 表前缀 / 事件域一律带命名空间前缀，断言只覆盖本用例自造的行。
"""

import ast
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.platform.catalog import SysModule
from bms_core.schemas.pagination import BasePageQuery
from bms_core.testing.namespace import Namespace
from bms_core.testing.transaction import rollback_session
from bms_platform.domains.platform_registry.repositories import module_repository
from bms_platform.domains.platform_registry.repositories.module_repository import ModuleRepository

_WRITE_VERBS = frozenset({"create", "update", "delete", "save", "flush", "commit", "upsert", "insert"})
"""仓储自有方法名中的写动词（只读护栏：命中即失败）。"""

_SESSION_WRITES = frozenset({"add", "add_all", "flush", "commit", "delete"})
"""会话写调用（只读护栏：`self._session` 上出现即失败；读取经 `execute` 属只读语义）。"""


@pytest.fixture
async def session(shared_platform_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """共享平台库上的回滚会话（`sys_module` 表幂等补齐）。"""
    async with shared_platform_engine.begin() as connection:
        await connection.run_sync(lambda conn: cast("Table", SysModule.__table__).create(conn, checkfirst=True))
    async with rollback_session(shared_platform_engine) as session:
        yield session


async def _seed(session: AsyncSession, ns: Namespace) -> ConcurrentStableList[str]:
    """写入三行本用例专属目录记录（平台服务行 / 服务行 / 产品模块）。

    Args:
        session: 回滚会话。
        ns: 用例命名空间。

    Returns:
        ConcurrentStableList[str]: 三行模块键（顺序与写入一致）。
    """
    base = ns.prefix
    keys: ConcurrentStableList[str] = ConcurrentStableList([f"{base}sys", f"{base}identity", f"{base}pur"])
    session.add_all(
        [
            SysModule(
                module_key=keys[0],
                service_key=f"{base}platform",
                name="平台地基与配置服务",
                table_prefix=f"{base}sys_",
                errcode_segment="01",
                event_domain=keys[0],
                service_group="foundation",
                status="enabled",
            ),
            SysModule(
                module_key=keys[1],
                service_key=f"{base}identity",
                name="认证与身份服务",
                table_prefix=f"{base}identity_",
                event_domain=keys[1],
                service_group="foundation",
                status="enabled",
            ),
            SysModule(
                module_key=keys[2],
                name="采购",
                table_prefix=f"{base}pur_",
                business_code=f"{base}pur",
                errcode_segment="10",
                event_domain=keys[2],
                service_group="product",
                build_batch=3,
                product_key="biz",
                status="planned",
            ),
        ]
    )
    await session.commit()
    return keys


@pytest.mark.kiwi_id(2162)
async def test_list_catalog_filters(session: AsyncSession, ns: Namespace) -> None:
    """按分组 / 状态 / 服务维度过滤。"""
    keys = await _seed(session, ns)
    repository = ModuleRepository(session)

    listed = {module.module_key for module in await repository.list_catalog()}
    assert set(keys) <= listed

    product = {module.module_key for module in await repository.list_catalog(group="product")}
    assert keys[2] in product and keys[0] not in product and keys[1] not in product

    planned = {module.module_key for module in await repository.list_catalog(status="planned")}
    assert keys[2] in planned and keys[0] not in planned

    service_only = {module.module_key for module in await repository.list_catalog(service_only=True)}
    assert {keys[0], keys[1]} <= service_only and keys[2] not in service_only


@pytest.mark.kiwi_id(2162)
async def test_get_by_key_and_soft_delete(session: AsyncSession, ns: Namespace) -> None:
    """单条命中 / 缺失；软删后不可见。"""
    keys = await _seed(session, ns)
    repository = ModuleRepository(session)
    sys_module = await repository.get_by_key(keys[0])
    assert sys_module is not None
    assert sys_module.service_key == f"{ns.prefix}platform"
    assert await repository.get_by_key(ns.code("missing")) is None

    sys_module.soft_delete()
    await session.commit()
    assert await repository.get_by_key(keys[0]) is None
    remaining = {module.module_key for module in await repository.list_catalog()}
    assert keys[0] not in remaining and {keys[1], keys[2]} <= remaining


@pytest.mark.kiwi_id(2164)
async def test_page_catalog_filters_and_total(session: AsyncSession, ns: Namespace) -> None:
    """分页：筛选 / 排序 / 当前页与筛选后总数。"""
    keys = await _seed(session, ns)
    repository = ModuleRepository(session)

    rows, total = await repository.page_catalog(BasePageQuery(page=1, size=200))
    assert total >= 3
    assert [row.module_key for row in rows if row.module_key in keys] == keys

    rows, _ = await repository.page_catalog(
        BasePageQuery(page=1, size=200, order_by="id", order=ConcurrentStableList(["desc"]))
    )
    assert [row.module_key for row in rows if row.module_key in keys] == list(reversed(keys))

    # 排序白名单只含 `id`：`module_key` 属非法字段，按缺省 `id` 升序返回
    rows, _ = await repository.page_catalog(
        BasePageQuery(page=1, size=200, order_by="module_key", order=ConcurrentStableList(["asc"]))
    )
    assert [row.module_key for row in rows if row.module_key in keys] == keys

    product_rows, _ = await repository.page_catalog(BasePageQuery(page=1, size=200), group="product")
    assert keys[2] in {row.module_key for row in product_rows}

    planned_rows, _ = await repository.page_catalog(BasePageQuery(page=1, size=200), status="planned")
    assert keys[2] in {row.module_key for row in planned_rows}

    beyond, _ = await repository.page_catalog(BasePageQuery(page=50, size=200))
    assert [row.module_key for row in beyond if row.module_key in keys] == []


@pytest.mark.kiwi_id(2164)
async def test_get_by_service_key(session: AsyncSession, ns: Namespace) -> None:
    """按服务键命中 / 缺失（产品模块行无服务键）；软删后不可见。"""
    keys = await _seed(session, ns)
    repository = ModuleRepository(session)
    row = await repository.get_by_service_key(f"{ns.prefix}platform")
    assert row is not None
    assert row.module_key == keys[0]
    assert await repository.get_by_service_key(ns.code("missing")) is None
    assert await repository.get_by_service_key(keys[2]) is None

    row.soft_delete()
    await session.commit()
    assert await repository.get_by_service_key(f"{ns.prefix}platform") is None


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
