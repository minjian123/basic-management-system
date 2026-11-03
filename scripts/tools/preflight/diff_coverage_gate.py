#!/usr/bin/env python3
"""改动行覆盖率门禁：只判「本次改动的代码行」是否被本轮测试执行到。

**为什么不是模块级**：要求整个模块 100%，会把与本次改动无关的历史缺口一起算账——改一行也要
为整文件补齐用例，代价与收益不成比例。本门禁的判据是**本次 diff 新增 / 修改的行必须被执行**，
未改动的代码不参与判定。

采集范围仍由 `--cov=<模块>` 限定（调用方决定）：未被采集的文件（如改动落在没有同名测试的
公共模块）直接跳过，其覆盖率由推送环 / CI 的全量判据承担。

用法（在 bms 仓库根，由预检的 scoped_tests 步骤调用）::

    python3 scripts/tools/preflight/diff_coverage_gate.py --report backend/.coverage.json --root .

改动清单从标准输入读（一行一个仓根相对路径），与其它步骤的 `--files-from -` 同口径，不落盘。

退出码：0 达标；1 存在未覆盖的改动行；2 参数 / 环境错误。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet

__all__ = ["changed_lines", "main", "statements_of"]

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
"""unified diff 的 hunk 头（取新文件起始行与行数）。"""

_SKIP_SEGMENTS = ("/tests/", "/test/")
"""测试目录不参与覆盖率判定（它们本身不是被测对象）。"""


def changed_lines(root: Path, relative: str) -> ConcurrentStableSet[int]:
    """取暂存区里某文件**新增 / 修改**的行号（删除行不参与）。

    Args:
        root: 仓库根。
        relative: 仓根相对路径。

    Returns:
        ConcurrentStableSet[int]: 新文件行号集合。
    """
    lines: ConcurrentStableSet[int] = ConcurrentStableSet()
    completed = subprocess.run(
        ["git", "diff", "--cached", "-U0", "--", relative],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        return lines
    for raw in completed.stdout.splitlines():
        match = _HUNK.match(raw)
        if match is None:
            continue
        start = int(match.group(1))
        count = 1 if match.group(2) is None else int(match.group(2))
        for offset in range(count):
            lines.add(start + offset)
    return lines


def statements_of(
    payload: ConcurrentStableDict[str, object],
    relative: str,
) -> tuple[ConcurrentStableSet[int], ConcurrentStableSet[int]] | None:
    """从 coverage JSON 里取某文件的「可执行语句行」与「未执行行」。

    可执行行 = `executed_lines ∪ missing_lines`；改动行若两种都不是（注释 / 空行 / 文档串），
    说明它根本不可执行，不参与判定。

    Args:
        payload: coverage JSON 报告内容。
        relative: 仓根相对路径。

    Returns:
        tuple[ConcurrentStableSet[int], ConcurrentStableSet[int]] | None:
            （可执行行, 未执行行）；该文件未被采集返回 None。
    """
    files = payload.get("files")
    if not isinstance(files, dict):
        return None
    wanted = relative.replace("\\", "/")
    for path, entry in files.items():
        normalized = str(path).replace("\\", "/")
        if not normalized.endswith(wanted):
            continue
        if not isinstance(entry, dict):
            return None
        executed_raw = entry.get("executed_lines")
        missing_raw = entry.get("missing_lines")
        if not isinstance(executed_raw, list) or not isinstance(missing_raw, list):
            return None
        executed: ConcurrentStableSet[int] = ConcurrentStableSet()
        for number in executed_raw:
            executed.add(int(number))
        missing: ConcurrentStableSet[int] = ConcurrentStableSet()
        for number in missing_raw:
            missing.add(int(number))
        statements: ConcurrentStableSet[int] = ConcurrentStableSet()
        for number in executed:
            statements.add(number)
        for number in missing:
            statements.add(number)
        return statements, missing
    return None


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（None 取 `sys.argv`）。

    Returns:
        int: 退出码。
    """
    parser = argparse.ArgumentParser(prog="diff_coverage_gate", description="改动行覆盖率门禁")
    parser.add_argument("--report", required=True, help="coverage JSON 报告路径")
    parser.add_argument("--root", default=".", help="仓库根（git 命令工作目录）")
    args = parser.parse_args(None if argv is None else list(argv))
    report = Path(args.report)
    if not report.is_file():
        print(f"[diff-coverage] 未找到覆盖率报告：{report}", file=sys.stderr)
        return 2
    root = Path(args.root).resolve()
    try:
        payload = cast("ConcurrentStableDict[str, object]", json.loads(report.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[diff-coverage] 覆盖率报告不可读：{exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("[diff-coverage] 覆盖率报告格式非法", file=sys.stderr)
        return 2
    gaps: ConcurrentStableDict[str, ConcurrentStableList[int]] = ConcurrentStableDict()
    checked = 0
    skipped: ConcurrentStableList[str] = ConcurrentStableList()
    for raw in sys.stdin.read().splitlines():
        relative = raw.strip()
        if not relative or not relative.endswith(".py"):
            continue
        if any(segment in f"/{relative}" for segment in _SKIP_SEGMENTS):
            continue
        probe = statements_of(payload, relative)
        if probe is None:
            skipped.add(relative)
            continue
        statements, missing = probe
        checked += 1
        # 只判「可执行的改动行」：注释 / 空行 / 文档串不在语句集合里，天然被排除
        hit = sorted(changed_lines(root, relative) & statements)
        uncovered = sorted(number for number in hit if number in missing)
        if uncovered:
            gaps.set(relative, ConcurrentStableList(uncovered))
    if skipped:
        print(f"[diff-coverage] 跳过 {len(skipped)} 个未采集文件（无同名测试，交推送环）")
    if not checked:
        print("[diff-coverage] 无可判文件：本轮改动的源文件均未被覆盖率采集")
        return 0
    if not gaps:
        print(f"[diff-coverage] 通过：{checked} 个文件的改动行均已被执行")
        return 0
    print("[diff-coverage] 未通过：以下文件的改动行未被本轮测试执行", file=sys.stderr)
    for relative, numbers in gaps.items():
        shown = "、".join(str(number) for number in numbers[:20])
        suffix = "" if len(numbers) <= 20 else f" …（共 {len(numbers)} 行）"
        print(f"[diff-coverage]   {relative}: {shown}{suffix}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
