#!/usr/bin/env python3
"""锁与写微基准（13_08 T1）：六项，各跑 N 次，出平均 / p50 / p95。

口径见详细设计 §13.4。**六项分两类**：

- **实现无关的历史口径**（与任务书 §2.3 逐格可比）：只取放文件写锁、建表 + 写一行 + 提交（不持锁 /
  持写门）、已有表上 `BEGIN IMMEDIATE` + 写一行；
- **当前实现的入口成本**：`gate_scope` 写门取放（含任务级持有登记与快照落盘）、操作系统原生锁取放
  （对照实施记录 §2.1 的 0.003ms）。

`BEGIN IMMEDIATE` 已从 `bms_core` 删除（详细记录 §2.16：互斥只由门提供），故第 4 项直接对 SQLite
执行，量的是「SQLite 写事务本身」而不是某个已不存在的 API。门名固定 `perf-micro`，不碰 `platform` /
`tenant` 的真实门记账与持有者快照。
"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing import rwlock
from bms_core.testing.gates import close_gates, gate_scope
from bms_core.testing.locks import file_lock
from bms_core.testing.paths import configure_project_root

DEFAULT_COUNT = 200
"""每项微基准的采样次数（与任务书 §2.3 一致）。"""

GATE_NAME = "perf-micro"
"""微基准专用门名（不碰 `platform` / `tenant` 的真实门）。"""


@dataclass(frozen=True)
class MicroResult:
    """单项微基准结果。

    Attributes:
        key: 稳定键（基线对比用，勿随意改名）。
        label: 中文口径名。
        count: 采样次数。
        avg_ms: 平均值（毫秒）。
        p50_ms: 中位数（毫秒，最近秩法）。
        p95_ms: p95（毫秒，最近秩法）。
    """

    key: str
    label: str
    count: int
    avg_ms: float
    p50_ms: float
    p95_ms: float


def percentile(samples: ConcurrentStableList[float], quantile: float) -> float:
    """最近秩法百分位（第 ⌈q·n⌉ 个样本）。

    Args:
        samples: 采样值。
        quantile: 分位（0 < q ≤ 1）。

    Returns:
        float: 分位值；空样本返回 0。
    """
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = max(1, math.ceil(quantile * len(ordered))) - 1
    return ordered[min(index, len(ordered) - 1)]


def summarize(key: str, label: str, samples: ConcurrentStableList[float]) -> MicroResult:
    """把采样值汇总成一行结果（毫秒）。

    Args:
        key: 稳定键。
        label: 中文口径名。
        samples: 采样值（秒）。

    Returns:
        MicroResult: 汇总结果。
    """
    count = len(samples)
    total = 0.0
    for sample in samples:
        total += sample
    average = total / count if count else 0.0
    return MicroResult(
        key=key,
        label=label,
        count=count,
        avg_ms=round(average * 1000, 3),
        p50_ms=round(percentile(samples, 0.50) * 1000, 3),
        p95_ms=round(percentile(samples, 0.95) * 1000, 3),
    )


def _tidy(workdir: Path) -> Path:
    """清掉上一轮的微基准库文件并返回工作目录。

    Args:
        workdir: 微基准工作目录。

    Returns:
        Path: 工作目录（已创建）。
    """
    workdir.mkdir(parents=True, exist_ok=True)
    for path in sorted(workdir.glob("*.db")):
        try:
            path.unlink()
        except OSError:
            continue
    return workdir


async def _create_and_insert(url: str, table: str) -> float:
    """建表 + 写一行 + 提交（`NullPool`，每次冷连接），返回耗时秒数。

    Args:
        url: SQLite 连接串。
        table: 本次使用的表名（每次唯一，避免重名冲突）。

    Returns:
        float: 耗时（秒）。
    """
    started = time.perf_counter()
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, v TEXT)")
            await connection.exec_driver_sql(f"INSERT INTO {table} (v) VALUES ('x')")
    finally:
        await engine.dispose()
    return time.perf_counter() - started


async def _measure_file_lock(count: int) -> ConcurrentStableList[float]:
    """#1 只取放文件写锁（无争用）。"""
    samples: ConcurrentStableList[float] = ConcurrentStableList()
    for _ in range(count):
        started = time.perf_counter()
        with file_lock("perf-micro-file-lock"):
            pass
        samples.add(time.perf_counter() - started)
    return samples


