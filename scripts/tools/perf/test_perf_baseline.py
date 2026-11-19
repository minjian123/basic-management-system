#!/usr/bin/env python3
"""全量耗时测量入口（13_08 T1）：分批耗时 / 最慢项 / 锁与写微基准。

用法（在 `bms` 仓根，必须用仓内 venv 的解释器）::

    backend\\.venv\\Scripts\\python.exe scripts\\tools\\perf\\test_perf_baseline.py all
    backend\\.venv\\Scripts\\python.exe scripts\\tools\\perf\\test_perf_baseline.py batch --coverage
    backend\\.venv\\Scripts\\python.exe scripts\\tools\\perf\\test_perf_baseline.py micro --micro-count 200
    backend\\.venv\\Scripts\\python.exe scripts\\tools\\perf\\test_perf_baseline.py slow --run-dir <运行目录>
    backend\\.venv\\Scripts\\python.exe scripts\\tools\\perf\\test_perf_baseline.py --self-test

口径（详细设计 §13）：

- 分批全量跑：显式 `.py` 文件清单、按字符预算 6000 分批、**批间串行**（守卫不拦、也不需要逃生开关）；
- 最慢项：随脚本的微型 pytest 插件按 setup / call / teardown 三段落 JSONL，与任务书 §2.2 同口径；
- 微基准：SQLite 文件库 + `NullPool`，六项各 N 次，出平均 / p50 / p95；
- 基线：`deploy/perf/test_perf_baseline.json`（入库、可 diff），只存本次实测，历史数字留在实施记录。

退出码：`0` 测量完成；`1` `--fail-over` 判定超阈值；`2` 参数 / 环境错误；`3` 批执行中断（超时等）。
"""

from __future__ import annotations

import argparse
import sys
import time
import tomllib
from pathlib import Path

_PERF_DIR = Path(__file__).resolve().parent
"""本目录（`scripts/tools/perf`）。"""

_REPO_ROOT = _PERF_DIR.parents[2]
"""默认仓库根（`bms/`）。"""

_BMS_CORE_SRC = _REPO_ROOT / "backend" / "libs" / "bms_core" / "src"
if str(_BMS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_BMS_CORE_SRC))
if str(_PERF_DIR) not in sys.path:
    sys.path.insert(0, str(_PERF_DIR))

import perf_baseline  # noqa: E402
import perf_micro  # noqa: E402
import perf_runner  # noqa: E402

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList  # noqa: E402
from bms_core.testing.paths import configure_project_root  # noqa: E402

DEFAULT_BASELINE = Path("deploy") / "perf" / "test_perf_baseline.json"
"""基线落点（相对仓库根）。"""

_SCHEMA_VERSION = 1
"""基线 schema 版本（字段增删时递增）。"""


