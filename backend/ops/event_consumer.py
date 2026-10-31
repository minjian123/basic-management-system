"""事件消费命令行：消费组诊断 / 单轮消费 / 独立 worker 宿主（不启 HTTP）。

用法::

    # 打印某服务自持的消费组与订阅（不连 broker、不消费）
    uv run python -m ops.event_consumer --service platform --groups

    # 单轮拉取消费（诊断 / 联调；连 broker，消费一批即退出）
    uv run python -m ops.event_consumer --service platform --once

    # 独立 worker 宿主（长驻；与服务进程 host=in_service 互斥）
    uv run python -m ops.event_consumer --service platform --worker

- **声明同源**：组声明一律取目标服务应用工厂的 `event_consumer_records()`，与进程内宿主完全一致，
  不引入第二套声明。
- **不启 lifespan**：CLI 不建表、不跑启动校验，只装配「消费运行器 + 引擎注册表」所需的最小上下文；
  首次使用前服务应已正常启动过一次（库表就绪）。
- **前置**：`[event_consumer].provider = "rocketmq"`、`[rocketmq].endpoints` 指向 broker proxy
  （8081），且 `[event_consumer].host` 与宿主形态一致（worker 时服务进程不应再消费同一组）。
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal
import sys
from collections.abc import Iterable
from importlib import import_module
from typing import cast

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.plugin import build_plugin_registry, resolve_plugin
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.events.base import BaseEventConsumerGroup, ConsumedTally
from bms_core.events.consumer_records import (
    EventConsumerRecord,
    merge_event_consumer_records,
    validate_event_consumer_records,
)

RUN_IMAGE = "*"
"""本脚本只依赖 `bms_core` 与 `ops`（不导入具体服务实现，按 `--service` 动态取工厂）。"""


def _service_factory(service: str) -> object:
    """按服务键取应用工厂实例（零参构造）。

    Args:
        service: 服务键（如 `platform`）。

    Returns:
        object: `ApplicationFactory` 实例。

    Raises:
        SystemExit: 服务包不存在（退出码 2）。
    """
    module_name = f"bms_{service}.main"
    try:
        module = import_module(module_name)
    except ImportError as exc:
        print(f"服务包不存在：{module_name}（{exc}）", file=sys.stderr)
        raise SystemExit(2) from exc
    factory_type = getattr(module, "ApplicationFactory", None)
    if factory_type is None:
        print(f"服务包未声明 ApplicationFactory：{module_name}", file=sys.stderr)
        raise SystemExit(2)
    return cast("object", factory_type())


def _records(factory: object, *, group_prefix: str) -> ConcurrentStableList[EventConsumerRecord]:
    """取并校验服务自持的消费组声明。

    Args:
        factory: 应用工厂实例。
        group_prefix: 组名前缀。

    Returns:
        ConcurrentStableList[EventConsumerRecord]: 合并后的声明。

    Raises:
        SystemExit: 声明校验不通过（退出码 1）。
    """
    getter = getattr(factory, "event_consumer_records", None)
    declared: ConcurrentStableList[EventConsumerRecord] = (
        ConcurrentStableList(cast("Iterable[EventConsumerRecord]", getter()))
        if callable(getter)
        else ConcurrentStableList()
    )
    records = merge_event_consumer_records(declared, group_prefix=group_prefix)
    errors = validate_event_consumer_records(records)
    if errors:
        for error in errors:
            print(f"[声明校验] {error}", file=sys.stderr)
        raise SystemExit(1)
    return records


def _build_group(records: ConcurrentStableList[EventConsumerRecord]) -> tuple[BaseEventConsumerGroup, EngineRegistry]:
    """构造消费组运行时与引擎注册表（CLI 无应用上下文）。

    Args:
        records: 组声明。

    Returns:
        tuple[BaseEventConsumerGroup, EngineRegistry]: 运行时与注册表（调用方负责释放）。

    Raises:
        SystemExit: provider 未配置（退出码 1）。
    """
    settings = get_settings()
    for module in ("bms_core.events.null", "bms_core.events.rocketmq_consumer"):
        import_module(module)
    build_plugin_registry()
    registry = EngineRegistry(EngineFactory(settings))
    group = cast(
        "BaseEventConsumerGroup",
        resolve_plugin(
            "event_consumer",
            settings.event_consumer.provider,
            expected_version=BaseEventConsumerGroup.contract_version,
        ),
    )
    group.load(records)
    return group, registry


async def _groups(args: argparse.Namespace) -> int:
    """打印已装载组与订阅（不连 broker）。

    Args:
        args: 命令行参数。

    Returns:
        int: 退出码。
    """
    settings = get_settings()
    records = _records(_service_factory(args.service), group_prefix=settings.event_consumer.group_prefix)
    print(f"服务 {args.service}：声明 {len(records)} 条")
    for record in records:
        flag = "有序" if record.ordered else f"并发 {record.concurrency or settings.event_consumer.concurrency}"
        print(f"  - {record.consumer} ← {record.event_type}（{flag}）{record.description}")
    print(f"消费开关 enabled={settings.event_consumer.enabled}；宿主 host={settings.event_consumer.host}")
    return 0


async def _once(args: argparse.Namespace) -> int:
    """单轮消费（连 broker，消费一批即退出）。

    Args:
        args: 命令行参数。

    Returns:
        int: 退出码。
    """
    settings = get_settings()
    records = _records(_service_factory(args.service), group_prefix=settings.event_consumer.group_prefix)
    if not records:
        print("无可消费的组声明（服务未声明 event_consumer_records）")
        return 0
    group, registry = _build_group(records)
    try:
        tally: ConsumedTally = await group.consume_once(max_messages=args.max_messages)
    finally:
        await group.aclose()
        await registry.aclose()
    print(
        f"单轮消费：拉取 {tally.received} / 成功 {tally.succeeded} / 跳过 {tally.skipped} / "
        f"重试 {tally.retried} / 死信 {tally.dead}"
    )
    return 0


async def _worker(args: argparse.Namespace) -> int:
    """独立 worker 宿主（长驻消费，Ctrl+C 退出）。

    Args:
        args: 命令行参数。

    Returns:
        int: 退出码。
    """
    settings = get_settings()
    records = _records(_service_factory(args.service), group_prefix=settings.event_consumer.group_prefix)
    if not records:
        print("无可消费的组声明（服务未声明 event_consumer_records）")
        return 0
    group, registry = _build_group(records)
    stop = asyncio.Event()

    def _request_stop(*_: object) -> None:
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, AttributeError, ValueError):
            asyncio.get_running_loop().add_signal_handler(sig, _request_stop)
    try:
        await group.start()
        print(f"worker 已启动（{args.service}，{len(records)} 条声明）；Ctrl+C 退出")
        await stop.wait()
    finally:
        await group.aclose()
        await registry.aclose()
        print("worker 已停止")
    return 0


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """命令行入口。

    Args:
        argv: 参数列表（缺省取 sys.argv）。

    Returns:
        int: 退出码。
    """
    parser = argparse.ArgumentParser(prog="ops.event_consumer", description="事件消费诊断 / 单轮 / worker 宿主")
    parser.add_argument("--service", default="platform", help="服务键（取该服务的消费组声明），缺省 platform")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--groups", action="store_true", help="打印组与订阅（不连 broker）")
    mode.add_argument("--once", action="store_true", help="单轮拉取消费")
    mode.add_argument("--worker", action="store_true", help="独立 worker 宿主（长驻）")
    parser.add_argument("--max-messages", type=int, default=32, help="单轮单组拉取上限（--once）")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.groups:
        return asyncio.run(_groups(args))
    if args.once:
        return asyncio.run(_once(args))
    return asyncio.run(_worker(args))


if __name__ == "__main__":
    raise SystemExit(main())
