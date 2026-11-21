"""数据库访问门钩子用例（Kiwi 2533）：生产直通与测试注入。

口径见 `bms_core.db.gate` 模块文档。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db import gate as gate_module
from bms_core.db.gate import LazyGatedSession

pytestmark = pytest.mark.kiwi_id(2533)

_CALLS: ConcurrentStableList[tuple[str, bool]] = ConcurrentStableList()
"""钩子调用记录（每个用例开始清空）。"""


@asynccontextmanager
async def _recording_hook(db_key: str, read_only: bool, wait: float | None = None) -> AsyncGenerator[None]:
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


class _FakeSession:
    """最小会话替身：协程方法、同步方法、关闭各一个。"""

    def __init__(self) -> None:
        """初始化状态。"""
        self.calls = 0
        self.closed = False

    async def execute(self) -> str:
        """协程方法（应触发取门）。

        Returns:
            str: 固定结果。
        """
        self.calls += 1
        return "ok"

    def add(self, item: object) -> str:
        """同步方法（应原样透传，不触发取门）。

        Args:
            item: 任意对象。

        Returns:
            str: 固定结果。
        """
        return f"added:{type(item).__name__}"

    async def aclose(self) -> None:
        """关闭会话。"""
        self.closed = True


def _recording_scope(entered: ConcurrentStableList[str]) -> AbstractAsyncContextManager[None]:
    """构造记录进出的门上下文（写会话按事务持门用）。

    Args:
        entered: 记录缓冲。

    Returns:
        AbstractAsyncContextManager[None]: 异步上下文管理器。
    """

    @asynccontextmanager
    async def _scope() -> AsyncGenerator[None]:
        entered.add("in")
        try:
            yield
        finally:
            entered.add("out")

    return _scope()


async def test_lazy_session_defers_gate_until_first_db_call() -> None:
    """写会话：第一次协程调用才进门；同步方法不触发。"""
    entered: ConcurrentStableList[str] = ConcurrentStableList()
    session = _FakeSession()
    lazy = LazyGatedSession(_recording_scope(entered), session)

    assert lazy.add(object()) == "added:object"
    assert list(entered) == [], "同步方法不应取门"

    assert await lazy.execute() == "ok"  # type: ignore[misc]
    assert list(entered) == ["in"]


async def test_lazy_session_close_releases_gate() -> None:
    """写会话：`aclose` 关闭底层会话并放门（写门覆盖事务）。"""
    entered: ConcurrentStableList[str] = ConcurrentStableList()
    session = _FakeSession()
    lazy = LazyGatedSession(_recording_scope(entered), session)

    await lazy.execute()  # type: ignore[misc]
    await lazy.aclose()

    assert session.closed is True
    assert list(entered) == ["in", "out"]


async def test_lazy_session_close_without_use_skips_gate() -> None:
    """写会话：没碰库就关闭，不进门、不放门。"""
    entered: ConcurrentStableList[str] = ConcurrentStableList()
    session = _FakeSession()
    lazy = LazyGatedSession(_recording_scope(entered), session)

    await lazy.aclose()

    assert session.closed is True
    assert list(entered) == []


async def test_lazy_session_enter_is_idempotent() -> None:
    """写会话：多次协程调用只取一次门（事务级持有）。"""
    entered: ConcurrentStableList[str] = ConcurrentStableList()
    lazy = LazyGatedSession(_recording_scope(entered), _FakeSession())

    await lazy.execute()  # type: ignore[misc]
    await lazy.execute()  # type: ignore[misc]

    assert list(entered) == ["in"]


async def test_lazy_session_repr_contains_session() -> None:
    """`repr` 带底层会话，便于诊断。"""
    lazy = LazyGatedSession(_recording_scope(ConcurrentStableList()), _FakeSession())

    assert "LazyGatedSession" in repr(lazy)
