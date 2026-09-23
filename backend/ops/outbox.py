"""发件箱命令行：手动投递 / 事件账本重放（运维入口，不启 lifespan）。

用法::

    uv run python -m ops.outbox dispatch [--db-key platform]
    uv run python -m ops.outbox replay [--event-type T] [--aggregate-key K] [--since ISO] [--db-key K] [--limit N]

- `dispatch`：构造轮询投递器，对指定库执行一次投递（不启动后台循环）。
- `replay`：把已投递 / 死信事件按 类型 / 聚合 / 时间 重置为待投递（消费端 `event_id` 幂等，重放安全）。
- 缺省库键为平台库；租户库传 `--db-key tenant_<code>`。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from importlib import import_module
from typing import cast

from bms_core.core.config import get_settings
from bms_core.core.plugin import build_plugin_registry, resolve_plugin
from bms_core.db.engine import PLATFORM_DB_KEY, EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory, session_scope
from bms_core.events.base import EventPublisher
from bms_core.events.null import NullEventPublisher
from bms_core.metrics.base import BaseMetrics
from bms_core.metrics.null import NullMetrics
from bms_core.outbox.dispatcher import PollOutboxDispatcher
from bms_core.outbox.store import SqlOutboxStore


def _resolve[PortT](plugin_key: str, provider: str, expected_version: str, fallback: PortT) -> PortT:
    """解析能力实现：未配置 provider 时直接取缺省实现（不构建注册表，避免影响同进程装配）。

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
    for module in ("bms_core.events.null", "bms_core.metrics.null"):
        import_module(module)
    build_plugin_registry()
    return cast("PortT", resolve_plugin(plugin_key, provider, expected_version=expected_version))


def _build_dispatcher() -> tuple[PollOutboxDispatcher, EngineRegistry]:
    """构造投递器与引擎注册表（CLI 无应用上下文，按配置自行装配）。

    Returns:
        tuple[PollOutboxDispatcher, EngineRegistry]: 投递器与引擎注册表（调用方负责释放）。
    """
    settings = get_settings()
    publisher = _resolve("event", settings.event.provider, EventPublisher.contract_version, NullEventPublisher())
    metrics = _resolve("metrics", settings.metrics.provider, BaseMetrics.contract_version, NullMetrics())
    registry = EngineRegistry(EngineFactory(settings))
    dispatcher = PollOutboxDispatcher.from_settings(
        settings,
        store=SqlOutboxStore(),
        publisher=publisher,
        engine_registry=registry,
        session_factory=SessionFactory(),
        metrics=metrics,
    )
    return dispatcher, registry


async def _dispatch(args: argparse.Namespace) -> int:
    """执行一次投递并打印汇总。

    Args:
        args: 命令行参数。

    Returns:
        int: 退出码（0 成功）。
    """
    dispatcher, registry = _build_dispatcher()
    try:
        result = await dispatcher.dispatch_once(db_key=args.db_key)
    finally:
        await dispatcher.aclose()
        await registry.aclose()
    print(
        f"投递（{args.db_key}）：成功 {result.published} / 失败 {result.failed} / "
        f"死信 {result.dead} / 积压 {result.backlog}"
    )
    return 0


async def _replay(args: argparse.Namespace) -> int:
    """按条件重置发件箱为待投递并打印条数。

    Args:
        args: 命令行参数。

    Returns:
        int: 退出码（0 成功）。
    """
    settings = get_settings()
    registry = EngineRegistry(EngineFactory(settings))
    store = SqlOutboxStore()
    since = datetime.fromisoformat(args.since) if args.since else None
    try:
        async with (
            session_scope(registry, db_key=args.db_key, factory=SessionFactory()) as session,
            session.begin(),
        ):
            count = await store.replay(
                session,
                event_type=args.event_type,
                aggregate_key=args.aggregate_key,
                since=since,
                limit=args.limit,
            )
    finally:
        await registry.aclose()
    print(f"重放（{args.db_key}）：重置待投递 {count} 条")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """构造命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(prog="ops.outbox", description="发件箱投递与重放")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dispatch = subparsers.add_parser("dispatch", help="手动执行一次投递")
    dispatch.add_argument("--db-key", default=PLATFORM_DB_KEY, help="数据源键（缺省平台库）")

    replay = subparsers.add_parser("replay", help="重置已投递 / 死信为待投递")
    replay.add_argument("--event-type", default=None, help="事件类型筛选")
    replay.add_argument("--aggregate-key", default=None, help="聚合键筛选")
    replay.add_argument("--since", default=None, help="发生时间下限（ISO 格式）")
    replay.add_argument("--limit", type=int, default=None, help="重置上限")
    replay.add_argument("--db-key", default=PLATFORM_DB_KEY, help="数据源键（缺省平台库）")
    return parser


def main(argv: list[str] | None = None) -> int:
    """入口：解析参数并执行子命令。

    Args:
        argv: 参数列表（None 取 `sys.argv`）。

    Returns:
        int: 退出码。
    """
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "dispatch":
            return asyncio.run(_dispatch(args))
        return asyncio.run(_replay(args))
    except Exception as exc:
        print(f"发件箱命令失败：{exc!r}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
