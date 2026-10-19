#!/usr/bin/env python3
"""选测执行器：推导 → 跑 pytest → 读覆盖率缺口 → 扩圈重跑 → 退化兜底 → 度量。

与 `test_selection.py`（纯推导）配套，构成**预检与 CI 的单一执行入口**：

1. 调 `test_selection.build_selection` 取受影响测试文件与覆盖率目标模块；
2. 跑 `--pytest-cmd`（缺省 `uv run pytest`）+ 选中文件 + `--cov=<变更模块> --cov-branch
   --cov-fail-under=100`；
3. 失败但**不是测试失败**（输出无 `failed` / `error` 计数）且覆盖率有缺行时，把缺行模块并入
   选测集重跑（最多 `--max-rounds` 轮，缺省 2）；
4. 扩圈无新增测试 / 轮次用尽 ⇒ 退化工程级全量重跑一次，并**显式打印原因**；
5. 结束打印度量行（`picked` / `degraded` / `rounds` / `cov`），供 13_03 采集与复盘。

门禁口径不降级：覆盖率目标恒为**最初变更模块**（扩圈只扩大测试集，不扩大门禁范围）。

用法::

    python3 scripts/tools/preflight/run-selected.py --changed-from origin/main
    python3 scripts/tools/preflight/run-selected.py --changed-file backend/libs/... --no-cov
    python3 scripts/tools/preflight/run-selected.py --changed-from HEAD~1 --jobs 4

并行：`--jobs auto|N|off`（缺省 `auto`；`off` 串行），每轮 pytest 同口径追加 `-n`（13_02）。

退出码：pytest 最终退出码（`0` 通过）；推导异常 / 参数非法 `1`；单轮超时 `124`。

用例：Kiwi **2316**（选测器）/ **2318**（并行与重复面护栏，`test_parallel_guard.py`）。
"""

import argparse
import contextlib
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import parallel_jobs  # noqa: E402
import test_selection  # noqa: E402
from test_selection import ConcurrentStableList, ConcurrentStableSet  # noqa: E402

_FAILED_PATTERN = re.compile(r"\b\d+ (?:failed|error|errors)\b")
"""测试失败特征（pytest 摘要行）：出现即判定为真失败，不进入扩圈。"""

_COVERAGE_EXCLUDED_MODULES = ("bms_core.testing.plugin",)
"""覆盖率目标排除项（13_02）：pytest 插件入口由 pytest 在覆盖率探针启动**之前**加载，
行执行不可观测（并行下恒低于 100%，串行可达）；其逻辑本体在 `bms_core.testing.fixtures`，
仍受行 + 分支 100% 门禁。"""


