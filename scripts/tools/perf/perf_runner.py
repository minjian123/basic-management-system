#!/usr/bin/env python3
"""分批全量跑（13_08 T1）：发现测试文件 → 按字符预算分批 → 逐批起独立 pytest 会话 → 汇总。

口径见详细设计 §13.2，四条要点：

1. **显式文件清单**：每批把该批全部 `.py` 文件逐个作为位置参数。重命令守卫（位置参数全为
   `.py` / `::节点` 即放行）与全量测试守卫（`.py` 目标不算全量）都不会拦，因此本模块**不需要、
   也不得设置** `ENGKIT_ALLOW_UNWRAPPED` 之类的逃生开关。
2. **批间串行**：`pytest_configure` 在非 xdist controller 上会清空共享测试库，两个会话并发会互相
   删库（实施记录 §3 已实测「大面积 no such table」），所以必须一批跑完再起下一批。
3. **每批完整输出落盘**：`batch-NN.log`，终端只读摘要——否则几万行输出会把摘要与失败明细一起淹没。
4. **超时杀进程树**：xdist worker 是 controller 的子进程，只杀 controller 会留下占门进程（下一轮
   直接等门超时），故 Windows 用 `taskkill /F /T`、POSIX 用进程组 `SIGKILL`。
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.testing import rwlock

PERF_ROOT_NAME = "perf"
"""测量产物根目录名（`<backend>/.cache/perf`）。

