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

_SUMMARY_RE = re.compile(r"(?P<failed>\d+) failed.*?(?P<passed>\d+) passed|(?P<passed_only>\d+) passed")
"""末行汇总（只用于打印，不参与判定）。"""


def _run_round(  # bare-collections:allow（本脚本只依赖标准库，不引 bms_core 并发集合）
    files: list[str], *, run_id: str, extra: list[str]
) -> tuple[int, str]:
    """跑一轮 pytest（两轮共用同一 `BMS_TEST_RUN_ID`）。

    Args:
        files: 测试文件（相对 backend）。
        run_id: 测试运行标识（第一轮据此删库重建，第二轮据此复用）。
        extra: 透传给 pytest 的额外参数。

    Returns:
        tuple[int, str]: （退出码, 完整输出）。
    """
    env = dict(os.environ)
    env["CODEBUDDY_SAFE_DELETE_ENABLED"] = "0"
    # 与推送环同口径：本脚本是内部判定工具，目标清单可能含集成目录
    env["ENGKIT_FULL_TESTS_AUTHORIZED"] = "1"
    env["BMS_TEST_RUN_ID"] = run_id
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
        *files,
        *extra,
    ]
    completed = subprocess.run(argv, cwd=_BACKEND, env=env, capture_output=True, text=True, encoding="utf-8")
    return completed.returncode, completed.stdout + completed.stderr


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
        if "passed" in line or "failed" in line or "error" in line:
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
    code1, out1 = _run_round(files, run_id=run_id, extra=extra)
    first = _failures(out1)
    print(f"[isolation] 第 1 轮：{_summary(out1)}", flush=True)

    print("[isolation] 第 2 轮（同一次运行，叠加复用同一份库）", flush=True)
    code2, out2 = _run_round(files, run_id=run_id, extra=extra)
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
