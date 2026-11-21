"""公告域用例共用夹具：公告表按整份目录串行，并在用例前后清掉本域数据。

为什么需要：公告是全租户共享的列表 / 统计口径（`total` 直接断言），写入已改为立即落库，
并行或叠加都会让「先造一条再断言总数」失真。公告三张表只由本目录用例写入，串行 + 清场
不会碰到他人数据。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.testing.locks import file_lock
from bms_core.testing.transaction import write_session

_PURGE_STATEMENTS = (
    "DELETE FROM sys_notice_read WHERE id IS NOT NULL",
    "DELETE FROM sys_notice_i18n WHERE id IS NOT NULL",
    "DELETE FROM sys_notice WHERE id IS NOT NULL",
)
"""清场语句（子表先删；原生 SQL 显式带 WHERE，护栏要求）。"""


@pytest.fixture(autouse=True)
def _serial_notice_state() -> Iterator[None]:
    """公告表整份目录串行（清理与用例必须原子）。

    Yields:
        None: 用例运行期。
    """
    with file_lock("notification-notice-state", timeout=180.0):
        yield


@pytest.fixture(autouse=True)
async def _clean_notice_tables(_serial_notice_state: None, shared_tenant_engine: AsyncEngine) -> AsyncIterator[None]:
    """用例前后清空公告三表（子表先删；写入立即落库，必须自己收尾）。

    Args:
        _serial_notice_state: 保证清场与用例在同一个串行区间。
        shared_tenant_engine: 共享租户库引擎。

    Yields:
        None: 用例运行期。
    """

    async def _purge() -> None:
        """删除公告与附表 / 回执的全部行。"""
        async with write_session(shared_tenant_engine) as session:
            for statement in _PURGE_STATEMENTS:
                await session.execute(text(statement))

    await _purge()
    yield
    await _purge()