**不能放 `.cache/test`**：共享测试库清理会按「无后缀即目录」递归删除 `.cache/test` 下的条目，
实测一次分批跑就把运行目录（含批日志与阶段记录）整批删掉，只活下最后一批。
"""

DEFAULT_BATCH_BUDGET = 6000
"""单批路径参数字符预算（与 `engkit.preflight.pack_paths` 的 6000 同值，口径一致才可比）。"""

PHASES = ("setup", "call", "teardown")
"""阶段名的固定顺序（历史口径：最慢项按阶段计）。"""

_COUNT_PATTERN = re.compile(r"(\d+) (passed|failed|error|errors|skipped|deselected|xfailed|xpassed|warning|warnings)")
"""pytest 摘要计数（`-q` 末行的 `12 passed, 3 failed in 1.2s`）。"""

_CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
"""POSIX 上不存在该常量；Windows 用它让 `taskkill /T` 能识别进程树。"""


@dataclass(frozen=True)
class BatchOutcome:
    """单批执行结果。

    Attributes:
        index: 批次序号（1 起）。
        files: 该批测试文件数。
        seconds: 该批墙钟耗时（含会话固定成本，见详细设计 §13.2）。
        counts: pytest 摘要计数（`passed` / `failed` / `skipped` 等）。
        exit_code: 退出码；超时为 -1。
        timed_out: 是否超时被杀。
        log_name: 该批日志文件名（相对运行目录）。
    """

    index: int
    files: int
    seconds: float
    counts: ConcurrentStableDict[str, int]
    exit_code: int
    timed_out: bool
    log_name: str


@dataclass(frozen=True)
class BatchReport:
    """一次「分批全量跑」的整体结果。

    Attributes:
        files: 测试文件总数。
        batches: 逐批结果。
        total_seconds: 全部分批的墙钟总耗时。
        interrupted: 是否因超时中止（中止后不再起后续批次）。
        covered_files: 覆盖率采集开关的状态（用于摘要标注）。
    """

    files: int
    batches: ConcurrentStableList[BatchOutcome]
    total_seconds: float
    interrupted: bool
    covered_files: bool


@dataclass(frozen=True)
class PhaseHit:
    """一条「用例 + 阶段」耗时记录。

    Attributes:
        test: 用例节点 ID。
        phase: `setup` / `call` / `teardown`。
        seconds: 该阶段耗时。
        outcome: `passed` / `failed` / `skipped`。
    """

    test: str
    phase: str
    seconds: float
    outcome: str


@dataclass(frozen=True)
class SlowReport:
    """最慢项汇总。

    Attributes:
        hits: 最慢 N 项（按耗时降序）。
        totals: 各阶段耗时合计。
        over_one_second: 单段耗时 ≥1s 的条数（历史口径对照指标）。
        cases: 参与统计的用例数。
    """

    hits: ConcurrentStableList[PhaseHit]
    totals: ConcurrentStableDict[str, float] = field(default_factory=ConcurrentStableDict)
    over_one_second: int = 0
    cases: int = 0


def find_test_files(backend: Path, projects: ConcurrentStableList[str]) -> ConcurrentStableList[str]:
    """按工程清单发现测试文件（`<工程>/tests/**/test_*.py`）。

    Args:
        backend: `backend/` 目录。
        projects: 相对 `backend/` 的工程目录清单（来自 `engkit.toml` 的 `[backend].projects`）。

    Returns:
        ConcurrentStableList[str]: 相对 `backend/` 的 POSIX 路径（按工程声明序 + 路径字典序）。
    """
    found: ConcurrentStableList[str] = ConcurrentStableList()
    for project in projects:
        tests_dir = backend / project / "tests"
        if not tests_dir.is_dir():
            continue
        for path in sorted(tests_dir.rglob("test_*.py")):
            found.add(path.relative_to(backend).as_posix())
    return found


def pack_paths(
    paths: ConcurrentStableList[str], budget: int = DEFAULT_BATCH_BUDGET
) -> ConcurrentStableList[ConcurrentStableList[str]]:
    """按字符预算把测试文件切成批（贪婪装箱，保序）。

    Args:
        paths: 测试文件路径。
        budget: 单批路径参数字符预算（含空白开销）。

    Returns:
        ConcurrentStableList[ConcurrentStableList[str]]: 分批结果（空输入返回空列表）。
    """
    batches: ConcurrentStableList[ConcurrentStableList[str]] = ConcurrentStableList()
    current: ConcurrentStableList[str] = ConcurrentStableList()
    size = 0
    for path in paths:
        cost = len(path) + 1
        if current and size + cost > budget:
            batches.add(current)
            current = ConcurrentStableList()
            size = 0
        current.add(path)
        size += cost
    if current:
        batches.add(current)
    return batches


def invalid_targets(paths: ConcurrentStableList[str], backend: Path) -> ConcurrentStableList[str]:
    """校验每个目标都是存在且以 `.py` 结尾的文件（守卫合规的前置断言）。

    Args:
        paths: 相对 `backend/` 的测试文件路径。
        backend: `backend/` 目录。

    Returns:
        ConcurrentStableList[str]: 不合规的目标（空列表表示全部合规）。
    """
    offenders: ConcurrentStableList[str] = ConcurrentStableList()
    for path in paths:
        if not path.endswith(".py") or not (backend / path).is_file():
            offenders.add(path)
    return offenders


def build_pytest_argv(batch: ConcurrentStableList[str], *, jobs: str) -> ConcurrentStableList[str]:
    """构造单批 pytest 命令（显式 `.py` 清单 + 阶段计时插件 + 可选并行档位）。

    Args:
        batch: 该批测试文件（相对 `backend/`）。
        jobs: `auto`（沿用 addopts 的 `-n auto`）/ `off`（`-p no:xdist`）/ 正整数。

    Returns:
        ConcurrentStableList[str]: 完整命令（解释器 + `-m pytest` + 目标）。
    """
    argv: ConcurrentStableList[str] = ConcurrentStableList(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-rf",
            # 钉死配置与根目录：只传单工程文件时 pytest 会把 rootdir 落到该工程（如 libs/bms_core），
            # 插件集与 addopts 随之换成本工程配置（守卫 / 测试基座 / 夹具口径全变），批次之间不可比。
            "-c",
            "pyproject.toml",
            "--rootdir",
            ".",
            "-p",
            "perf_phase_timer",
        ]
    )
    argv.extend(batch)
    if jobs == "off":
        # `-n 0` 关闭 xdist 子进程；不能用 `-p no:xdist`——addopts 里的 `-n auto` 会变成未知参数。
        argv.extend(["-n", "0"])
    elif jobs != "auto":
        argv.extend(["-n", jobs])
    return argv


def parse_counts(text: str) -> ConcurrentStableDict[str, int]:
    """解析 pytest 摘要计数（只看末行 `12 passed, 3 failed in 1.2s`）。

    Args:
        text: pytest 输出（整段日志，只取最后一个匹配行）。

    Returns:
        ConcurrentStableDict[str, int]: 计数（缺省为 0）。
    """
    counts: ConcurrentStableDict[str, int] = ConcurrentStableDict()
    for key in ("passed", "failed", "error", "errors", "skipped", "deselected", "xfailed", "xpassed"):
        counts.set(key, 0)
    tail = ""
    for line in reversed(text.splitlines()):
        if " in " in line and ("passed" in line or "failed" in line or "error" in line or "skipped" in line):
            tail = line
            break
    for matched in _COUNT_PATTERN.finditer(tail):
        key = matched.group(2)
        if key == "errors":
            key = "error"
        elif key == "warnings":
            key = "warning"
        counts.set(key, counts.get(key, 0) + int(matched.group(1)))
    return counts


def _kill_tree(pid: int) -> None:
    """杀掉整个进程树（controller 与其 xdist worker）。

    Args:
        pid: 子进程（controller）进程号。
    """
    if os.name == "nt":  # Windows 分支
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)
        return
    with contextlib.suppress(ProcessLookupError, PermissionError):  # POSIX 分支（本地开发机不可达）
        os.killpg(os.getpgid(pid), signal.SIGKILL)


def _batch_env(
    run_dir: Path, *, coverage: bool, source_modules: ConcurrentStableList[str], repo_root: Path
) -> dict[str, str]:  # bare-collections:allow - subprocess 的 env 参数按内置 dict[str, str] 组装
    """构造单批子进程环境。

    Args:
        run_dir: 本次运行目录（阶段记录落这里）。
        coverage: 是否启用覆盖率采集。
        source_modules: 覆盖率采集范围（`[backend].coverage_packages`）。
        repo_root: 仓库根（覆盖率数据落 `<仓根>/.cache/coverage/`）。

    Returns:
        dict[str, str]: 子进程环境变量。
    """
    env = dict(os.environ)
    env["BMS_TEST_PERF_PHASE_DIR"] = str(run_dir)
    perf_dir = str(Path(__file__).resolve().parent)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [perf_dir, env.get("PYTHONPATH", "")]))
    if coverage:
        data_file = (repo_root / ".cache" / "coverage" / ".coverage").resolve()
        env["BMS_COVERAGE_DATA"] = str(data_file)
        env["BMS_COVERAGE_SOURCE"] = ",".join(sorted({module.split(".", 1)[0] for module in source_modules}))
        env.pop("COVERAGE_FILE", None)
    else:
        # 本地可能正处在预检里（父进程带着采集变量）：残留会让 `coverage_guard` 判「换落点」直接 exit(2)。
        env.pop("BMS_COVERAGE_DATA", None)
        env.pop("BMS_COVERAGE_SOURCE", None)
        env.pop("COVERAGE_FILE", None)
    return env


def perf_root(backend: Path) -> Path:
    """测量产物根目录（`<backend>/.cache/perf`）。

    Args:
        backend: `backend/` 目录。

    Returns:
        Path: 已创建的根目录。
    """
    directory = backend / ".cache" / PERF_ROOT_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _lock_pid(path: Path) -> int | None:
    """读会话锁里的进程号。

    Args:
        path: 锁文件。

    Returns:
        int | None: 进程号；读不出时为 None。
    """
    try:
        return int(path.read_text(encoding="utf-8").strip() or "0") or None
    except OSError, ValueError:
        return None


@contextlib.contextmanager
def session_lock(backend: Path) -> Iterator[None]:
    """会话级互斥：同一时刻只允许一个测量会话（两轮并发会互相删共享测试库）。

    锁文件放 `.cache/perf/`（**不能放 `.cache/test`**：测试会话启动会删掉那里的普通 `.lock`）。

    Args:
        backend: `backend/` 目录。

    Yields:
        None: 持锁区间。

    Raises:
        TimeoutError: 已有会话在跑（持有进程仍存活）。
    """
    path = perf_root(backend) / "session.lock"
    handle: int | None = None
    for _attempt in range(2):
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            pid = _lock_pid(path)
            if pid is not None and rwlock._pid_alive(pid):
                raise TimeoutError(f"测量会话互斥：{path}（进程 {pid} 仍在运行）") from None
            with contextlib.suppress(OSError):
                path.unlink()
    if handle is None:
        raise TimeoutError(f"测量会话互斥：{path}")
    with os.fdopen(handle, "w", encoding="utf-8") as file:
        file.write(str(os.getpid()))
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            path.unlink()


def run_batches(
    *,
    repo_root: Path,
    backend: Path,
    project_list: ConcurrentStableList[str],
    source_modules: ConcurrentStableList[str],
    run_dir: Path,
    budget: int = DEFAULT_BATCH_BUDGET,
    jobs: str = "auto",
    coverage: bool = False,
    timeout: float | None = None,
) -> BatchReport:
    """跑完所有批次（串行），返回逐批结果。

    Args:
        repo_root: 仓库根。
        backend: `backend/` 目录（pytest 工作目录）。
        project_list: 工程清单（`[backend].projects`）。
        source_modules: 覆盖率采集范围（`[backend].coverage_packages`）。
        run_dir: 本次运行目录。
        budget: 单批字符预算。
        jobs: 并行档位（`auto` / `off` / 正整数）。
        coverage: 是否启用覆盖率采集（走 engkit 采集插件，不用 `--cov`）。
        timeout: 单批超时（秒）；`None` 表示不限制。

    Returns:
        BatchReport: 整体结果。

    Raises:
        RuntimeError: 目标清单不合规（非 `.py` 或文件不存在）——守卫合规的前置断言。
    """
    files = find_test_files(backend, project_list)
    offenders = invalid_targets(files, backend)
    if offenders:
        raise RuntimeError(f"分批目标不合规（必须是存在的 .py 文件）：{list(offenders)[:5]}")
    batches = pack_paths(files, budget)
    run_dir.mkdir(parents=True, exist_ok=True)
    env = _batch_env(run_dir, coverage=coverage, source_modules=source_modules, repo_root=repo_root)
    outcomes: ConcurrentStableList[BatchOutcome] = ConcurrentStableList()
    started = time.perf_counter()
    interrupted = False
    for index, batch in enumerate(batches, start=1):
        argv = build_pytest_argv(batch, jobs=jobs)
        log_name = f"batch-{index:02d}.log"
        log_path = run_dir / log_name
        batch_started = time.perf_counter()
        timed_out = False
        with log_path.open("w", encoding="utf-8", errors="replace") as handle:
            process = subprocess.Popen(
                list(argv),
                cwd=str(backend),
                env=env,
                stdout=handle,
                stderr=subprocess.STDOUT,
                creationflags=_CREATE_NEW_PROCESS_GROUP,
                start_new_session=os.name != "nt",
            )
            try:
                exit_code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                exit_code = -1
                _kill_tree(process.pid)
                process.wait(timeout=30)
        elapsed = time.perf_counter() - batch_started
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        counts = parse_counts(log_text)
        outcomes.add(
            BatchOutcome(
                index=index,
                files=len(batch),
                seconds=elapsed,
                counts=counts,
                exit_code=exit_code,
                timed_out=timed_out,
                log_name=log_name,
            )
        )
        print(
            f"[批次 {index}/{len(batches)}] {len(batch)} 个文件，{elapsed:.1f}s，"
            f"通过 {counts.get('passed', 0)} / 失败 {counts.get('failed', 0) + counts.get('error', 0)}"
            + ("，超时中止" if timed_out else ""),
            flush=True,
        )
        if timed_out:
            interrupted = True
            break
    return BatchReport(
        files=len(files),
        batches=outcomes,
        total_seconds=time.perf_counter() - started,
        interrupted=interrupted,
        covered_files=coverage,
    )


def _phase_files(run_dir: Path) -> ConcurrentStableList[Path]:
    """运行目录下的阶段记录文件。

    Args:
        run_dir: 本次运行目录。

    Returns:
        ConcurrentStableList[Path]: `phase-*.jsonl`（按文件名排序）。
    """
    found: ConcurrentStableList[Path] = ConcurrentStableList()
    for path in sorted(run_dir.glob("phase-*.jsonl")):
        found.add(path)
    return found


def collect_phases(
    run_dir: Path,
) -> tuple[ConcurrentStableList[PhaseHit], ConcurrentStableList[str], ConcurrentStableList[str]]:
    """读取阶段记录，返回「阶段命中 / 已完成用例 / 已开始未结束用例」。

    Args:
        run_dir: 本次运行目录。

    Returns:
        tuple: （阶段记录，已完成用例 nodeid，卡住候选 nodeid）。
    """
    hits: ConcurrentStableList[PhaseHit] = ConcurrentStableList()
    finished: ConcurrentStableList[str] = ConcurrentStableList()
    started: ConcurrentStableList[str] = ConcurrentStableList()
    finished_seen: ConcurrentStableDict[str, int] = ConcurrentStableDict()
    started_seen: ConcurrentStableDict[str, int] = ConcurrentStableDict()
    for path in _phase_files(run_dir):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            test = str(record.get("test", ""))
            if not test:
                continue
            if record.get("event") == "start":
                if test not in started_seen:
                    started_seen.set(test, 1)
                    started.add(test)
                continue
            if record.get("event") != "phase":
                continue
            hits.add(
                PhaseHit(
                    test=test,
                    phase=str(record.get("phase", "")),
                    seconds=float(record.get("duration", 0.0)),
                    outcome=str(record.get("outcome", "")),
                )
            )
            if record.get("phase") == "teardown" and test not in finished_seen:
                finished_seen.set(test, 1)
                finished.add(test)
    hanging: ConcurrentStableList[str] = ConcurrentStableList()
    for test in started:
        if test not in finished_seen:
            hanging.add(test)
    return hits, finished, hanging


def summarize_phases(
    hits: ConcurrentStableList[PhaseHit],
    finished: ConcurrentStableList[str],
    top: int = 20,
) -> SlowReport:
    """聚合最慢项与各阶段合计。

    Args:
        hits: 阶段记录（`collect_phases` 的返回）。
        finished: 已完成用例的 nodeid。
        top: 最慢项条数。

    Returns:
        SlowReport: 最慢项汇总。
    """
    totals: ConcurrentStableDict[str, float] = ConcurrentStableDict()
    for phase in PHASES:
        totals.set(phase, 0.0)
    over_one = 0
    for hit in hits:
        totals.set(hit.phase, totals.get(hit.phase, 0.0) + hit.seconds)
        if hit.seconds >= 1.0:
            over_one += 1
    ordered = sorted(hits, key=lambda item: item.seconds, reverse=True)
    picked: ConcurrentStableList[PhaseHit] = ConcurrentStableList()
    for hit in ordered[: max(0, top)]:
        picked.add(hit)
    return SlowReport(hits=picked, totals=totals, over_one_second=over_one, cases=len(finished))