def _run_pytest(cmd: ConcurrentStableList[str], cwd: Path, timeout: float | None) -> tuple[int, str]:
    """执行一轮 pytest：**逐行实时透传**输出（本地后台与 CI 日志即刻可见进度），同时收集全文供判定。

    Args:
        cmd: 命令与参数。
        cwd: 工作目录。
        timeout: 超时（秒；None 表示不设限）。

    Returns:
        tuple[int, str]: （退出码, 完整输出）。

    Raises:
        subprocess.TimeoutExpired: 超过 `timeout`（子进程已被结束）。
    """
    started = time.monotonic()
    process = subprocess.Popen(
        list(cmd),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    lines: ConcurrentStableList[str] = ConcurrentStableList()
    assert process.stdout is not None
    for line in process.stdout:
        lines.add(line.rstrip("\n"))
        print(line, end="", flush=True)
        if timeout is not None and time.monotonic() - started > timeout:
            process.kill()
            raise subprocess.TimeoutExpired(list(cmd), timeout)
    return process.wait(), "\n".join(lines)


def _print_metrics(picked: int, total: int, degraded: bool, rounds: int, cov_modules: int) -> None:
    """打印统一度量行（供复盘与 13_03 采集）。

    Args:
        picked: 选中的测试文件数。
        total: 全部工程测试文件数。
        degraded: 是否发生退化。
        rounds: 实际执行轮次。
        cov_modules: 覆盖率目标模块数。
    """
    print(
        f"[test-selection] picked={picked}/{total} degraded={str(degraded).lower()} "
        f"rounds={rounds} cov={cov_modules} 模块"
    )


def main(argv: tuple[str, ...] | None = None) -> int:
    """命令行入口。

    Args:
        argv: 参数（缺省取 `sys.argv[1:]`）。

    Returns:
        int: pytest 最终退出码 / 推导异常 1 / 超时 124。
    """
    parser = argparse.ArgumentParser(description="选测执行器（推导 → 跑 → 扩圈 → 退化 → 度量）")
    parser.add_argument("--root", default=str(test_selection._REPO_ROOT), help="bms 仓库根")
    parser.add_argument("--changed-from", default="", help="对比基准（git 引用，如 origin/main）")
    parser.add_argument("--changed-file", action="append", default=[], help="显式变更文件（可重复）")
    parser.add_argument("--changed-file-list", default="", help="变更清单文件（一行一个路径）")
    parser.add_argument("--force-full", action="store_true", help="强制退化全量（基准不可解析时）")
    parser.add_argument("--pytest-cmd", default="uv run pytest", help="pytest 执行器前缀（空格分词）")
    parser.add_argument("--pytest-cwd", default="backend", help="pytest 工作目录（相对仓库根）")
    parser.add_argument("--pytest-arg", action="append", default=[], help="透传 pytest 参数（可重复）")
    parser.add_argument(
        "--jobs",
        default=parallel_jobs.DEFAULT_JOBS,
        help="并行档位：auto（缺省）/ 正整数 / off（串行）",
    )
    parser.add_argument("--cov", dest="cov", action="store_true", default=True, help="开启覆盖率门禁（缺省开）")
    parser.add_argument("--no-cov", dest="cov", action="store_false", help="跳过覆盖率门禁")
    parser.add_argument("--cov-fail-under", type=int, default=100, help="覆盖率门禁阈值")
    parser.add_argument("--max-rounds", type=int, default=2, help="扩圈轮次上限")
    parser.add_argument("--cov-json", default="backend/coverage.json", help="覆盖率报告落点（相对仓库根）")
    parser.add_argument("--timeout", type=float, default=0.0, help="单轮 pytest 超时（秒；0 表示不设限）")
    args = parser.parse_args(argv)
    try:
        jobs = parallel_jobs.jobs_args(args.jobs)
    except ValueError as error:
        print(f"[test-selection] {error}", file=sys.stderr)
        return 1
    print(f"[test-selection] {parallel_jobs.describe(args.jobs)}")

    root = Path(args.root).resolve()
    backend = root / "backend"
    force_full = args.force_full
    try:
        changed = test_selection.read_changed(
            root,
            changed_from=args.changed_from,
            changed_files=tuple(args.changed_file),
            changed_file_list=args.changed_file_list,
        )
    except RuntimeError as error:
        print(f"[test-selection] {error} ⇒ 显式退化全量")
        changed = ()
        force_full = True

    try:
        selection = test_selection.build_selection(backend, changed, force_full=force_full)
    except RuntimeError as error:
        print(f"[test-selection] {error}", file=sys.stderr)
        return 1

    if selection.reason:
        print(f"[test-selection] 退化：{selection.reason}")
    for note in selection.notes:
        print(f"[test-selection] 说明：{note}")
    print(
        f"[test-selection] 变更 {len(changed)} 个文件；选中 {selection.picked}/{selection.total} 测试文件"
        f"（{selection.picked / selection.total:.1%}）"
        if selection.total
        else f"[test-selection] 变更 {len(changed)} 个文件；无后端测试文件"
    )
    if selection.cov_modules:
        print(f"[test-selection] 覆盖率门禁（行 + 分支 {args.cov_fail_under}%）：{'、'.join(selection.cov_modules)}")
    if not selection.test_paths:
        print("[test-selection] 无受影响后端测试 ⇒ 跳过 pytest")
        return 0

    test_paths: ConcurrentStableList[str] = ConcurrentStableList(selection.test_paths)
    cov_modules: ConcurrentStableList[str] = ConcurrentStableList(selection.cov_modules)
    excluded = ConcurrentStableList([module for module in cov_modules if module in _COVERAGE_EXCLUDED_MODULES])
    if excluded:
        print(
            f"[test-selection] 覆盖率目标排除（插件入口由 pytest 早于覆盖率探针加载，行执行不可观测）："
            f"{'、'.join(excluded)}"
        )
        cov_modules = ConcurrentStableList([module for module in cov_modules if module not in excluded])
    cov_enabled = args.cov and bool(cov_modules)
    cov_json = (root / args.cov_json).resolve()
    cwd = root / args.pytest_cwd
    rounds = 0
    expanded = 0
    degraded = selection.degraded
    full_retried = degraded
    timeout = args.timeout if args.timeout > 0 else None

    while True:
        rounds += 1
        cmd: ConcurrentStableList[str] = ConcurrentStableList([*shlex.split(args.pytest_cmd), "-q", *test_paths])
        if cov_enabled:
            cmd.update(f"--cov={module}" for module in cov_modules)
            cmd.update(
                [
                    "--cov-branch",
                    "--cov-report=term",
                    f"--cov-report=json:{cov_json.as_posix()}",
                    f"--cov-fail-under={args.cov_fail_under}",
                ]
            )
        cmd.update(jobs)
        cmd.update(args.pytest_arg)
        print(f"\n[test-selection] 第 {rounds} 轮：{len(test_paths)} 个测试文件")
        print(f"  $ {' '.join(cmd)}")
        try:
            code, output = _run_pytest(cmd, cwd, timeout)
        except subprocess.TimeoutExpired:
            print(f"[test-selection] 单轮超时（{timeout:.0f}s）⇒ 中止；长命令交 CI")
            _print_metrics(len(test_paths), selection.total, degraded, rounds, len(cov_modules))
            return 124

        if code == 0:
            _print_metrics(len(test_paths), selection.total, degraded, rounds, len(cov_modules))
            return 0

        # 真失败（测试 / 收集错误）：原样透传，不扩圈
        if _FAILED_PATTERN.search(output):
            _print_metrics(len(test_paths), selection.total, degraded, rounds, len(cov_modules))
            return code

        if not cov_enabled:
            _print_metrics(len(test_paths), selection.total, degraded, rounds, 0)
            return code

        missing = test_selection.expand_from_coverage(cov_json, tuple(cov_modules))
        if not missing:
            _print_metrics(len(test_paths), selection.total, degraded, rounds, len(cov_modules))
            return code

        merged: ConcurrentStableSet[str] = ConcurrentStableSet()
        merged.update(test_paths)
        for rel in test_selection.tests_for_modules(backend, missing):
            merged.add(rel)

        if len(merged) == len(test_paths) or expanded >= args.max_rounds:
            if full_retried:
                _print_metrics(len(test_paths), selection.total, degraded, rounds, len(cov_modules))
                return code
            reason = "扩圈无新增测试" if len(merged) == len(test_paths) else "扩圈轮次用尽"
            print(f"[test-selection] {reason} ⇒ 退化工程级全量重跑（覆盖率缺口模块：{'、'.join(missing)}）")
            test_paths = ConcurrentStableList(test_selection.all_test_paths(backend))
            degraded = True
            full_retried = True
            continue

        expanded += 1
        print(
            f"[test-selection] 扩圈第 {expanded} 轮：补 {len(merged) - len(test_paths)} 个测试文件"
            f"（缺行模块 {len(missing)} 个）"
        )
        test_paths = ConcurrentStableList(merged)


if __name__ == "__main__":
    with contextlib.suppress(BrokenPipeError):
        sys.exit(main())
