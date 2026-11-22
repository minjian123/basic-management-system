"""公告域用例共用夹具：只清本用例命名空间造出的公告行，不做整表清场。

公告是全租户共享的列表 / 统计口径，共享库里任何用例都可能写入；因此本目录的用例统一
把标题写成 `{ns.prefix}-…`，查询与断言只认这个前缀（管理列表按 `keyword=ns.prefix`
过滤，公开列表在返回行里按前缀取自己的行），清理也只删自己前缀的行。不假设空表、
不假设「本目录是唯一使用者」，因此也不需要整份目录串行。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.db.gate import GATE_CRITICAL_WAIT
from bms_core.testing.namespace import Namespace
from bms_core.testing.transaction import write_session

_PURGE_STATEMENTS = (
    "DELETE FROM sys_notice_read WHERE notice_id IN (SELECT id FROM sys_notice WHERE title LIKE :pattern)",
    "DELETE FROM sys_notice_i18n WHERE notice_id IN (SELECT id FROM sys_notice WHERE title LIKE :pattern)",
    "DELETE FROM sys_notice WHERE title LIKE :pattern",
)
"""按标题前缀清理本用例造出的公告（子表先删）。"""


@pytest.fixture(autouse=True)
async def _clean_own_notices(ns: Namespace, shared_tenant_engine: AsyncEngine) -> AsyncIterator[None]:
    """用例前后只删本用例前缀的公告（写入立即落库，必须自己收尾）。

    Args:
        ns: 用例命名空间（标题前缀）。
        shared_tenant_engine: 共享租户库引擎。

    Yields:
        None: 用例运行期。
    """
    params = {"pattern": ns.like()}

    async def _purge() -> None:
        """删除本用例前缀的公告与附表 / 回执行。"""
        async with write_session(shared_tenant_engine, wait=GATE_CRITICAL_WAIT) as session:
            for statement in _PURGE_STATEMENTS:
                await session.execute(text(statement), params)

    await _purge()
    yield
    await _purge()
