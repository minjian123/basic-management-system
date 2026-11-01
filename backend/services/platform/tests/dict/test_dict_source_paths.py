"""平台内建字典数据源路径补齐用例（`bms_platform/sources/dict_source.py`）。

覆盖：角色数据源加载启用行（软删除 / 停用过滤）、未支持标识返回空元组。

单库叠加口径（04-6-2）：库用**共享租户库**、写入走 `rollback_session`（整体回滚不残留）；
角色码带命名空间前缀，断言只看本用例自造的行（叠加库中他人角色不能进断言集合）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.models.platform.role import SysRole
from bms_core.testing.namespace import Namespace
from bms_core.testing.transaction import rollback_session
from bms_platform.domains.platform_registry.sources.dict_source import PlatformDictDataSource
from bms_platform.wiring import role_reference

_TABLES: ConcurrentStableList[Table] = ConcurrentStableList((cast("Table", SysRole.__table__),))
"""本文件涉及的表（共享租户库幂等补齐）。"""


@dataclass(frozen=True)
class _Scenario:
    """用例场景：字典数据源 + 本用例自造的角色码。

    Attributes:
        source: 平台内建字典数据源（经共享租户库取数）。
        ns: 用例命名空间。
        enabled: 启用角色的角色码。
        label: 启用角色的名称（断言展示名）。
    """

    source: PlatformDictDataSource
    ns: Namespace
    enabled: str
    label: str


@pytest_asyncio.fixture
async def scenario(
    shared_tenant_engine: AsyncEngine, shared_tenant_db_url: str, ns: Namespace, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[_Scenario]:
    """共享租户库（`sys_role` 幂等补齐 + 回滚会话播种）+ 平台内建字典数据源。

    Args:
        shared_tenant_engine: 共享租户库引擎。
        shared_tenant_db_url: 共享租户库连接串（供引擎注册表解析）。
        ns: 用例命名空间。
        monkeypatch: 环境变量覆盖。

    Yields:
        _Scenario: 数据源与本用例角色码。
    """
    async with shared_tenant_engine.begin() as connection:
        await connection.run_sync(lambda conn: SysRole.metadata.create_all(conn, tables=list(_TABLES)))
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", shared_tenant_db_url)
    get_settings.cache_clear()

    enabled = ns.code("ops")
    label = "运维角色"
    async with rollback_session(shared_tenant_engine) as session:
        session.add_all(
            [
                SysRole(code=enabled, name=label, status="enabled"),
                SysRole(code=ns.code("off"), name="停用角色", status="disabled"),
            ]
        )
        removed = SysRole(code=ns.code("gone"), name="已删角色", status="enabled")
        removed.soft_delete()
        session.add(removed)
        await session.commit()

        registry = EngineRegistry(EngineFactory(get_settings()))
        try:
            yield _Scenario(
                source=PlatformDictDataSource(engines=registry, role_options=role_reference),
                ns=ns,
                enabled=enabled,
                label=label,
            )
        finally:
            await registry.aclose()
            get_settings.cache_clear()


async def test_platform_dict_source_loads_enabled_roles(scenario: _Scenario) -> None:
    """角色数据源：仅返回启用且未软删的行；未支持标识返回空元组。"""
    source = scenario.source
    assert source.data_source == "platform"

    items = await source.load("role", "zh-CN")
    owned = [item for item in items if item.value.startswith(scenario.ns.prefix)]
    assert [item.value for item in owned] == [scenario.enabled]
    assert owned[0].label == scenario.label
    assert owned[0].code == scenario.enabled

    assert await source.load("ghost", "zh-CN") == ()


async def test_table_source_instance_cached_per_spec(scenario: _Scenario) -> None:
    """同一规格复用同一个表源实例（按 key 缓存，避免每次取数重建）。"""
    source = scenario.source
    spec = source._specs["icon"]  # pyright: ignore[reportPrivateUsage]
    first = source._table_source(spec)  # pyright: ignore[reportPrivateUsage]
    assert source._table_source(spec) is first  # pyright: ignore[reportPrivateUsage]
    other = source._table_source(source._specs["task"])  # pyright: ignore[reportPrivateUsage]
    assert other is not first