async def _measure_write(count: int, url: str, prefix: str, *, gated: bool) -> ConcurrentStableList[float]:
    """#2 / #3 建表 + 写一行 + 提交（不持锁 / 持写门）。"""
    samples: ConcurrentStableList[float] = ConcurrentStableList()
    for index in range(count):
        table = f"{prefix}_{index}"
        if gated:
            async with gate_scope(GATE_NAME, read_only=False):
                samples.add(await _create_and_insert(url, table))
        else:
            samples.add(await _create_and_insert(url, table))
    return samples


async def _measure_begin_immediate(count: int, url: str) -> ConcurrentStableList[float]:
    """#4 已有表上 `BEGIN IMMEDIATE` + 写一行。"""
    engine = create_async_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    samples: ConcurrentStableList[float] = ConcurrentStableList()
    try:
        async with engine.connect() as connection:
            await connection.exec_driver_sql("CREATE TABLE t4 (id INTEGER PRIMARY KEY, v TEXT)")
        for _ in range(count):
            started = time.perf_counter()
            async with engine.connect() as connection:
                await connection.exec_driver_sql("BEGIN IMMEDIATE")
                await connection.exec_driver_sql("INSERT INTO t4 (v) VALUES ('x')")
                await connection.exec_driver_sql("COMMIT")
            samples.add(time.perf_counter() - started)
    finally:
        await engine.dispose()
    return samples


async def _measure_gate_cycle(count: int) -> ConcurrentStableList[float]:
    """#5 写门取放（`gate_scope`，含记账）。"""
    samples: ConcurrentStableList[float] = ConcurrentStableList()
    for _ in range(count):
        started = time.perf_counter()
        async with gate_scope(GATE_NAME, read_only=False):
            pass
        samples.add(time.perf_counter() - started)
    return samples


async def _measure_os_lock(count: int, workdir: Path) -> ConcurrentStableList[float]:
    """#6 只取放操作系统原生锁（门实现的最底层）。"""
    # 私有入口：要量的是「OS 锁本身」，走公开的 DbGate 会把任务记账与快照落盘一起算进来（那是 #5）。
    backend = rwlock._make_backend(workdir / "raw-os.lock")
    samples: ConcurrentStableList[float] = ConcurrentStableList()
    try:
        for _ in range(count):
            started = time.perf_counter()
            acquired = backend.try_acquire(write=True)
            backend.release()
            samples.add(time.perf_counter() - started)
            if not acquired:
                raise RuntimeError("原生锁在无争用场景下未能取得独占锁")
    finally:
        backend.close()
    return samples


async def run_micro(backend: Path, count: int = DEFAULT_COUNT) -> ConcurrentStableList[MicroResult]:
    """跑完六项微基准。

    Args:
        backend: `backend/` 目录（门文件与微基准库落其 `.cache/test/`）。
        count: 每项采样次数。

    Returns:
        ConcurrentStableList[MicroResult]: 六项结果（固定顺序）。
    """
    configure_project_root(str(backend))
    workdir = _tidy(backend / ".cache" / "perf" / "micro")
    # 每项一个独立库文件：#2/#3 各建 200 张表，共用库会把后续项的 fsync 成本推高（实测 #4 从 3.3ms 涨到 7.5ms）。
    urls = {
        name: f"sqlite+aiosqlite:///{(workdir / f'{name}.db').as_posix()}" for name in ("no_gate", "gated", "begin")
    }
    results: ConcurrentStableList[MicroResult] = ConcurrentStableList()
    try:
        results.add(summarize("file_lock", "只取放文件写锁（无争用）", await _measure_file_lock(count)))
        results.add(
            summarize(
                "write_no_gate",
                "建表 + 写一行 + 提交（不持锁）",
                await _measure_write(count, urls["no_gate"], "t2", gated=False),
            )
        )
        results.add(
            summarize(
                "write_gate",
                "建表 + 写一行 + 提交（持写门）",
                await _measure_write(count, urls["gated"], "t3", gated=True),
            )
        )
        results.add(
            summarize(
                "begin_immediate",
                "已有表上 BEGIN IMMEDIATE + 写一行",
                await _measure_begin_immediate(count, urls["begin"]),
            )
        )
        results.add(summarize("gate_cycle", "写门取放（gate_scope，含记账）", await _measure_gate_cycle(count)))
        results.add(summarize("os_lock", "只取放操作系统原生锁", await _measure_os_lock(count, workdir)))
    finally:
        close_gates()
    return results


def run_micro_sync(backend: Path, count: int = DEFAULT_COUNT) -> ConcurrentStableList[MicroResult]:
    """`run_micro` 的同步入口（脚本侧调用）。

    Args:
        backend: `backend/` 目录。
        count: 每项采样次数。

    Returns:
        ConcurrentStableList[MicroResult]: 六项结果。
    """
    return asyncio.run(run_micro(backend, count))
