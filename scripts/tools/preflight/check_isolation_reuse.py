"""隔离自检：同一批用例**复用同一份共享库**连跑两轮，第二轮不得出现新失败。

为什么需要：共享库默认「会话开始删库重建」，依赖空库 / 固定主键 / 整表口径的用例会被删库掩盖——
单轮永远是绿的，直到有人把库复用起来才成片变红（实测末批复用第二轮 21 条失败，典型
`UNIQUE constraint failed: sys_session.id`）。本脚本把那一步固化成可重复的判定：

1. 第 1 轮：本次运行的首次会话（数据初始化之前删库重建，拿到干净基线）；
2. 第 2 轮：**同一次运行**的第二个会话（两轮共用一个 `BMS_TEST_RUN_ID`，叠加复用同一份库）；
3. 判定：第 2 轮的失败集合必须为空——非空即「用例动了别人的数据 / 依赖空库 / 用了固定键」。

用法：
    python scripts/tools/preflight/check_isolation_reuse.py path/a.py path/b.py
    git diff --name-only | python scripts/tools/preflight/check_isolation_reuse.py --files-from -

判据只认 `FAILED` / `ERROR` 行，不解析耗时；两轮都失败且集合相同时仍然判失败（功能缺陷先修）。
文件清单按字符预算拆成多条 pytest 命令在**同一轮内顺序执行**（同一次运行的多个会话，
仍只有第一个会话删库建库），以避开 Windows 命令行长度上限（全仓 845 文件实测 `WinError 206`）。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
"""仓根（本文件位于 `<仓根>/scripts/tools/preflight/`）。"""

_BACKEND = _REPO_ROOT / "backend"
"""pytest 工作目录。"""

_RESULT_RE = re.compile(r"^(?:FAILED|ERROR) (?P<nodeid>[^\s]+)", re.MULTILINE)
"""失败 / 错误行（`-rf` 的短摘要）。"""

_SUMMARY_RE = re.compile(r"\d+ (?:passed|failed|errors?)\b")
"""末行汇总的识别标记（**必须带计数**：日志里的 `worker_id_heartbeat_failed` 之类不算汇总）。"""

_ARGV_BUDGET = 6000
"""单条 pytest 命令的路径字符预算。

