"""审计链写入侧基准（15_01，手动执行、CI 不跑）：稳态吞吐 + 积压排空。

用法：
    uv run python -m benchmarks.bench_audit_chain --rows 50000 --mode both
    uv run python -m benchmarks.bench_audit_chain --rows 50000 --mode steady --tenant 9000000000000001

口径：
- **稳态**：逐条构造事件并立即入链（无积压），输出条/秒与 P50 / P95 / P99 写入时延；
- **排空**：先按时间构造 `rows` 条事件（`occurred_at` = 入队时刻）再逐条消费，输出端到端时延
  （入队 → 落库）与排空总耗时——**不含** broker 传输与消费组拉取（本机无 broker，见详细设计 §7.3）；
- 每条一个事务（与 `audit-chain` 消费处理器同口径：一条事件一个平台库短事务）；
- 指标器用真实 `PrometheusMetrics`，跑完渲染 `bms_audit_write_total` / `bms_audit_consume_lag_seconds`
  样本值，证明发射点真实生效。
- 库：平台库（`[database]` 配置，开发态为 `database/bms/bms_platform.db`），只写审计分片表，租户取合成主键。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import Table

from bms_core.audit.events import OPERATION_LOG_EVENT
from bms_core.audit.sha256 import Sha256HashChain
from bms_core.audit.shards import month_key
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.logging import configure_logging
from bms_core.db.engine import PLATFORM_DB_KEY, EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory, session_scope
from bms_core.events.base import EventEnvelope
from bms_core.metrics.prometheus import PrometheusMetrics
from bms_core.models.base import Base
from bms_core.models.platform.log import SysAuditShard
from bms_platform.domains.log.services.writer import AuditLogWriter

DEFAULT_ROWS = 50_000
DEFAULT_TENANT = "9000000000000001"
SERVICE_NAME = "platform-bench"
"""指标标签的服务名（基准进程独立归因，避免与真实服务混采）。"""

os.environ.setdefault("BMS_LOG__LEVEL", "WARNING")
"""基准进程默认压低日志级别（逐条 debug 会把耗时测成日志吞吐；须在取配置前生效）。"""


def _now() -> datetime:
    """当前 UTC naive 时间（与库内存储口径一致）。"""
    return datetime.now(UTC).replace(tzinfo=None)


def _percentile(samples: ConcurrentStableList[float], ratio: float) -> float:
    """取分位值（毫秒；样本已排序）。

    Args:
        samples: 升序样本。
        ratio: 分位比例（0~1）。

    Returns:
        float: 分位值（毫秒，保留两位）。
    """
    if not samples:
        return 0.0
    index = min(len(samples) - 1, max(0, int(len(samples) * ratio) - 1))
    return round(samples[index] * 1000, 2)


def _event(index: int, tenant: str, *, occurred_at: datetime, prefix: str) -> EventEnvelope:
    """构造一条操作日志事件（字段齐备，走真实链写入分支）。"""
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "tenant_id": tenant,
            "user_id": "7",
            "username": "bench",
            "module": "bench",
            "action": "bench:write",
            "method": "POST",
            "path": "/api/v1/bench",
            "status": 200,
            "cost_time": 1,
        }
    )
    return EventEnvelope(
        event_type=OPERATION_LOG_EVENT,
        payload=payload,
        tenant_id=tenant,
        occurred_at=occurred_at,
        event_id=f"{prefix}-{index}",
        aggregate_key=f"tenant:{tenant}",
    )


async def _ensure_ledger(factory: EngineFactory) -> None:
    """确保分片台账表存在（幂等；服务正常启动过一次即已存在）。"""
    engine = factory.create()
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                Base.metadata.create_all, tables=[cast("Table", SysAuditShard.__table__)], checkfirst=True
            )
    finally:
        await engine.dispose()


async def _run(mode: str, rows: int, tenant: str, batch: int) -> ConcurrentStableDict[str, object]:
    """执行一种模式并返回统计结果。

    Args:
        mode: `steady`（稳态吞吐）/ `drain`（积压排空）。
        rows: 事件条数。
        tenant: 租户主键（合成值，避免污染真实租户链）。
        batch: 每多少条提交一次（1 = 真实消费口径「一条一事务」）。

    Returns:
        ConcurrentStableDict[str, object]: 统计结果（吞吐 / 分位 / 指标样本）。
    """
    settings = get_settings()
    configure_logging(settings)
    if not settings.app.service:
        settings.app.service = "platform"
    run_id = f"{int(time.time() * 1000):x}"
    metrics = PrometheusMetrics(SERVICE_NAME)
    factory = EngineFactory(settings)
    registry = EngineRegistry(factory)
    await _ensure_ledger(factory)
    latencies: ConcurrentStableList[float] = ConcurrentStableList()
    lags: ConcurrentStableList[float] = ConcurrentStableList()
    events: ConcurrentStableList[EventEnvelope] = ConcurrentStableList()
    if mode == "drain":
        events.extend(
            _event(index, tenant, occurred_at=_now(), prefix=f"bench-drain-{run_id}") for index in range(rows)
        )
    started = time.perf_counter()

    async with session_scope(registry, db_key=PLATFORM_DB_KEY, factory=SessionFactory()) as session:
        writer = AuditLogWriter(session, Sha256HashChain(), metrics=metrics)
        pending = 0

        async def _write(event: EventEnvelope) -> None:
            """写一条事件（按 batch 决定是否一条一事务）。"""
            nonlocal pending
            if batch <= 1:
                async with session.begin():
                    await writer.write(event)
                return
            await writer.write(event)
            pending += 1
            if pending >= batch:
                await session.commit()
                pending = 0

        if mode == "steady":
            for index in range(rows):
                event = _event(index, tenant, occurred_at=_now(), prefix=f"bench-steady-{run_id}")
                begin = time.perf_counter()
                await _write(event)
                latencies.add(time.perf_counter() - begin)
        else:
            for event in events:
                begin = time.perf_counter()
                await _write(event)
                latencies.add(time.perf_counter() - begin)
                lags.add(max(0.0, (_now() - cast("datetime", event.occurred_at)).total_seconds()))
        if pending:
            await session.commit()

    elapsed = time.perf_counter() - started
    latencies = ConcurrentStableList(sorted(latencies))
    lags = ConcurrentStableList(sorted(lags))
    rendered = metrics.render()
    text = "" if rendered is None else rendered[0].decode("utf-8")
    samples: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    prefixes = ("bms_audit_write_total", "bms_audit_consume_lag_seconds_count", "bms_audit_consume_lag_seconds_sum")
    for line in text.splitlines():
        if line.startswith(prefixes):
            key, _, value = line.rpartition(" ")
            samples.set(key, value)
    result: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "mode": mode,
            "rows": rows,
            "tenant": tenant,
            "batch": batch,
            "month": month_key(_now()),
            "elapsed_seconds": round(elapsed, 2),
            "throughput_per_second": round(rows / elapsed, 1) if elapsed > 0 else 0.0,
            "p50_ms": _percentile(latencies, 0.5),
            "p95_ms": _percentile(latencies, 0.95),
            "p99_ms": _percentile(latencies, 0.99),
            "max_ms": round(latencies[-1] * 1000, 2) if latencies else 0.0,
            "lag_p50_s": _percentile(lags, 0.5) / 1000,
            "lag_p95_s": _percentile(lags, 0.95) / 1000,
            "lag_p99_s": _percentile(lags, 0.99) / 1000,
            "metrics": dict(samples),
        }
    )
    return result


def main(argv: ConcurrentStableList[str]) -> int:
    """命令行入口。

    Args:
        argv: 参数（不含程序名）。

    Returns:
        int: 退出码。
    """
    parser = argparse.ArgumentParser(description="审计链写入侧基准（稳态吞吐 / 积压排空）")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS, help=f"事件条数（缺省 {DEFAULT_ROWS}）")
    parser.add_argument("--tenant", default=DEFAULT_TENANT, help=f"合成租户主键（缺省 {DEFAULT_TENANT}）")
    parser.add_argument("--mode", choices=("steady", "drain", "both"), default="both", help="执行模式")
    parser.add_argument("--batch", type=int, default=1, help="每多少条提交一次（1 = 一条一事务，真实消费口径）")
    parser.add_argument("--out", default="", help="结果 JSON 落盘路径（缺省只打印）")
    args = parser.parse_args(list(argv))

    modes = ["steady", "drain"] if args.mode == "both" else [args.mode]
    results: ConcurrentStableList[object] = ConcurrentStableList()
    for mode in modes:
        result = asyncio.run(_run(mode, args.rows, args.tenant, args.batch))
        print(json.dumps(dict(result), ensure_ascii=False, indent=2), flush=True)
        results.add(dict(result))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(list(results), handle, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(ConcurrentStableList(sys.argv[1:])))
