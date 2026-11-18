"""用例级写门声明（13_08：整条用例持锁已取消）。

历史问题：`platform_db_write_whole` / `tenant_db_write_whole` / `serial_db_write` 把「准备 → 调用 →
清理」整条用例圈进独占锁，实测单条 20~45s 全在临界区，24 个 worker 只能排一条队——第 5 批
477.6s 的主因。13_08 起写门由会话入口（`_open_session` / `session_scope`）按「一次写操作」取放，
整条用例持锁的三个夹具全部删除。

保留的两个夹具只服务**直连共享引擎**的用例（不经会话入口）：把用例级读门升级为写门，
用例结束自动降回读门。新用例应优先经会话入口，不应依赖这两个夹具。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from bms_core.testing.gates import PLATFORM_GATE, TENANT_GATE, upgrade_to_write


@pytest.fixture
async def platform_db_write() -> AsyncIterator[None]:
    """声明本用例要写**平台库**（仅直连 `shared_platform_engine` 的用例需要）。

    Yields:
        None: 写门区间（退出后恢复用例级读门）。
    """
    async with upgrade_to_write(PLATFORM_GATE):
        yield


@pytest.fixture
async def tenant_db_write() -> AsyncIterator[None]:
    """声明本用例要写**租户库**（仅直连 `shared_tenant_engine` 的用例需要）。

    Yields:
        None: 写门区间（退出后恢复用例级读门）。
    """
    async with upgrade_to_write(TENANT_GATE):
        yield
