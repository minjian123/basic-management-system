"""数据库门上下文用例（Kiwi 2533）：单例、读门 / 写门、升级顺序与关闭。

口径见 `bms_core.testing.gates` 模块文档与《测试规范》「并行与隔离」节。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import pytest

from bms_core.db import gate as gate_module
from bms_core.db.registry import PLATFORM_DB_KEY
from bms_core.testing import gates, plugin, rwlock

pytestmark = pytest.mark.kiwi_id(2533)


@pytest.fixture(autouse=True)
def _isolate_gates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """每个用例用独立门目录，并在前后清空单例。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest 补丁夹具。

    Yields:
        None: 用例运行期。
    """

    def _gate_path(name: str) -> Path:
        """替身门路径（固定到本用例的临时目录）。"""
        return tmp_path / f"db-gate-{name}.lock"

    monkeypatch.setattr(gates, "gate_path", _gate_path)
    gates.reset_gates()
    yield
    gates.reset_gates()


def test_gate_is_singleton() -> None:
    """同名复用同一门实例，不同名各自独立。"""
    assert gates.gate(gates.PLATFORM_GATE) is gates.gate(gates.PLATFORM_GATE)
    assert gates.gate(gates.PLATFORM_GATE) is not gates.gate(gates.TENANT_GATE)


async def test_read_gate_context_releases() -> None:
    """读门上下文进出后回到未持有。"""
    async with gates.read_gate(gates.PLATFORM_GATE):
        assert gates.gate(gates.PLATFORM_GATE).mode == rwlock.READ

    assert gates.gate(gates.PLATFORM_GATE).mode is None


async def test_write_gate_context_releases() -> None:
    """写门上下文进出后回到未持有。"""
    async with gates.write_gate(gates.TENANT_GATE):
        assert gates.gate(gates.TENANT_GATE).mode == rwlock.WRITE

    assert gates.gate(gates.TENANT_GATE).mode is None


async def test_write_window_takes_platform_gate() -> None:
    """写窗口按平台库键取平台写门，退出即释放（直连引擎的单次写）。"""
    async with gates.write_window(PLATFORM_DB_KEY):
        assert gates.gate(gates.PLATFORM_GATE).mode == rwlock.WRITE

    assert gates.gate(gates.PLATFORM_GATE).mode is None


async def test_write_window_takes_tenant_gate_for_other_keys() -> None:
    """非平台库键一律走租户写门。"""
    async with gates.write_window("tenant_demo"):
        assert gates.gate(gates.TENANT_GATE).mode == rwlock.WRITE

    assert gates.gate(gates.TENANT_GATE).mode is None


async def test_upgrade_restores_read_mode() -> None:
    """升级写门期间为写模式，退出后恢复原读门深度。"""
    async with gates.read_gate(gates.PLATFORM_GATE):
        async with gates.upgrade_to_write(gates.PLATFORM_GATE):
            assert gates.gate(gates.PLATFORM_GATE).mode == rwlock.WRITE
        assert gates.gate(gates.PLATFORM_GATE).mode == rwlock.READ
        assert gates.gate(gates.PLATFORM_GATE).depth == 1

    assert gates.gate(gates.PLATFORM_GATE).mode is None


async def test_upgrade_failure_restores_read_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """取写门失败时恢复读门并原样抛出异常。"""
    target = gates.gate(gates.PLATFORM_GATE)
    await target.acquire(write=False)
    original = target.acquire

    async def _maybe_fail(*, write: bool) -> None:
        """写门请求直接失败，其余走真实实现。"""
        if write:
            raise TimeoutError("boom")
        await original(write=write)

    monkeypatch.setattr(target, "acquire", _maybe_fail)
    with pytest.raises(TimeoutError, match="boom"):
        async with gates.upgrade_to_write(gates.PLATFORM_GATE):
            pass

    assert target.mode == rwlock.READ
    assert target.depth == 1
    await target.release(write=False)


def test_close_gates_drops_singletons() -> None:
    """关闭后再次取门得到新实例（旧句柄已释放）。"""
    first = gates.gate(gates.TENANT_GATE)

    gates.close_gates()
    second = gates.gate(gates.TENANT_GATE)

    assert first is not second


@asynccontextmanager
async def _noop_hook(db_key: str, read_only: bool) -> AsyncGenerator[None]:
    """空门钩子（仅用于验证撤销逻辑）。

    Args:
        db_key: 数据源键。
        read_only: 是否只读。

    Yields:
        None: 区间。
    """
    del db_key, read_only
    yield


def test_pytest_unconfigure_clears_hook() -> None:
    """会话结束钩子撤销门钩子并关闭门（覆盖率口径要求该路径被执行）。"""
    gate_module.set_gate_hook(_noop_hook)
    gates.gate(gates.PLATFORM_GATE)

    plugin.pytest_unconfigure(cast("pytest.Config", None))

    assert gate_module.current_gate_hook() is None
