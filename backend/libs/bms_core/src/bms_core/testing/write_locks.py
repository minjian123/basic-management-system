"""用例级写门声明（13_08：整条用例持锁已取消）。

历史问题：`platform_db_write_whole` / `tenant_db_write_whole` / `serial_db_write` 把「准备 → 调用 →
清理」整条用例圈进独占锁，实测单条 20~45s 全在临界区，24 个 worker 只能排一条队——第 5 批
477.6s 的主因。13_08 起写门由会话入口（`_open_session` / `session_scope`）按「一次写操作」取放，
整条用例持锁的三个夹具全部删除。

保留的两个夹具只服务**直连共享引擎**的用例（不经会话入口）：直连引擎拿不到会话边界，用例又要
整段独占（如共享库上的「先查后插」全局播种），由用例**显式**取写门声明。它们不再「升级」——
`shared_*_engine` 已不取夹具级读门（整条用例持读门会让写者等到所有并发读用例收尾），故这里
直接取写门；与经会话入口的写在同一条队列上排队。新用例应优先经会话入口，不应依赖这两个夹具。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from bms_core.testing.gates import PLATFORM_GATE, TENANT_GATE, write_gate


@pytest.fixture
async def platform_db_write() -> AsyncIterator[None]:
    """声明本用例要写**平台库**（仅直连 `shared_platform_engine` 的用例需要）。

    Yields:
        None: 写门区间。
    """
    async with write_gate(PLATFORM_GATE):
        yield


@pytest.fixture
async def tenant_db_write() -> AsyncIterator[None]:
    """声明本用例要写**租户库**（仅直连 `shared_tenant_engine` 的用例需要）。

    Yields:
        None: 写门区间。
    """
    async with write_gate(TENANT_GATE):
        yield
