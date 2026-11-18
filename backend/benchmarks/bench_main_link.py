"""主链路写路径副作用成本基准（15_01，手动执行、CI 不跑）。

为什么不是 HTTP 压测：本机环境里「服务 A → 服务 B」的回连在启动钩子阶段被拒（与端口 / 代理 /
端点映射无关，已排除），客户端口径无法闭环；改为**同一写路径的应用层 A/B**——真实 ORM 写入 +
真实字段级捕获 + 同事务发件箱，量出「有 / 无审计副作用」的 P99 差异。HTTP 段在压测报告里标
「限定达标（环境阻塞）」。

三个变体（各跑 `--rows` 条，一条一事务）：
- `off`   ：只插一条 `sys_role`（无审计副作用）；
- `field` ：开启 `[audit_capture]` 的 ORM 字段级捕获（业务写入 + **同事务**审计发件箱，06_02 口径）；
- `oplog` ：业务写入后发射一条操作日志事件（`AuditEventEmitter`，独立短事务 = **响应后段**，不计入客户端时延）。

用法：
    uv run python -m benchmarks.bench_main_link --rows 2000 --mode both
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import cast

from sqlalchemy import Table
from sqlalchemy.ext.asyncio import async_sessionmaker

from bms_core.audit.events import build_operation_event
from bms_core.audit.field_capture import install_field_audit, reset_capture_state, uninstall_field_audit
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.id import id_generator
from bms_core.core.logging import configure_logging
from bms_core.db.engine import EngineFactory
from bms_core.models.base import Base
from bms_core.models.outbox import SysOutbox
from bms_core.models.platform.log import SysAuditShard
from bms_core.models.platform.role import SysRole
from bms_core.outbox.store import SqlOutboxStore

os.environ.setdefault("BMS_LOG__LEVEL", "WARNING")
os.environ.setdefault("BMS_DATABASE__SQLITE_DIR", "../../database/bms-perf-15-01")

MODE_OFF = "off"
MODE_FIELD = "field"
MODE_OPLOG = "oplog"


def _percentile(samples: ConcurrentStableList[float], ratio: float) -> float:
    """分位值（毫秒）。"""
    if not samples:
        return 0.0
    index = min(len(samples) - 1, max(0, int(len(samples) * ratio) - 1))
    return round(samples[index] * 1000, 2)


def _role(index: int, run_id: str) -> SysRole:
    """构造一条唯一角色（审计白名单表 `sys_role`）。"""
    return SysRole(
        form_key="bench_role",
        code=f"bench_{run_id}_{index}",
        name=f"基准角色 {index}",
        role_type="custom",
        status="enabled",
        id=id_generator.next_id(),
    )


async def _ensure_schema(factory: EngineFactory) -> None:
    """确保基准所需表存在（幂等；角色 / 发件箱 / 分片台账）。"""
    tables = [SysRole.__table__, SysOutbox.__table__, SysAuditShard.__table__]
    engine = factory.create()
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all, tables=[cast("Table", item) for item in tables])
    finally:
        await engine.dispose()


async def _run(mode: str, rows: int) -> ConcurrentStableDict[str, object]:
    """跑一个变体并返回统计。

    Args:
        mode: `off` / `field` / `oplog`。
        rows: 条目数。

    Returns:
        ConcurrentStableDict[str, object]: 统计结果。
    """
    settings = get_settings()
    configure_logging(settings)
    if not settings.app.service:
        settings.app.service = "platform"
    factory = EngineFactory(settings)
    await _ensure_schema(factory)
    run_id = f"{int(time.time() * 1000):x}"
    session_factory = async_sessionmaker(factory.create(), expire_on_commit=False)
    store = SqlOutboxStore() if mode == MODE_OPLOG else None
    if mode == MODE_FIELD:
        install_field_audit(settings)
    latencies: ConcurrentStableList[float] = ConcurrentStableList()
    started = time.perf_counter()
    try:
        async with session_factory() as session, session_factory() as audit_session:
            for index in range(rows):
                begin = time.perf_counter()
                async with session.begin():
                    session.add(_role(index, run_id))
                if store is not None:
                    event = build_operation_event(
                        tenant_id=None,
                        user_id=7,
                        username="bench",
                        module="role",
                        action="role:create",
                        method="POST",
                        path="/api/v1/roles",
                        query=None,
                        params=None,
                        ip=None,
                        user_agent="bench",
                        cost_time=1,
                        status=200,
                        error_msg=None,
                    )
                    async with audit_session.begin():
                        await store.enqueue(audit_session, event)
                latencies.add(time.perf_counter() - begin)
    finally:
        if mode == MODE_FIELD:
            uninstall_field_audit()
            reset_capture_state()
    elapsed = time.perf_counter() - started
    latencies = ConcurrentStableList(sorted(latencies))
    result: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "variant": mode,
            "rows": rows,
            "elapsed_seconds": round(elapsed, 2),
            "throughput_per_second": round(rows / elapsed, 1) if elapsed > 0 else 0.0,
            "p50_ms": _percentile(latencies, 0.5),
            "p95_ms": _percentile(latencies, 0.95),
            "p99_ms": _percentile(latencies, 0.99),
            "max_ms": round(latencies[-1] * 1000, 2) if latencies else 0.0,
        }
    )
    return result


def main(argv: ConcurrentStableList[str]) -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="主链路写路径副作用成本基准")
    parser.add_argument("--rows", type=int, default=2000, help="每个变体的条目数")
    parser.add_argument("--mode", choices=(MODE_OFF, MODE_FIELD, MODE_OPLOG, "both", "all"), default="both")
    parser.add_argument("--out", default="", help="结果 JSON 落盘路径")
    args = parser.parse_args(list(argv))
    modes = {
        "both": [MODE_OFF, MODE_FIELD],
        "all": [MODE_OFF, MODE_FIELD, MODE_OPLOG],
    }.get(args.mode, [args.mode])
    results: ConcurrentStableList[object] = ConcurrentStableList()
    for mode in modes:
        result = asyncio.run(_run(mode, args.rows))
        print(json.dumps(dict(result), ensure_ascii=False, indent=2), flush=True)
        results.add(dict(result))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(list(results), handle, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(ConcurrentStableList(sys.argv[1:])))
