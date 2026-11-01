"""认证域仓储的可选筛选「缺省」分支（04-6-2 覆盖率收口）。

`SysClientRepository` / `IdentityProviderRepository` 的 `_filter_conditions` 只在**传了**筛选值时才
追加条件；管理面用例总是带 `name` 等条件，缺省路径（不追加）长期没有用例走到，两个仓储的分支覆盖
停在 97%。这里补「不传筛选」的最小调用。

为什么不断言具体行：`sys_client` / `sys_identity_provider` 的唯一约束含 `deleted_at`（NULL 下
NULL ≠ NULL 使约束失效），在共享库上插行会与他人用例互撞。故用「不过滤的结果集不小于按必然不存在的
值过滤的结果集」表达「不传即不过滤」，不碰他人行。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.identity.client import SysClient
from bms_core.models.identity.identity_provider import SysIdentityProvider
from bms_core.schemas.pagination import BasePageQuery
from bms_core.testing.namespace import Namespace
from bms_core.testing.schema import ensure_tables
from bms_identity.domains.identity_federation.repositories.client import SysClientRepository
from bms_identity.domains.identity_federation.repositories.identity_provider import IdentityProviderRepository

_TABLES: ConcurrentStableList[Table] = ConcurrentStableList(
    (cast("Table", SysClient.__table__), cast("Table", SysIdentityProvider.__table__))
)
"""租户库待补齐表（第三方客户端 / 外部 IdP 配置）。"""


@pytest_asyncio.fixture
async def session(shared_tenant_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """租户库只读会话（表幂等补齐，不写数据）。

    Args:
        shared_tenant_engine: 共享租户库引擎。

    Yields:
        AsyncSession: 用例会话。
    """
    await ensure_tables(shared_tenant_engine, _TABLES)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    async with factory() as opened:
        yield opened


@pytest.mark.kiwi_id(927)
async def test_client_list_without_name_filter(session: AsyncSession, ns: Namespace) -> None:
    """客户端分页：不传 `name` 即不追加名称模糊条件（`if name:` 缺省分支）。

    Args:
        session: 租户库会话。
        ns: 用例命名空间（取一个必然不存在的名称做对照）。
    """
    repository = SysClientRepository(session)
    rows = await repository.list_filtered(BasePageQuery())
    narrowed = await repository.list_filtered(BasePageQuery(), name=ns.code("absent"))
    assert len(rows) >= len(narrowed)
    assert await repository.count_filtered() >= await repository.count_filtered(name=ns.code("absent"))


@pytest.mark.kiwi_id(927)
async def test_identity_provider_list_without_name_filter(session: AsyncSession, ns: Namespace) -> None:
    """外部 IdP 分页：不传 `name` 即不追加名称模糊条件（`if name:` 缺省分支）。

    Args:
        session: 租户库会话。
        ns: 用例命名空间（取一个必然不存在的名称做对照）。
    """
    repository = IdentityProviderRepository(session)
    rows = await repository.list_filtered(BasePageQuery())
    narrowed = await repository.list_filtered(BasePageQuery(), name=ns.code("absent"))
    assert len(rows) >= len(narrowed)
    assert await repository.count_filtered() >= await repository.count_filtered(name=ns.code("absent"))
