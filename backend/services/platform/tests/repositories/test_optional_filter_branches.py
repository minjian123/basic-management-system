"""仓储可选筛选参数的「缺省」分支（04-6-2 覆盖率收口）。

管理面用例总是带筛选条件，`page_filtered` / `list_filtered` 里「不传就不过滤」的反向分支长期没有
用例走到，平台 / 认证两个包的行 + 分支覆盖率因此卡在 99%。这里逐处补「缺省筛选」的最小调用。

为什么统一下放到仓储层：这几个分支只在仓储内部出现，经端点调用还要构造权限与租户上下文，
噪音大于收益；仓储层直测既命中分支也便于说明语义。

为什么不断言具体行：`sys_config` / `sys_icon` 的唯一约束含 `form_key`（全局唯一，且 SQLite 的
`deleted_at` 为 NULL 时 NULL ≠ NULL 使约束失效），在共享库上插行会与他人用例互撞。故用
「不过滤的结果集不小于按一个必然不存在的值过滤的结果集」表达「不传即不过滤」，不碰他人行。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.config.models import SysConfig
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.platform.icon import SysIcon
from bms_core.models.platform.job import SysJobType
from bms_core.models.platform.task import SysTask
from bms_core.testing.namespace import Namespace
from bms_core.testing.schema import ensure_tables
from bms_platform.domains.job.repositories.job import JobTypeRepository
from bms_platform.domains.permission_meta.repositories.icon import IconRepository
from bms_platform.domains.platform_config.repositories.config import ConfigRepository
from bms_platform.domains.task.repositories.task import TaskRepository

_PLATFORM_TABLES: ConcurrentStableList[Table] = ConcurrentStableList(
    (cast("Table", SysJobType.__table__), cast("Table", SysTask.__table__))
)
"""平台库待补齐表（作业类型目录 / 定时任务）。"""

_TENANT_TABLES: ConcurrentStableList[Table] = ConcurrentStableList(
    (cast("Table", SysConfig.__table__), cast("Table", SysIcon.__table__))
)
"""租户库待补齐表（系统参数 / 自定义图标）。"""


@pytest_asyncio.fixture
async def platform_session(shared_platform_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """平台库只读会话（表幂等补齐，不写数据）。

    Args:
        shared_platform_engine: 共享平台库引擎。

    Yields:
        AsyncSession: 用例会话。
    """
    await ensure_tables(shared_platform_engine, _PLATFORM_TABLES)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(shared_platform_engine, expire_on_commit=False)
    async with factory() as opened:
        yield opened


@pytest_asyncio.fixture
async def tenant_session(shared_tenant_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """租户库只读会话（表幂等补齐，不写数据）。

    Args:
        shared_tenant_engine: 共享租户库引擎。

    Yields:
        AsyncSession: 用例会话。
    """
    await ensure_tables(shared_tenant_engine, _TENANT_TABLES)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    async with factory() as opened:
        yield opened


@pytest.mark.kiwi_id(2386)
async def test_job_type_page_without_filters(platform_session: AsyncSession, ns: Namespace) -> None:
    """作业类型分页：不传 `service_key` / `status` 即不过滤。

    Args:
        platform_session: 平台库会话。
        ns: 用例命名空间（取一个必然不存在的服务键做对照）。
    """
    repository = JobTypeRepository(platform_session)
    rows, total = await repository.page_filtered(page=1, size=5)
    _, narrowed_total = await repository.page_filtered(page=1, size=5, service_key=ns.code("absent"))
    assert total >= narrowed_total
    assert [type(row) for row in rows] == [SysJobType] * len(rows)


@pytest.mark.kiwi_id(2386)
async def test_task_page_without_name(platform_session: AsyncSession, ns: Namespace) -> None:
    """定时任务分页：不传 `name` 即不按名称模糊过滤。

    Args:
        platform_session: 平台库会话。
        ns: 用例命名空间（取一个必然不存在的名称做对照）。
    """
    repository = TaskRepository(platform_session)
    rows, total = await repository.page_filtered(page=1, size=5)
    _, narrowed_total = await repository.page_filtered(page=1, size=5, name=ns.code("absent"))
    assert total >= narrowed_total
    assert [type(row) for row in rows] == [SysTask] * len(rows)


@pytest.mark.kiwi_id(2373)
async def test_config_page_without_keyword(tenant_session: AsyncSession, ns: Namespace) -> None:
    """系统参数分页：不传 `keyword` 即不追加模糊条件（其余筛选仍可独立生效）。

    Args:
        tenant_session: 租户库会话。
        ns: 用例命名空间（取一个必然不存在的关键字做对照）。
    """
    repository = ConfigRepository(tenant_session)
    _, total = await repository.page_filtered(page=1, size=5)
    _, narrowed_total = await repository.page_filtered(page=1, size=5, keyword=ns.code("absent"))
    assert total >= narrowed_total


@pytest.mark.kiwi_id(927)
async def test_icon_list_without_keyword(tenant_session: AsyncSession, ns: Namespace) -> None:
    """自定义图标列示：不传 `keyword` 即不追加模糊条件（分组 / 状态仍可独立生效）。

    Args:
        tenant_session: 租户库会话。
        ns: 用例命名空间（取一个必然不存在的关键字做对照）。
    """
    repository = IconRepository(tenant_session)
    rows = await repository.list_filtered()
    narrowed = await repository.list_filtered(keyword=ns.code("absent"))
    assert len(rows) >= len(narrowed)
    assert [type(row) for row in rows] == [SysIcon] * len(rows)
