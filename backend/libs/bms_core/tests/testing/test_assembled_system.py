"""全系统装配组件用例（13_10）：装配一次 / 失败回滚 / 取用 / 每例复位 / 进程单例。

用两个假应用验证容器契约；真实服务的装配验证由 3 文件探针承担。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable, Iterator
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict, ConcurrentStableList
from bms_core.testing.system import (
    AssembledSystem,
    get_assembled_system,
    reset_assembled_system,
    set_assembled_system,
)

pytestmark = pytest.mark.kiwi_id(2556)


def _factory(log: ConcurrentStableList[str], key: str, *, fail_on_enter: bool = False) -> Callable[[], FastAPI]:
    """造一个带 lifespan 的假应用工厂。

    Args:
        log: lifespan 事件记录（`enter:x` / `exit:x`）。
        key: 服务键。
        fail_on_enter: 进入 lifespan 时是否抛错（验证回滚）。

    Returns:
        Callable[[], FastAPI]: 零参工厂。
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        del app
        log.add(f"enter:{key}")
        if fail_on_enter:
            raise RuntimeError(f"assembly failed: {key}")
        yield
        log.add(f"exit:{key}")

    app = FastAPI(lifespan=lifespan)

    @app.get("/ping", response_model=None)
    async def ping() -> ConcurrentStableDict[str, str]:
        return ConcurrentStableDict({"service": key})

    return lambda: app


@pytest.fixture(autouse=True)
def _clean_singleton() -> Iterator[None]:
    """每个用例前后清空进程单例，避免相互污染。"""
    reset_assembled_system()
    yield
    reset_assembled_system()


async def test_assemble_once_and_serve() -> None:
    """装配只发生一次；客户端按服务键取用；关闭按逆序退出 lifespan。"""
    log: ConcurrentStableList[str] = ConcurrentStableList()
    system = AssembledSystem(ConcurrentStableDict({"a": _factory(log, "a"), "b": _factory(log, "b")}))

    await system.assemble()
    assert list(log) == ["enter:a", "enter:b"]

    with pytest.raises(RuntimeError, match="只允许装配一次"):
        await system.assemble()

    async with system.client("a") as client:
        assert (await client.get("/ping")).json() == {"service": "a"}
    async with system.client("b", headers=ConcurrentStableFrozenDict({"X-Test": "1"})) as client:
        assert client.headers["X-Test"] == "1"
        assert (await client.get("/ping")).json() == {"service": "b"}

    await system.aclose()
    assert list(log) == ["enter:a", "enter:b", "exit:b", "exit:a"]
    assert list(system.apps) == []


async def test_assemble_failure_rolls_back() -> None:
    """任一服务装配失败：已进入的 lifespan 全部退出，容器保持未装配。"""
    log: ConcurrentStableList[str] = ConcurrentStableList()
    system = AssembledSystem(
        ConcurrentStableDict({"ok": _factory(log, "ok"), "bad": _factory(log, "bad", fail_on_enter=True)})
    )

    with pytest.raises(RuntimeError, match="assembly failed: bad"):
        await system.assemble()

    assert list(log) == ["enter:ok", "enter:bad", "exit:ok"]
    assert list(system.apps) == []
    await system.aclose()


def test_app_lookup_errors() -> None:
    """取未装配服务 / 空系统时给出可用清单，不静默返回空。"""
    system = AssembledSystem(ConcurrentStableDict({"a": _factory(ConcurrentStableList(), "a")}))
    with pytest.raises(RuntimeError, match="可用：无"):
        system.app("a")

    system.apps["a"] = _factory(ConcurrentStableList(), "a")()
    with pytest.raises(RuntimeError, match="可用：a"):
        system.app("missing")


async def test_reset_per_test_clears_tenant_cache() -> None:
    """每例复位只清租户缓存，不重建应用；无租户源的 app 不报错。"""
    log: ConcurrentStableList[str] = ConcurrentStableList()
    cached = _factory(log, "cached")()
    cache = MemoryCacheRegion()
    cache.set("k", 1)
    cached.state.tenant_source = SimpleNamespace(cache=cache)
    plain = _factory(log, "plain")()
    system = AssembledSystem(ConcurrentStableDict({"cached": lambda: cached, "plain": lambda: plain}))

    await system.assemble()
    system.reset_per_test()

    assert cache.get("k") is None
    assert system.app("cached") is cached
    await system.aclose()


def test_process_singleton() -> None:
    """未登记时取用即报错；登记后可取；复位后再次报错。"""
    with pytest.raises(RuntimeError, match="尚未装配"):
        get_assembled_system()

    system = AssembledSystem(ConcurrentStableDict())
    set_assembled_system(system)
    assert get_assembled_system() is system

    reset_assembled_system()
    with pytest.raises(RuntimeError, match="尚未装配"):
        get_assembled_system()


async def test_before_start_hook_runs_before_lifespan() -> None:
    """每个应用在进入 lifespan 之前先执行准备回调（对端声明装载等）。"""
    log: ConcurrentStableList[str] = ConcurrentStableList()
    prepared: ConcurrentStableList[str] = ConcurrentStableList()
    system = AssembledSystem(
        ConcurrentStableDict({"a": _factory(log, "a")}),
        before_start=lambda key, app: prepared.add(f"prepare:{key}"),
    )

    await system.assemble()
    assert list(prepared) == ["prepare:a"]
    assert list(log) == ["enter:a"]
    await system.aclose()
