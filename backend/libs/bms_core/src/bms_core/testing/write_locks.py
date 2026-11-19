"""用例级写门夹具（13_08）：**整段独占**语义，只服务跨多步的全局状态临界区。

两个夹具都是普通 pytest 夹具，`async with db_access_gate(..., read_only=False)` 包住 `yield`——**持门区间就是夹具作用域**
（含同用例其它夹具的 setup / teardown），即「整条用例持门」。它**不等于**设计决策 2 的「门作用域 =
一次写操作」，属显式豁免，判据与登记见《测试规范》「并行与隔离」节：

- 需要整段独占的只有「共享库全局状态跨多步一致」一类（当前仅平台默认键的两处套件夹具：键复位 →
  用例读写 → 键再复位，中间不能插别的 worker）；
- 回滚会话（`rollback_session`）进入时自己按引擎取写门，**不要**再声明这两个夹具（声明只把门深度 +1）；
- 直连共享引擎的单次写事务用 `bms_core.testing.gates.write_window`，临界区即写段本身；
- 新用例优先经会话入口（`session_scope` / `_open_session`），那里按「一次会话」取放门。

历史：`platform_db_write_whole` / `tenant_db_write_whole` / `serial_db_write` 已删除（整条用例持锁
使第 5 批 477.6s）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from bms_core.db.gate import db_access_gate
from bms_core.testing.gates import PLATFORM_GATE, TENANT_GATE


@pytest.fixture
async def platform_db_write() -> AsyncIterator[None]:
    """整段独占平台库写门（**整条用例**，仅跨多步的全局状态临界区可声明）。

    Yields:
        None: 写门区间。
    """
    async with db_access_gate(PLATFORM_GATE, read_only=False):
        yield


@pytest.fixture
async def tenant_db_write() -> AsyncIterator[None]:
    """整段独占租户库写门（**整条用例**，仅跨多步的全局状态临界区可声明）。

    Yields:
        None: 写门区间。
    """
    async with db_access_gate(TENANT_GATE, read_only=False):
        yield
