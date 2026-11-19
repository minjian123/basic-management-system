"""数据库访问门钩子用例（Kiwi 2533）：生产直通与测试注入。

口径见 `bms_core.db.gate` 模块文档。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db import gate as gate_module

pytestmark = pytest.mark.kiwi_id(2533)

_CALLS: ConcurrentStableList[tuple[str, bool]] = ConcurrentStableList()
"""钩子调用记录（每个用例开始清空）。"""


@asynccontextmanager
async def _recording_hook(db_key: str, read_only: bool) -> AsyncGenerator[None]:
    """记录调用参数后放行的钩子。

    Args:
        db_key: 数据源键。
        read_only: 是否只读。

    Yields:
        None: 区间。
    """
    _CALLS.append((db_key, read_only))
    yield


@pytest.fixture(autouse=True)
def _reset_hook(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """每个用例期间清空钩子与记录，用例结束后**恢复会话钩子**。

    直接 `set_gate_hook(None)` 会在本文件跑完后把全局钩子留成空，后续文件的
    `db_access_gate` 变成直通（门不生效）——用 monkeypatch 记录并在退出时还原。

    Args:
        monkeypatch: pytest 补丁夹具（负责还原）。

    Yields:
        None: 用例运行期。
    """
    monkeypatch.setattr(gate_module, "_hook", None)
    _CALLS.clear()
    yield


async def test_default_hook_is_passthrough() -> None:
    """未注入钩子时直接放行，且 `current_gate_hook` 为 None。"""
    async with gate_module.db_access_gate("platform", read_only=True):
        pass

    assert gate_module.current_gate_hook() is None
    assert list(_CALLS) == []


async def test_injected_hook_wraps_access() -> None:
    """注入钩子后按其上下文进入，参数原样透传。"""
    gate_module.set_gate_hook(_recording_hook)

    async with gate_module.db_access_gate("tenant_demo", read_only=False):
        assert list(_CALLS) == [("tenant_demo", False)]

    assert gate_module.current_gate_hook() is _recording_hook