全仓 845 个测试文件拼进一条命令会超 Windows 命令行上限（实测 `WinError 206`），故同一轮内
按预算拆成多条 pytest 会话**顺序**执行：它们共用同一个 `BMS_TEST_RUN_ID`，即「同一次运行的
多个会话」——只有本轮第一个会话删库建库，其余会话叠加复用（与推送环分批同口径）。
"""

_LOG_DIR = _REPO_ROOT / ".cache" / "preflight"
"""逐批完整输出落点（排障只看这些文件，不靠终端截断）。"""


def _write_batch_log(run_id: str, label: str, index: int, output: str) -> Path:
    """把单批 pytest 完整输出落盘（stdout + stderr）。

    Args:
        run_id: 运行标识（文件名组成部分，便于把两轮归到同一次运行）。
        label: 轮次标签（`r1` / `r2`）。
        index: 批序号（从 1 起）。
        output: pytest 完整输出。

    Returns:
        Path: 日志文件路径。
    """
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = _LOG_DIR / f"isolation-{run_id}-{label}-b{index}.log"
    path.write_text(output, encoding="utf-8", newline="\n")
    return path


def _split_batches(  # bare-collections:allow（脚本内临时列表，不引 bms_core）
    files: list[str], budget: int = _ARGV_BUDGET
) -> list[list[str]]:  # bare-collections:allow（同上）
    """按字符预算把文件清单拆成多条命令（保序、不丢项）。

    Args:
        files: 测试文件（相对 backend）。
        budget: 单批字符预算（含分隔空格）。

    Returns:
        list[list[str]]: 分批结果；空清单返回空列表。
    """
    batches: list[list[str]] = []  # bare-collections:allow（同上）
    current: list[str] = []  # bare-collections:allow（同上）
    size = 0
    for item in files:
        cost = len(item) + 1
        if current and size + cost > budget:
            batches.append(current)
            current = []
            size = 0
        current.append(item)
        size += cost
    if current:
        batches.append(current)
    return batches


def _run_round(  # bare-collections:allow（本脚本只依赖标准库，不引 bms_core 并发集合）
    files: list[str], *, run_id: str, label: str, extra: list[str]
) -> tuple[int, str]:
    """跑一轮 pytest（两轮共用同一 `BMS_TEST_RUN_ID`）。

    Args:
        files: 测试文件（相对 backend）。
        run_id: 测试运行标识（第一轮据此删库重建，第二轮据此复用）。
        label: 轮次标签（`r1` / `r2`，用于逐批日志文件名）。
        extra: 透传给 pytest 的额外参数。

    Returns:
        tuple[int, str]: （退出码, 完整输出）；多条命令时取首个非 0 退出码。
    """
    env = dict(os.environ)
    env["CODEBUDDY_SAFE_DELETE_ENABLED"] = "0"
    # 与推送环同口径：本脚本是内部判定工具，目标清单可能含集成目录
    env["ENGKIT_FULL_TESTS_AUTHORIZED"] = "1"
    env["BMS_TEST_RUN_ID"] = run_id
    batches = _split_batches(files)
    code = 0
    chunks: list[str] = []  # bare-collections:allow（同上）
    for index, batch in enumerate(batches, start=1):
        if len(batches) > 1:
            print(f"[isolation]   第 {index}/{len(batches)} 批：{len(batch)} 个文件", flush=True)
        argv = [
            "uv",
            "run",
            "pytest",
            "-q",
            "-rf",
            "--tb=no",
            "-p",
            "bms_testing_plugin",
            "-n",
            "auto",
            *batch,
            *extra,
        ]
        completed = subprocess.run(argv, cwd=_BACKEND, env=env, capture_output=True, text=True, encoding="utf-8")
        output = completed.stdout + completed.stderr
        chunks.append(output)
        path = _write_batch_log(run_id, label, index, output)
        if completed.returncode != 0 and code == 0:
            code = completed.returncode
        print(
            f"[isolation]   第 {index}/{len(batches)} 批结果：{_summary(output) or '（无汇总行）'}（完整输出：{path}）",
            flush=True,
        )
    return code, "\n".join(chunks)


def _failures(output: str) -> set[str]:  # bare-collections:allow（脚本内临时集合）
    """从输出里取失败节点集合。

    Args:
        output: pytest 输出。

    Returns:
        set[str]: 失败 / 错误的节点 id。
    """
    return {match.group("nodeid") for match in _RESULT_RE.finditer(output)}


def _summary(output: str) -> str:
    """取末行汇总文本（只用于打印）。

    Args:
        output: pytest 输出。

    Returns:
        str: 末行汇总；找不到返回空串。
    """
    for line in reversed(output.strip().splitlines()):
        if _SUMMARY_RE.search(line):
            return line.strip()
    return ""


def main(argv: list[str] | None = None) -> int:  # bare-collections:allow（与 pytest 入口同形）
    """执行两轮复用判定。

    Args:
        argv: 命令行参数（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 0 通过；1 第二轮出现失败（用例违规）；2 用法 / 首轮失败（功能缺陷）。
    """
    parser = argparse.ArgumentParser(description="隔离自检：复用共享库连跑两轮")
    parser.add_argument("files", nargs="*", help="测试文件（相对 backend）")
    parser.add_argument("--files-from", default="", help="从文件读清单（`-` 表示 stdin）")
    parser.add_argument("--pytest-args", default="", help="透传给 pytest 的额外参数（空格分隔）")
    args = parser.parse_args(argv)

    files = list(args.files)
    if args.files_from:
        raw = sys.stdin.read() if args.files_from == "-" else Path(args.files_from).read_text(encoding="utf-8")
        files.extend(item.strip() for item in raw.splitlines() if item.strip())
    if not files:
        parser.error("未给出测试文件（位置参数或 --files-from）")

    extra = args.pytest_args.split() if args.pytest_args else []

    run_id = f"isolation-{uuid.uuid4().hex}"
    print(f"[isolation] 第 1 轮（本次运行首次会话，删库建库）：{len(files)} 个文件", flush=True)
    code1, out1 = _run_round(files, run_id=run_id, label="r1", extra=extra)
    first = _failures(out1)
    print(f"[isolation] 第 1 轮：{_summary(out1)}", flush=True)

    print("[isolation] 第 2 轮（同一次运行，叠加复用同一份库）", flush=True)
    code2, out2 = _run_round(files, run_id=run_id, label="r2", extra=extra)
    second = _failures(out2)
    print(f"[isolation] 第 2 轮：{_summary(out2)}", flush=True)

    if code1 != 0 and not first:
        print("[isolation] 第 1 轮退出码非 0 但未解析到失败项：按功能缺陷处理，先看完整输出", file=sys.stderr)
        return 2
    if code2 != 0 and not second:
        print("[isolation] 第 2 轮退出码非 0 但未解析到失败项：按功能缺陷处理，先看完整输出", file=sys.stderr)
        return 2

    if second:
        print(
            f"\n[isolation] 不通过：复用同一份库后有 {len(second)} 条失败（依赖空库 / 固定键 / 整表口径）",
            file=sys.stderr,
        )
        for nodeid in sorted(second):
            marker = "（首轮也失败）" if nodeid in first else ""
            print(f"  - {nodeid}{marker}", file=sys.stderr)
        return 1

    print("\n[isolation] 通过：复用同一份库连跑两轮无新增失败")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
