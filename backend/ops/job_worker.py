"""作业 worker 开发便捷入口：`python -m ops.job_worker --service <key> [--once]`。

- **生产不用**：每个服务由自身 `bms_<service>.jobs` 承载（容器命令 `python -m bms_<service>.jobs`）；
- 本命令只用于开发 / 排障：按服务标识动态导入 `bms_<service>.jobs` 并复用其 `build_worker()`，
  不复制 handler / 声明，避免双份维护；
- 前置：目标服务包已安装（镜像只装目标服务，跨服务跑会导入失败，这是刻意的边界）。
"""

from __future__ import annotations

import argparse
import contextlib
from importlib import import_module
from typing import cast

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.jobs.worker import JobWorker
from ops._worker import run_with_worker_id

__all__ = ["main"]


def _build_worker(service_key: str) -> tuple[JobWorker, object]:
    """按服务标识构造 worker（复用服务入口的装配）。

    Args:
        service_key: 服务标识（如 `platform` / `file`）。

    Returns:
        tuple[JobWorker, object]: worker 与引擎注册表（调用方负责释放）。

    Raises:
        SystemExit: 服务包不存在或未提供 `build_worker`。
    """
    module_name = f"bms_{service_key}.jobs"
    try:
        module = import_module(module_name)
    except ImportError as exc:
        raise SystemExit(f"服务包不可导入：{module_name}（{exc}）") from exc
    builder = getattr(module, "build_worker", None)
    if builder is None or not callable(builder):
        raise SystemExit(f"服务未提供作业 worker 装配：{module_name}.build_worker")
    return cast("tuple[JobWorker, object]", builder())


async def _run(args: argparse.Namespace) -> int:
    """运行 worker（单轮或长驻）。

    Args:
        args: 命令行参数。

    Returns:
        int: 退出码。
    """
    worker, engine_registry = _build_worker(args.service)
    closer = getattr(engine_registry, "aclose", None)
    try:
        if args.once:
            report = await worker.run_once()
            print(f"单轮抢占 {report.claimed} 条 / 执行 {report.executed} 条 / 回收 {report.requeued} 条")
            return 0
        print(f"作业 worker 启动：{worker.worker_id}（服务 {args.service}）")
        await worker.run_forever()
    except KeyboardInterrupt:
        print("作业 worker 收到中断，已退出")
    finally:
        await worker.aclose()
        if callable(closer):
            await closer()
    return 0


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（None 取 `sys.argv`）。

    Returns:
        int: 退出码。
    """
    parser = argparse.ArgumentParser(prog="ops.job_worker", description="作业 worker 开发便捷入口")
    parser.add_argument("--service", required=True, help="服务标识（如 platform / file）")
    parser.add_argument("--once", action="store_true", help="只跑一轮即退出（诊断 / 冒烟）")
    args = parser.parse_args(None if argv is None else list(argv))
    with contextlib.suppress(KeyboardInterrupt):
        return run_with_worker_id(lambda: _run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
