"""并发集合微基准：单/多线程吞吐与锁开销对比（手动执行，CI 不跑）。

用法：
    uv run python -m benchmarks.bench_collections
"""

import json
import threading
import time
from collections.abc import Callable

from app.core.collections import SortedDict
from app.core.concurrent import ConcurrentSortedDict, LockStrategy

OPERATIONS = 20_000
READ_RATIO = 0.9
KEYSPACE = 500

Setter = Callable[[str, int], None]
Getter = Callable[[str], int | None]


def _workload(setter: Setter, getter: Getter, operations: int) -> None:
    for index in range(operations):
        key = f"k{index % KEYSPACE}"
        if index % 10 == 0:
            setter(key, index)
        else:
            getter(key)


def _benchmark(setter: Setter, getter: Getter, operations: int, threads: int) -> float:
    barrier = threading.Barrier(threads) if threads > 1 else None

    def worker(count: int) -> None:
        if barrier is not None:
            barrier.wait()
        _workload(setter, getter, count)

    workers = [threading.Thread(target=worker, args=(operations // threads,)) for _ in range(threads)]
    started = time.perf_counter()
    for worker_thread in workers:
        worker_thread.start()
    for worker_thread in workers:
        worker_thread.join()
    elapsed = time.perf_counter() - started
    return operations / elapsed


def _concurrent_setter(data: ConcurrentSortedDict[str, int]) -> Setter:
    return lambda key, value: data.set(key, value)


def _concurrent_getter(data: ConcurrentSortedDict[str, int]) -> Getter:
    return lambda key: data.get(key)


def main() -> None:
    """运行微基准并输出吞吐表。"""
    raw: SortedDict[str, int] = SortedDict()

    def raw_setter(key: str, value: int) -> None:
        raw[key] = value

    def raw_getter(key: str) -> int | None:
        return raw.get(key)

    rows: list[dict[str, object]] = [
        {
            "名称": "SortedDict（裸，单线程）",
            "策略": "—",
            "线程": 1,
            "ops/秒": round(_benchmark(raw_setter, raw_getter, OPERATIONS, 1)),
        }
    ]

    for strategy in LockStrategy:
        data: ConcurrentSortedDict[str, int] = ConcurrentSortedDict(strategy=strategy)
        setter = _concurrent_setter(data)
        getter = _concurrent_getter(data)
        rows.append(
            {
                "名称": "ConcurrentSortedDict",
                "策略": strategy.value,
                "线程": 1,
                "ops/秒": round(_benchmark(setter, getter, OPERATIONS, 1)),
            }
        )
        shared: ConcurrentSortedDict[str, int] = ConcurrentSortedDict(strategy=strategy)
        shared_setter = _concurrent_setter(shared)
        shared_getter = _concurrent_getter(shared)
        rows.append(
            {
                "名称": "ConcurrentSortedDict",
                "策略": strategy.value,
                "线程": 4,
                "ops/秒": round(_benchmark(shared_setter, shared_getter, OPERATIONS, 4)),
            }
        )

    header = f"{'名称':<28}{'策略':<10}{'线程':>4}{'ops/秒':>12}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(f"{row['名称']:<28}{row['策略']:<10}{row['线程']:>4}{row['ops/秒']:>12}")
    print("-" * len(header))
    print(f"参数：操作 {OPERATIONS}、读写比 1:9、键空间 {KEYSPACE}")
    print(json.dumps(rows, ensure_ascii=False))


if __name__ == "__main__":
    main()
