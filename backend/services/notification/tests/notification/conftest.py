"""通知域用例共用夹具：按用例派生收件人主键，并清理本用例的站内信。"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.db.gate import GATE_CRITICAL_WAIT
from bms_core.testing.namespace import Namespace
from bms_core.testing.sql_ids import sqlite_id
from bms_core.testing.transaction import write_session

_OFFSETS = range(4)
"""本用例可用的收件人槽位（`uid` 起连续 4 个，覆盖「本人 + 他人」场景）。"""


@pytest.fixture
def uid(ns: Namespace) -> int:
    """本用例的收件人主键基值（按 nodeid 派生，查询与清理都限定这几个槽位）。"""
    return int(ns.prefix[2:], 16) % 900_000 + 10_000


@pytest.fixture(autouse=True)
async def _clean_notification_rows(shared_tenant_engine: AsyncEngine, uid: int) -> AsyncIterator[None]:
    """用例前后只清本用例收件人的站内信（写入立即落库，不再回滚）。

    Args:
        shared_tenant_engine: 共享租户库引擎。
        uid: 本用例收件人基值。

    Yields:
        None: 用例运行期。
    """
    users = [sqlite_id(uid + offset) for offset in _OFFSETS]
    placeholders = ", ".join(f":u{index}" for index in range(len(users)))
    statement = text(f"DELETE FROM sys_notification WHERE user_id IN ({placeholders})")
    params = {f"u{index}": value for index, value in enumerate(users)}

    async def _purge() -> None:
        """按收件人删除本用例的站内信。"""
        async with write_session(shared_tenant_engine, wait=GATE_CRITICAL_WAIT) as session:
            await session.execute(statement, params)

    await _purge()
    yield
    await _purge()
