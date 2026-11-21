"""数据库访问门钩子用例（Kiwi 2533）：生产直通与测试注入。

口径见 `bms_core.db.gate` 模块文档。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

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

    bind: object = None
    """绑定引擎占位（显式 `bind` 透传用例会改写）。"""

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

    async def commit(self) -> None:
        """提交（写门按事务释放的触发点）。"""

    async def rollback(self) -> None:
        """回滚（写门按事务释放的触发点）。"""

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
    """写会话：只有协程数据库方法才取门；同步方法不触发。"""
    entered: ConcurrentStableList[str] = ConcurrentStableList()
    session = _FakeSession()
    lazy = LazyGatedSession(lambda: _recording_scope(entered), session)

    assert lazy.add(object()) == "added:object"
    assert list(entered) == [], "同步方法不应取门"

    assert await lazy.execute() == "ok"  # type: ignore[misc]
    assert list(entered) == ["in", "out"]


async def test_lazy_session_close_releases_gate() -> None:
    """写会话：`aclose` 关闭底层会话并放门（写门覆盖事务）。"""
    entered: ConcurrentStableList[str] = ConcurrentStableList()
    session = _FakeSession()
    lazy = LazyGatedSession(lambda: _recording_scope(entered), session)

    await lazy.execute()  # type: ignore[misc]
    await lazy.aclose()

    assert session.closed is True
    assert list(entered) == ["in", "out"]


async def test_lazy_session_close_without_use_skips_gate() -> None:
    """写会话：没碰库就关闭，不进门、不放门。"""
    entered: ConcurrentStableList[str] = ConcurrentStableList()
    session = _FakeSession()
    lazy = LazyGatedSession(lambda: _recording_scope(entered), session)

    await lazy.aclose()

    assert session.closed is True
    assert list(entered) == []


async def test_lazy_session_gates_each_call() -> None:
    """写会话：**每次**协程调用各取放一次写门（操作级持有）。"""
    entered: ConcurrentStableList[str] = ConcurrentStableList()
    lazy = LazyGatedSession(lambda: _recording_scope(entered), _FakeSession())

    await lazy.execute()  # type: ignore[misc]
    await lazy.execute()  # type: ignore[misc]

    assert list(entered) == ["in", "out", "in", "out"]


async def test_lazy_session_repr_contains_session() -> None:
    """`repr` 带底层会话，便于诊断。"""
    lazy = LazyGatedSession(lambda: _recording_scope(ConcurrentStableList()), _FakeSession())

    assert "LazyGatedSession" in repr(lazy)


class _FakeResult:
    """结果替身：行 + 可选 rowcount（`ChunkedIteratorResult` 没有 rowcount）。"""

    rowcount: int

    def __init__(self, rows: ConcurrentStableList[Any], rowcount: int = -1) -> None:
        """初始化。

        Args:
            rows: 物化行。
            rowcount: 受影响行数。
        """
        self._rows = rows
        self.rowcount = rowcount

    def all(self) -> ConcurrentStableList[Any]:
        """全部行。"""
        return ConcurrentStableList(self._rows)

    def close(self) -> None:
        """关闭占位。"""


class _Row:
    """行替身：支持下标与 `_mapping`。"""

    def __init__(self, value: int) -> None:
        """初始化。

        Args:
            value: 单列值。
        """
        self._value = value
        self._mapping = {"value": value}

    def __getitem__(self, index: int) -> int:
        """按下标取值。"""
        assert index == 0
        return self._value


class _ReadSession:
    """读会话替身：覆盖读路径的协程方法与同步方法。"""

    def __init__(self) -> None:
        """初始化状态。"""
        self.closed = False
        self.executed = 0

    async def execute(self, *args: object, **kwargs: object) -> _FakeResult:
        """返回两行结果（第三行用于 `one` 的报错分支）。"""
        del args, kwargs
        self.executed += 1
        return _FakeResult(ConcurrentStableList((_Row(1), _Row(2))), rowcount=7)

    async def scalar(self, *args: object, **kwargs: object) -> int:
        """返回固定标量。"""
        del args, kwargs
        return 42

    async def get(self, *args: object, **kwargs: object) -> str:
        """返回固定对象。"""
        del args, kwargs
        return "entity"

    async def flush(self) -> None:
        """写库协程（读会话不该被调用，仅为分支覆盖）。"""

    def add(self, item: object) -> str:
        """同步方法透传。"""
        return f"added:{type(item).__name__}"

    async def scalars(self, *args: object, **kwargs: object) -> _FakeResult:
        """返回两行结果（供读代理的 scalars 分支覆盖）。"""
        return await self.execute(*args, **kwargs)

    async def stream(self, *args: object, **kwargs: object) -> _FakeResult:
        """流式结果（读代理应明确拒绝，避免门泄漏）。"""
        return await self.execute(*args, **kwargs)

    async def aclose(self) -> None:
        """关闭会话。"""
        self.closed = True


def _gated_reads(session: _ReadSession, entered: ConcurrentStableList[str]) -> gate_module.ReadOperationGatedSession:
    """构造读按操作会话（每次读操作：新门 + 新短会话）。"""

    @asynccontextmanager
    async def _session_ctx() -> AsyncGenerator[_ReadSession]:
        yield session

    return gate_module.ReadOperationGatedSession(lambda: _recording_scope(entered), _session_ctx)


async def test_read_operation_takes_gate_per_call() -> None:
    """读会话：每次 execute / get / scalar 各取放一次门（不跨调用持有）。"""
    entered: ConcurrentStableList[str] = ConcurrentStableList()
    session = _ReadSession()
    reads = _gated_reads(session, entered)

    first = await reads.execute("stmt")
    second = await reads.execute("stmt")
    assert list(entered) == ["in", "out", "in", "out"]
    assert [row[0] for row in first.all()] == [1, 2]
    assert first.rowcount == 7
    assert [row[0] for row in second.fetchall()] == [1, 2]

    entered.clear()
    assert await reads.get("entity", 1) == "entity"
    assert await reads.scalar("stmt") == 42
    assert list(entered) == ["in", "out", "in", "out"]
    before = len(entered)
    with pytest.raises(AttributeError, match="读会话不提供 add"):
        reads.add  # noqa: B018  # 触发 __getattr__ 的拒绝分支
    assert len(entered) == before, "非读路径方法不得取门"
    await reads.aclose()
    assert session.closed is False, "读会话按次开关，没有长会话需要关闭"


def test_read_operation_exposes_bind_for_engine_assertions() -> None:
    """读会话透出绑定引擎（`bind` / `get_bind`）：路由用例按引擎身份断言。"""
    engine = object()
    reads = gate_module.ReadOperationGatedSession(
        lambda: _recording_scope(ConcurrentStableList()),
        lambda: _null_session(),  # type: ignore[arg-type]
        bind=engine,
    )
    assert reads.bind is engine
    assert reads.get_bind() is engine
    assert (
        gate_module.ReadOperationGatedSession(
            lambda: _recording_scope(ConcurrentStableList()),
            lambda: _null_session(),  # type: ignore[arg-type]
        ).bind
        is None
    )


@asynccontextmanager
async def _null_session() -> AsyncGenerator[_ReadSession]:
    """空短会话上下文（只为构造参数，不做读）。"""
    yield _ReadSession()


def test_lazy_gated_session_exposes_explicit_bind() -> None:
    """写会话显式给出原始引擎时 `bind` 返回它；未给出时透传底层会话。"""
    fake = _FakeSession()
    fake.bind = "inner"
    lazy = LazyGatedSession(lambda: _recording_scope(ConcurrentStableList()), fake)
    assert lazy.bind == "inner"
    assert lazy.get_bind() == "inner"
    explicit = LazyGatedSession(lambda: _recording_scope(ConcurrentStableList()), fake, bind="original")
    assert explicit.bind == "original"


async def test_read_operation_scalars_and_stream_rejected() -> None:
    """读会话：`scalars` 返回标量代理；流式结果明确拒绝（避免门泄漏）。"""
    entered: ConcurrentStableList[str] = ConcurrentStableList()
    reads = _gated_reads(_ReadSession(), entered)

    scalars = await reads.scalars("stmt")
    assert list(scalars.all()) == [1, 2]
    with pytest.raises(NotImplementedError, match="流式结果"):
        await reads.stream("stmt")
    assert "ReadOperationGatedSession" in repr(reads)


def test_result_proxy_readonly_views() -> None:
    """结果代理：常用只读接口都是内存操作。"""
    rows = ConcurrentStableList((_Row(1), _Row(2)))
    proxy = gate_module.ResultProxy(rows, rowcount=3)

    assert proxy.returns_rows is True
    assert len(proxy) == 2
    assert list(proxy) == list(rows)
    assert proxy.rowcount == 3
    assert proxy.first() is rows[0]
    assert proxy.scalar() == 1
    assert list(proxy.scalars().all()) == [1, 2]
    assert proxy.scalars().first() == 1
    assert list(proxy.mappings().all()) == [{"value": 1}, {"value": 2}]
    assert proxy.mappings().first() == {"value": 1}
    assert list(proxy.mappings()) == [{"value": 1}, {"value": 2}]
    assert list(proxy.keys()) == ["value"]
    assert proxy.unique() is proxy
    proxy.close()


def test_result_proxy_one_branches() -> None:
    """单行 / 空行的 one / one_or_none / scalar_one 分支。"""
    single = gate_module.ResultProxy(ConcurrentStableList((_Row(5),)))
    assert single.one() is single.first()
    assert single.scalar_one() == 5
    assert single.scalar_one_or_none() == 5
    empty = gate_module.ResultProxy(ConcurrentStableList())
    assert empty.first() is None
    assert empty.scalar() is None
    assert empty.scalar_one_or_none() is None
    assert list(empty.keys()) == []
    with pytest.raises(ValueError, match="恰好一条"):
        empty.one()
    with pytest.raises(ValueError, match="最多一条"):
        gate_module.ResultProxy(ConcurrentStableList((_Row(1), _Row(2)))).one_or_none()
    with pytest.raises(ValueError, match="恰好一条"):
        gate_module.ResultProxy(ConcurrentStableList((_Row(1), _Row(2)))).scalar_one()
    with pytest.raises(ValueError, match="最多一条"):
        gate_module.ResultProxy(ConcurrentStableList((_Row(1), _Row(2)))).scalar_one_or_none()


def test_scalar_proxy_branches() -> None:
    """标量代理：空 / 单行 / 多行的取值与报错分支。"""
    single = gate_module.ResultProxy(ConcurrentStableList((_Row(5),))).scalars()
    assert single.one() == 5
    assert single.one_or_none() == 5
    assert single.unique() is single
    assert len(single) == 1
    empty = gate_module.ResultProxy(ConcurrentStableList()).scalars()
    assert empty.first() is None
    assert empty.one_or_none() is None
    with pytest.raises(ValueError, match="恰好一条"):
        empty.one()
    many = gate_module.ResultProxy(ConcurrentStableList((_Row(1), _Row(2)))).scalars()
    with pytest.raises(ValueError, match="最多一条"):
        many.one_or_none()
    with pytest.raises(ValueError, match="恰好一条"):
        many.one()


async def test_read_operation_without_rowcount_reports_minus_one() -> None:
    """底层结果没有 rowcount（如 `ChunkedIteratorResult`）时按 -1 记录，不抛错。"""

    class _NoRowcount(_ReadSession):
        """去掉 rowcount 的读会话。"""

        async def execute(self, *args: object, **kwargs: object) -> _FakeResult:
            del args, kwargs
            return _FakeResult(ConcurrentStableList((_Row(9),)))

    reads = _gated_reads(_NoRowcount(), ConcurrentStableList())
    result = await reads.execute("stmt")
    assert result.rowcount == -1


async def test_lazy_session_gates_commit_and_rollback_too() -> None:
    """写会话：提交 / 回滚也是各取放一次门（同样是操作级）。"""
    entered: ConcurrentStableList[str] = ConcurrentStableList()
    session = _FakeSession()
    lazy = LazyGatedSession(lambda: _recording_scope(entered), session)

    await lazy.execute()  # type: ignore[misc]
    await lazy.commit()  # type: ignore[misc]
    await lazy.rollback()  # type: ignore[misc]

    assert list(entered) == ["in", "out", "in", "out", "in", "out"]


async def test_lazy_session_commit_failure_propagates_and_releases() -> None:
    """提交失败：异常原样抛出，写门已按操作放掉（不遗留持门）。"""

    class _FailingCommit(_FakeSession):
        """提交恒失败的会话。"""

        async def commit(self) -> None:
            raise RuntimeError("提交失败")

    entered: ConcurrentStableList[str] = ConcurrentStableList()
    session = _FailingCommit()
    lazy = LazyGatedSession(lambda: _recording_scope(entered), session)

    with pytest.raises(RuntimeError, match="提交失败"):
        await lazy.commit()  # type: ignore[misc]
    assert list(entered) == ["in", "out"]
