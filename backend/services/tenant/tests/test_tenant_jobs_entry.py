"""租户服务作业 worker 入口用例（任务 `04_03-02`）：声明构造 / 单轮与长驻分支 / WorkerId 租约包裹。"""

from __future__ import annotations

import runpy
import sys
from argparse import Namespace
from types import SimpleNamespace
from typing import Any

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_tenant import jobs
from bms_tenant.domains.tenant.jobs import TENANT_PURGE_JOB_TYPE, TENANT_PURGE_SCAN_JOB_TYPE

pytestmark = pytest.mark.kiwi_id(2458)


class _Worker:
    """作业 worker 替身（不连库）。"""

    worker_id = "w-tenant"

    async def run_once(self) -> Any:
        """单轮执行。

        Returns:
            Any: 结果汇总替身。
        """
        return SimpleNamespace(claimed=1, executed=1, requeued=0)

    async def run_forever(self) -> None:
        """长驻执行：立刻中断（覆盖中断分支）。

        Raises:
            KeyboardInterrupt: 模拟 Ctrl+C。
        """
        raise KeyboardInterrupt

    async def aclose(self) -> None:
        """释放（无副作用）。"""


class _Registry:
    """引擎注册表替身。"""

    def __init__(self) -> None:
        """初始化（记录释放次数）。"""
        self.closed = 0

    async def aclose(self) -> None:
        """释放（记录调用）。"""
        self.closed += 1


def test_job_handlers_and_specs_are_declared() -> None:
    """handler 与类型声明齐备（代码侧唯一登记点）。"""
    assert set(jobs.job_handlers()) == {TENANT_PURGE_SCAN_JOB_TYPE, TENANT_PURGE_JOB_TYPE}
    assert set(jobs.job_specs()) == {TENANT_PURGE_SCAN_JOB_TYPE, TENANT_PURGE_JOB_TYPE}


def test_build_runner_and_worker_construct() -> None:
    """提交器 / worker 按声明装配（不建连）。"""
    assert jobs.build_runner() is not None
    worker, engine_registry = jobs.build_worker()

    assert worker.worker_id
    assert engine_registry is not None


async def test_run_once_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """`--once`：执行单轮后返回 0，并释放 worker 与引擎注册表。"""
    registry = _Registry()
    monkeypatch.setattr(jobs, "build_worker", lambda: (_Worker(), registry))

    assert await jobs._run(Namespace(once=True)) == 0  # pyright: ignore[reportPrivateUsage]
    assert registry.closed == 1


async def test_run_forever_stops_on_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    """长驻模式：收到中断后正常返回 0，并释放 worker 与引擎注册表。"""
    registry = _Registry()
    monkeypatch.setattr(jobs, "build_worker", lambda: (_Worker(), registry))

    assert await jobs._run(Namespace(once=False)) == 0  # pyright: ignore[reportPrivateUsage]
    assert registry.closed == 1


def test_main_wraps_entry_with_worker_id_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    """入口在 WorkerId 租约上下文内执行。"""
    seen: ConcurrentStableList[bool] = ConcurrentStableList()

    async def _fake_run(args: Any) -> int:
        seen.add(bool(args.once))
        return 3

    monkeypatch.setattr(jobs, "_run", _fake_run)

    assert jobs.main(ConcurrentStableList(["--once"])) == 3
    assert list(seen) == [True]


def test_main_returns_zero_on_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    """入口中断：`KeyboardInterrupt` 被抑制，返回 0。"""

    async def _boom(args: Any) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(jobs, "_run", _boom)

    assert jobs.main(ConcurrentStableList()) == 0


def test_module_entrypoint_runs_single_round(monkeypatch: pytest.MonkeyPatch) -> None:
    """`python -m bms_tenant.jobs --once`：模块入口执行单轮后以 0 退出（不连库）。"""
    from bms_core.db.registry import EngineRegistry
    from bms_core.jobs.worker import JobWorker

    async def _run_once(self: Any) -> Any:
        return SimpleNamespace(claimed=0, executed=0, requeued=0)

    async def _noop(self: Any) -> None:
        return None

    monkeypatch.setattr(JobWorker, "run_once", _run_once)
    monkeypatch.setattr(JobWorker, "aclose", _noop)
    monkeypatch.setattr(EngineRegistry, "aclose", _noop)
    monkeypatch.setattr(sys, "argv", ["bms_tenant.jobs", "--once"])

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("bms_tenant.jobs", run_name="__main__")

    assert excinfo.value.code == 0
