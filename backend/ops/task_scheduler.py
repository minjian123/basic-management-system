"""任务调度命令行：内置任务清单 / beat 调度 / 单轮诊断（不启 HTTP、不跑 lifespan）。

用法::

    # 打印内置任务清单（不连库、不连 Redis）
    uv run python -m ops.task_scheduler --list

    # 长驻调度（单副本；锁 bms:global:lock:beat）
    uv run python -m ops.task_scheduler --beat

    # 单轮诊断：跑一轮 tick 即退出（联调 / 冒烟）
    uv run python -m ops.task_scheduler --beat --once

    # 长驻执行（多副本；从 Redis 队列取任务）
    uv run python -m ops.task_scheduler --worker

    # 单条诊断：消费一条消息即退出
    uv run python -m ops.task_scheduler --worker --once

- **不启 lifespan**：CLI 不建表、不跑启动校验，只装配「调度器 + 引擎注册表 + 锁 + 队列 + 信号」；
  首次使用前服务应已正常启动过一次（库表就绪）。
- **前置**：`[task_scheduler]` 参数就绪；`[distributed_lock].provider = "redis"`（否则退化为进程内锁，
  多实例会双发）；`[redis]` 指向可用实例。
- **租户枚举**：库键由租户注册库（`platform_tenant`）的 `db_basis` 派生，清单按
  `[task_scheduler].tenant_cache_ttl_seconds` 缓存；与 `ops/migrate_tenants` 同一口径。
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import time
from importlib import import_module
from typing import cast

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings, get_settings
from bms_core.core.plugin import build_plugin_registry, resolve_plugin
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import build_platform_db_key, build_tenant_db_key
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory
from bms_core.db.tenant_source import TENANT_SERVICE_KEY
from bms_core.lock.base import BaseDistributedLock
from bms_core.lock.memory import MemoryDistributedLock
from bms_core.metrics.base import BaseMetrics
from bms_core.metrics.null import NullMetrics
from bms_core.tasks.builtin import BUILTIN_TASK_SPECS
from bms_core.tasks.queue import TaskQueue
from bms_core.tasks.scheduler import TaskScheduler
from bms_core.tasks.signal import TaskChangeSignal
from bms_core.tasks.worker import TaskWorker
from bms_core.tenant.registry import tenant_refs

RUN_IMAGE = "*"
"""本脚本只依赖 `bms_core` 与 `ops`（不导入任何服务包），任意服务镜像均可运行。"""

_PLATFORM_UNIT = "platform"
"""任务定义与执行记录落在 platform 服务的租户库。"""


def _resolve[PortT](plugin_key: str, provider: str, expected_version: str, fallback: PortT) -> PortT:
    """解析能力实现：未配置 provider 时直接取缺省实现（不构建注册表）。

    Args:
        plugin_key: 能力域键。
        provider: 配置选定的实现名（空 → 缺省实现）。
        expected_version: 期望契约版本。
        fallback: 未配置时的缺省实现实例。

    Returns:
        PortT: 能力实现实例。
    """
    if not provider:
        return fallback
    for module in ("bms_core.lock.null", "bms_core.metrics.null"):
        import_module(module)
    build_plugin_registry()
    return cast("PortT", resolve_plugin(plugin_key, provider, expected_version=expected_version))


class TenantKeyCache(BaseFrameworkObject):
    """租户库键清单（带 TTL 缓存；新开通租户最迟一个 TTL 后被纳入调度）。"""

    def __init__(self, *, factory: EngineFactory, ttl_seconds: float) -> None:
        """初始化。

        Args:
            factory: 引擎工厂（取租户注册库连接串）。
            ttl_seconds: 缓存有效期（秒）。
        """
        self._factory = factory
        self._ttl = ttl_seconds
        self._cached: ConcurrentStableList[str] = ConcurrentStableList()
        self._expires_at = 0.0

    async def __call__(self) -> ConcurrentStableList[str]:
        """取租户库键清单（命中缓存直接返回）。

        Returns:
            ConcurrentStableList[str]: 租户库键清单。
        """
        now = time.monotonic()
        if self._cached and now < self._expires_at:
            return self._cached
        registry_url = self._factory.resolved_url(build_platform_db_key(TENANT_SERVICE_KEY))
        refs = await tenant_refs(registry_url)
        keys: ConcurrentStableList[str] = ConcurrentStableList(
            build_tenant_db_key(ref.db_basis, service=_PLATFORM_UNIT) for ref in refs
        )
        self._cached = keys
        self._expires_at = now + self._ttl
        return keys


def _build_scheduler(settings: Settings) -> tuple[TaskScheduler, EngineRegistry]:
    """按配置装配调度器与引擎注册表（调用方负责释放）。

    Args:
        settings: 应用配置。

    Returns:
        tuple[TaskScheduler, EngineRegistry]: 调度器与引擎注册表。
    """
    factory = EngineFactory(settings)
    registry = EngineRegistry(factory)
    lock = _resolve(
        "distributed_lock",
        settings.distributed_lock.provider,
        BaseDistributedLock.contract_version,
        MemoryDistributedLock(),
    )
    metrics = _resolve("metrics", settings.metrics.provider, BaseMetrics.contract_version, NullMetrics())
    scheduler = TaskScheduler(
        settings=settings.task_scheduler,
        registry=registry,
        queue=TaskQueue(key=settings.task_scheduler.queue_key),
        lock=lock,
        tenant_keys=TenantKeyCache(factory=factory, ttl_seconds=settings.task_scheduler.tenant_cache_ttl_seconds),
        signal=TaskChangeSignal(channel=settings.task_scheduler.change_channel),
        session_factory=SessionFactory(),
        metrics=metrics,
    )
    return scheduler, registry


def _build_worker(settings: Settings) -> tuple[TaskWorker, EngineRegistry]:
    """按配置装配执行器与引擎注册表（调用方负责释放）。

    Args:
        settings: 应用配置。

    Returns:
        tuple[TaskWorker, EngineRegistry]: 执行器与引擎注册表。
    """
    registry = EngineRegistry(EngineFactory(settings))
    metrics = _resolve("metrics", settings.metrics.provider, BaseMetrics.contract_version, NullMetrics())
    worker = TaskWorker(
        settings=settings.task_scheduler,
        registry=registry,
        queue=TaskQueue(key=settings.task_scheduler.queue_key),
        allowed_handler_prefixes=settings.task_scheduler.allowed_handler_prefixes,
        session_factory=SessionFactory(),
        metrics=metrics,
    )
    return worker, registry


def _print_builtin_tasks() -> int:
    """打印内置任务清单。

    Returns:
        int: 退出码（0）。
    """
    print("内置任务清单：")
    for spec in BUILTIN_TASK_SPECS:
        print(f"  {spec.code:<24} {spec.cron:<14} {spec.name}（归口 {spec.owner}）")
    return 0


async def _run_beat(args: argparse.Namespace) -> int:
    """运行调度器（单轮或长驻）。

    Args:
        args: 命令行参数。

    Returns:
        int: 退出码（0 成功 / 1 单轮被锁跳过）。
    """
    settings = get_settings()
    scheduler, registry = _build_scheduler(settings)
    try:
        if args.once:
            report = await scheduler.tick()
            if not report.lock_held:
                print("调度锁被占用（另一实例在跑），本轮回跳过")
                return 1
            print(f"单轮派发 {report.dispatched} 条 / 回收超时 {report.reclaimed} 条")
            return 0
        print(f"调度器启动：轮询 {settings.task_scheduler.poll_interval_seconds}s，锁 {scheduler.lock_key}")
        await scheduler.run_forever()
    except KeyboardInterrupt:
        print("调度器收到中断，已退出")
    finally:
        await scheduler.aclose()
        await registry.aclose()
    return 0


async def _run_worker(args: argparse.Namespace) -> int:
    """运行执行器（单条或长驻）。

    Args:
        args: 命令行参数。

    Returns:
        int: 退出码（0 成功；单条模式下队列空返回 1）。
    """
    settings = get_settings()
    worker, registry = _build_worker(settings)
    try:
        if args.once:
            handled = await worker.run_once()
            if not handled:
                print("队列为空（无可消费任务）")
                return 1
            print("已消费一条任务")
            return 0
        queue_key = settings.task_scheduler.queue_key
        concurrency = settings.task_scheduler.worker_concurrency
        print(f"执行器启动：并发 {concurrency}，队列 {queue_key}")
        await worker.run_forever()
    except KeyboardInterrupt:
        print("执行器收到中断，已退出")
    finally:
        await worker.aclose()
        await registry.aclose()
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """构造命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(prog="ops.task_scheduler", description="任务调度器（beat）与内置任务清单")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--list", action="store_true", help="打印内置任务清单（不连库）")
    modes.add_argument("--beat", action="store_true", help="运行调度器（长驻；配 --once 只跑一轮）")
    modes.add_argument("--worker", action="store_true", help="运行执行器（长驻；配 --once 只消费一条）")
    parser.add_argument("--once", action="store_true", help="只跑一轮 tick 即退出（联调 / 冒烟）")
    return parser


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（None 取 `sys.argv`）。

    Returns:
        int: 退出码。
    """
    parser = _build_parser()
    args = parser.parse_args(None if argv is None else list(argv))
    if args.list:
        return _print_builtin_tasks()
    runner = _run_worker if args.worker else _run_beat
    with contextlib.suppress(KeyboardInterrupt):
        return asyncio.run(runner(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