def render_table(headers: ConcurrentStableList[str], rows: ConcurrentStableList[ConcurrentStableList[str]]) -> str:
    """渲染 markdown 表（终端与文档都直接可读，也不需要按中文宽度补空格）。

    Args:
        headers: 表头。
        rows: 数据行（每行列数须与表头一致）。

    Returns:
        str: markdown 表文本。
    """
    lines: ConcurrentStableList[str] = ConcurrentStableList()
    lines.add("| " + " | ".join(headers) + " |")
    lines.add("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.add("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def load_engine_config(repo_root: Path) -> tuple[ConcurrentStableList[str], ConcurrentStableList[str]]:
    """读 `engkit.toml` 的工程清单与覆盖率采集范围。

    Args:
        repo_root: 仓库根。

    Returns:
        tuple: （工程清单，覆盖率包清单）。

    Raises:
        SystemExit: 配置缺失或字段为空（退出码 2）。
    """
    path = repo_root / "engkit.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        print(f"[perf] 读取配置失败：{path}（{error}）", file=sys.stderr)
        raise SystemExit(2) from error
    backend = data.get("backend")
    if not isinstance(backend, dict):
        print(f"[perf] 配置缺少 [backend] 段：{path}", file=sys.stderr)
        raise SystemExit(2)
    projects = ConcurrentStableList(backend.get("projects", []))
    packages = ConcurrentStableList(backend.get("coverage_packages", []))
    if not projects:
        print(f"[perf] [backend].projects 为空：{path}", file=sys.stderr)
        raise SystemExit(2)
    return projects, packages


def latest_run_dir(backend: Path) -> Path | None:
    """最近一次运行目录（`<backend>/.cache/perf/<时间戳>`）。

    Args:
        backend: `backend/` 目录。

    Returns:
        Path | None: 最近目录；不存在时为 None。
    """
    root = backend / ".cache" / perf_runner.PERF_ROOT_NAME
    directories = [path for path in sorted(root.glob("*")) if path.is_dir() and path.name != "micro"]
    return directories[-1] if directories else None


def _batch_payload(report: perf_runner.BatchReport) -> ConcurrentStableDict[str, object]:
    """把分批结果转成基线 JSON 的 `batch` 段。

    Args:
        report: 分批结果。

    Returns:
        ConcurrentStableDict[str, object]: `batch` 段。
    """
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    payload.set("total_seconds", round(report.total_seconds, 3))
    payload.set("files", report.files)
    payload.set("batches", len(report.batches))
    payload.set("interrupted", report.interrupted)
    payload.set("coverage", report.covered_files)
    counts: ConcurrentStableDict[str, int] = ConcurrentStableDict()
    for key in ("passed", "failed", "error", "skipped"):
        counts.set(key, 0)
    items: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    for outcome in report.batches:
        for key in counts:
            counts.set(key, counts.get(key, 0) + outcome.counts.get(key, 0))
        item: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        item.set("index", outcome.index)
        item.set("files", outcome.files)
        item.set("seconds", round(outcome.seconds, 3))
        item.set("passed", outcome.counts.get("passed", 0))
        item.set("failed", outcome.counts.get("failed", 0) + outcome.counts.get("error", 0))
        item.set("skipped", outcome.counts.get("skipped", 0))
        item.set("exit_code", outcome.exit_code)
        item.set("timed_out", outcome.timed_out)
        item.set("log", outcome.log_name)
        items.add(item)
    payload.set("cases", counts)
    payload.set("items", items)
    return payload


def _micro_payload(
    results: ConcurrentStableList[perf_micro.MicroResult],
) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """把微基准结果转成基线 JSON 的 `micro` 段。

    Args:
        results: 六项结果。

    Returns:
        ConcurrentStableList[ConcurrentStableDict[str, object]]: `micro` 段。
    """
    payload: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    for result in results:
        item: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        item.set("key", result.key)
        item.set("label", result.label)
        item.set("count", result.count)
        item.set("avg_ms", result.avg_ms)
        item.set("p50_ms", result.p50_ms)
        item.set("p95_ms", result.p95_ms)
        payload.add(item)
    return payload


def _print_batch_table(report: perf_runner.BatchReport) -> None:
    """打印「分批耗时」表。

    Args:
        report: 分批结果。
    """
    headers: ConcurrentStableList[str] = ConcurrentStableList(
        ["批次", "文件数", "通过", "失败", "跳过", "耗时(s)", "占最慢批"]
    )
    rows: ConcurrentStableList[ConcurrentStableList[str]] = ConcurrentStableList()
    slowest = max((outcome.seconds for outcome in report.batches), default=0.0)
    passed = failed = skipped = 0
    for outcome in report.batches:
        passed += outcome.counts.get("passed", 0)
        failed += outcome.counts.get("failed", 0) + outcome.counts.get("error", 0)
        skipped += outcome.counts.get("skipped", 0)
        share = f"{outcome.seconds / slowest * 100:.0f}%" if slowest else "—"
        rows.add(
            ConcurrentStableList(
                [
                    str(outcome.index),
                    str(outcome.files),
                    str(outcome.counts.get("passed", 0)),
                    str(outcome.counts.get("failed", 0) + outcome.counts.get("error", 0)),
                    str(outcome.counts.get("skipped", 0)),
                    f"{outcome.seconds:.1f}",
                    share + ("（超时）" if outcome.timed_out else ""),
                ]
            )
        )
    rows.add(
        ConcurrentStableList(
            ["合计", str(report.files), str(passed), str(failed), str(skipped), f"{report.total_seconds:.1f}", "—"]
        )
    )
    print("\n### 分批耗时（每批含一次会话建库的固定成本）\n")
    print(render_table(headers, rows))


def _print_slow_table(report: perf_runner.SlowReport) -> None:
    """打印「最慢 N 项」表。

    Args:
        report: 最慢项汇总。
    """
    headers: ConcurrentStableList[str] = ConcurrentStableList(["用例", "阶段", "耗时(s)", "结果"])
    rows: ConcurrentStableList[ConcurrentStableList[str]] = ConcurrentStableList()
    for hit in report.hits:
        rows.add(ConcurrentStableList([hit.test, hit.phase, f"{hit.seconds:.2f}", hit.outcome]))
    print("\n### 最慢项（按阶段计，setup / call / teardown 各算一条）\n")
    print(render_table(headers, rows))
    totals = " / ".join(f"{phase} {report.totals.get(phase, 0.0):.1f}s" for phase in perf_runner.PHASES)
    print(f"\n阶段合计：{totals}；单段 ≥1s 共 {report.over_one_second} 段；统计用例 {report.cases} 条")


def _print_micro_table(results: ConcurrentStableList[perf_micro.MicroResult]) -> None:
    """打印「锁与写微基准」表。

    Args:
        results: 六项结果。
    """
    headers: ConcurrentStableList[str] = ConcurrentStableList(["项目", "次数", "平均(ms)", "p50(ms)", "p95(ms)"])
    rows: ConcurrentStableList[ConcurrentStableList[str]] = ConcurrentStableList()
    for result in results:
        rows.add(
            ConcurrentStableList(
                [
                    result.label,
                    str(result.count),
                    f"{result.avg_ms:.3f}",
                    f"{result.p50_ms:.3f}",
                    f"{result.p95_ms:.3f}",
                ]
            )
        )
    print("\n### 锁与写微基准（SQLite 文件库 + NullPool）\n")
    print(render_table(headers, rows))


def _print_comparison(rows: ConcurrentStableList[perf_baseline.MetricRow], baseline_path: Path) -> float:
    """打印与基线的对比表，返回最大涨幅（百分比）。

    Args:
        rows: 指标对比行。
        baseline_path: 基线文件路径（仅用于标题）。

    Returns:
        float: 最大涨幅（无基线可比时为 0）。
    """
    table_rows: ConcurrentStableList[ConcurrentStableList[str]] = ConcurrentStableList()
    worst = 0.0
    for row in rows:
        current = "—" if row.current is None else f"{row.current:.3f}"
        base = "—" if row.baseline is None else f"{row.baseline:.3f}"
        delta = "—" if row.delta_pct is None else f"{row.delta_pct:+.1f}%"
        if row.delta_pct is not None:
            worst = max(worst, row.delta_pct)
        table_rows.add(ConcurrentStableList([row.name, current, base, delta]))
    headers: ConcurrentStableList[str] = ConcurrentStableList(["指标", "本次", "基线", "增减"])
    print(f"\n### 与基线对比（{baseline_path.as_posix()}）\n")
    print(render_table(headers, table_rows))
    return worst


def run_self_test() -> int:
    """纯函数自测（不启动 pytest、不碰锁与数据库）。

    Returns:
        int: 0 全部通过；1 有失败。
    """
    checks: ConcurrentStableList[str] = ConcurrentStableList()

    def check(name: str, condition: bool) -> None:
        if not condition:
            checks.add(name)

    batches = perf_runner.pack_paths(ConcurrentStableList([]), 100)
    check("空清单不分批", len(batches) == 0)
    batches = perf_runner.pack_paths(ConcurrentStableList(["a.py"]), 100)
    check("单文件一批", len(batches) == 1 and list(batches[0]) == ["a.py"])
    batches = perf_runner.pack_paths(ConcurrentStableList(["a" * 10 + ".py", "b" * 10 + ".py"]), 12)
    check("超预算切两批", len(batches) == 2)
    batches = perf_runner.pack_paths(ConcurrentStableList(["a.py", "b.py", "c.py"]), 1000)
    check("预算足够保序", [item for batch in batches for item in batch] == ["a.py", "b.py", "c.py"])

    counts = perf_runner.parse_counts("1556 passed, 9 failed, 12 skipped in 15.00s")
    check("摘要解析", counts.get("passed") == 1556 and counts.get("failed") == 9 and counts.get("skipped") == 12)
    counts = perf_runner.parse_counts("no tests ran in 3.41s")
    check("空摘要归零", counts.get("passed") == 0 and counts.get("failed") == 0)

    samples = ConcurrentStableList([float(index) for index in range(1, 101)])
    check("p50 最近秩", perf_micro.percentile(samples, 0.50) == 50.0)
    check("p95 最近秩", perf_micro.percentile(samples, 0.95) == 95.0)
    check("单样本分位", perf_micro.percentile(ConcurrentStableList([2.0]), 0.95) == 2.0)

    current: ConcurrentStableDict[str, float] = ConcurrentStableDict()
    current.set("全量耗时(s)", 110.0)
    current.set("新增指标", 1.0)
    base: ConcurrentStableDict[str, float] = ConcurrentStableDict()
    base.set("全量耗时(s)", 100.0)
    base.set("消失指标", 2.0)
    rows = perf_baseline.compare_metrics(current, base)
    by_name = {row.name: row for row in rows}
    check("对比：涨幅", by_name["全量耗时(s)"].delta_pct == 10.0)
    check("对比：新增项无基线", by_name["新增指标"].baseline is None and by_name["新增指标"].delta_pct is None)
    check("对比：基线独有项保留", "消失指标" in by_name)
    zero_base: ConcurrentStableDict[str, float] = ConcurrentStableDict()
    zero_base.set("全量耗时(s)", 0.0)
    rows = perf_baseline.compare_metrics(current, zero_base)
    check("对比：零基线不出百分比", rows[0].delta_pct is None)

    headers: ConcurrentStableList[str] = ConcurrentStableList(["a", "b"])
    body: ConcurrentStableList[ConcurrentStableList[str]] = ConcurrentStableList([ConcurrentStableList(["1", "2"])])
    table = render_table(headers, body)
    check("表格列数一致", all(line.count("|") == 3 for line in table.splitlines()))

    fingerprint = perf_baseline.environment_fingerprint(_REPO_ROOT)
    check("环境指纹齐全", all(key in fingerprint for key in ("cpu", "logical_cores", "os", "python", "commit")))

    if checks:
        print("[自测] 失败：" + "、".join(checks))
        return 1
    print("[自测] 通过：12 项（分批切分 / 摘要解析 / 分位统计 / 基线对比 / 表格渲染 / 环境指纹）")
    return 0


def _run_command(args: argparse.Namespace, repo_root: Path) -> int:
    """执行子命令。

    Args:
        args: 命令行参数。
        repo_root: 仓库根。

    Returns:
        int: 退出码。
    """
    backend = repo_root / "backend"
    baseline_path = Path(args.baseline) if args.baseline else repo_root / DEFAULT_BASELINE
    projects, packages = load_engine_config(repo_root)
    configure_project_root(str(backend))

    report: perf_runner.BatchReport | None = None
    slow: perf_runner.SlowReport | None = None
    micro: ConcurrentStableList[perf_micro.MicroResult] = ConcurrentStableList()
    run_dir: Path | None = None
    if args.run_dir:
        run_dir = Path(args.run_dir)
        run_dir = run_dir if run_dir.is_absolute() else repo_root / run_dir
    base_payload = None
    if not args.no_compare and baseline_path.is_file():
        base_payload = perf_baseline.load_payload(baseline_path)

    try:
        with perf_runner.session_lock(backend):
            # 微基准先跑：全量跑完机器处在 IO / CPU 高位，微基准会被拖慢约 1.7 倍（实测），
            # 放在前面才与任务书 §2.3 的空闲机口径可比。
            if args.command in ("all", "micro"):
                print(f"[perf] 微基准：六项，各 {args.micro_count} 次")
                micro = perf_micro.run_micro_sync(backend, args.micro_count)
            if args.command in ("all", "batch"):
                run_dir = perf_runner.perf_root(backend) / time.strftime("%Y%m%d-%H%M%S")
                print(f"[perf] 运行目录：{run_dir}")
                report = perf_runner.run_batches(
                    repo_root=repo_root,
                    backend=backend,
                    project_list=projects,
                    source_modules=packages,
                    run_dir=run_dir,
                    budget=args.batch_budget,
                    jobs=args.jobs,
                    coverage=args.coverage,
                    timeout=args.timeout,
                )
            if args.command == "slow":
                if run_dir is None:
                    run_dir = latest_run_dir(backend)
                if run_dir is None or not run_dir.is_dir():
                    print("[perf] 未找到运行目录：请先跑一次 batch，或用 --run-dir 指定", file=sys.stderr)
                    return 2
    except TimeoutError:
        print("[perf] 已有测量会话在跑（.cache/perf/session.lock）；同一时刻只允许一个", file=sys.stderr)
        return 2

    if report is not None:
        _print_batch_table(report)
        if report.interrupted:
            print("\n[perf] 批执行中断（超时），以下为该批「已开始未结束」的用例：")
            if run_dir is not None:
                for test in perf_runner.collect_phases(run_dir)[2]:
                    print(f"  - {test}")
    if run_dir is not None and args.command in ("all", "batch", "slow"):
        hits, finished, _hanging = perf_runner.collect_phases(run_dir)
        slow = perf_runner.summarize_phases(hits, finished, args.top)
        _print_slow_table(slow)
    if micro:
        _print_micro_table(micro)

    payload: ConcurrentStableDict[str, object] | None = None
    if report is not None or micro:
        payload = ConcurrentStableDict()
        payload.set("schema_version", _SCHEMA_VERSION)
        payload.set("generated_at", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        payload.set("environment", perf_baseline.environment_fingerprint(repo_root))
        params: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        params.set("jobs", args.jobs)
        params.set("coverage", bool(args.coverage))
        params.set("batch_budget", args.batch_budget)
        params.set("timeout", args.timeout)
        params.set("slowest", args.top)
        params.set("micro_count", args.micro_count)
        payload.set("params", params)
        if report is not None:
            payload.set("batch", _batch_payload(report))
        if slow is not None:
            slow_items: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
            for hit in slow.hits:
                item: ConcurrentStableDict[str, object] = ConcurrentStableDict()
                item.set("test", hit.test)
                item.set("phase", hit.phase)
                item.set("seconds", round(hit.seconds, 3))
                item.set("outcome", hit.outcome)
                slow_items.add(item)
            payload.set("slowest", slow_items)
            totals: ConcurrentStableDict[str, float] = ConcurrentStableDict()
            for phase in perf_runner.PHASES:
                totals.set(phase, round(slow.totals.get(phase, 0.0), 3))
            payload.set("phase_totals", totals)
            stats: ConcurrentStableDict[str, object] = ConcurrentStableDict()
            stats.set("over_one_second", slow.over_one_second)
            stats.set("cases", slow.cases)
            payload.set("slowest_stats", stats)
        if micro:
            payload.set("micro", _micro_payload(micro))

    if args.save:
        if payload is None or report is None or not micro:
            print("[perf] --save 需要同时具备分批与微基准结果（请用 all）", file=sys.stderr)
            return 2
        perf_baseline.save_payload(payload, baseline_path)
        print(f"\n[perf] 基线已写入：{baseline_path}")

    exit_code = 3 if report is not None and report.interrupted else 0
    if payload is not None and base_payload is not None:
        rows = perf_baseline.compare_metrics(
            perf_baseline.collect_metrics(payload), perf_baseline.collect_metrics(base_payload)
        )
        worst = _print_comparison(rows, baseline_path)
        if args.fail_over is not None and worst > args.fail_over:
            print(f"\n[perf] 超过阈值：最大涨幅 {worst:.1f}% > {args.fail_over:.1f}%")
            exit_code = 1

    if args.coverage:
        print("\n[perf] 覆盖率数据已按 engkit 采集插件落 .cache/coverage/；查缺口用 coverage_report.py（勿手工采集）")
    return exit_code


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """命令行入口。

    Args:
        argv: 参数（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码。
    """
    parser = argparse.ArgumentParser(description="全量耗时测量：分批耗时 / 最慢项 / 锁与写微基准")
    parser.add_argument("command", nargs="?", default="all", choices=("all", "batch", "slow", "micro"))
    parser.add_argument("--root", default="", help="仓库根（缺省由脚本位置推出）")
    parser.add_argument("--jobs", default="auto", help="并行档位：auto / off / 正整数")
    parser.add_argument("--coverage", action="store_true", help="按 engkit 采集插件采覆盖率（不用 --cov）")
    parser.add_argument("--batch-budget", type=int, default=perf_runner.DEFAULT_BATCH_BUDGET)
    parser.add_argument("--timeout", type=float, default=None, help="单批超时秒数（超时杀进程树）")
    parser.add_argument("--top", type=int, default=20, help="最慢项条数")
    parser.add_argument("--micro-count", type=int, default=perf_micro.DEFAULT_COUNT)
    parser.add_argument("--baseline", default="", help="基线文件（缺省 deploy/perf/test_perf_baseline.json）")
    parser.add_argument("--no-compare", action="store_true", help="不与基线对比")
    parser.add_argument("--fail-over", type=float, default=None, help="任一指标涨幅超该百分比即返回 1")
    parser.add_argument("--save", action="store_true", help="把本次结果写入基线（需 all）")
    parser.add_argument("--run-dir", default="", help="指定运行目录（slow 复算用）")
    parser.add_argument("--self-test", action="store_true", help="只跑纯函数自测")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    repo_root = Path(args.root).resolve() if args.root else _REPO_ROOT
    if not (repo_root / "backend").is_dir():
        print(f"[perf] 不是 bms 仓库根：{repo_root}", file=sys.stderr)
        return 2
    if args.jobs not in ("auto", "off") and not args.jobs.isdigit():
        print(f"[perf] --jobs 只接受 auto / off / 正整数：{args.jobs}", file=sys.stderr)
        return 2
    if args.batch_budget <= 0 or args.top <= 0 or args.micro_count <= 0:
        print("[perf] --batch-budget / --top / --micro-count 必须为正数", file=sys.stderr)
        return 2
    return _run_command(args, repo_root)


if __name__ == "__main__":
    sys.exit(main())
