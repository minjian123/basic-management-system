#!/usr/bin/env python3
"""覆盖率豁免必须带理由（本仓专属护栏）。

口径（《AI开发规范》「覆盖率要求」/《测试规范》§6）：
`# pragma: no cover` 只允许用于**确实不可达**的分支（被 schema / 前置校验拦截、环境缺失显式报错等），
且**必须**在同一行以 ` - 理由` 说明不可达原因；否则覆盖率门禁会出现「永远补不上」的分支缺口，
且后人无法判断该豁免是否仍然成立。

用法::

    python3 scripts/tools/preflight/check_pragma_reason.py [仓库根] [--files-from <清单>]

`--files-from -` 从标准输入读改动清单（每行一个仓根相对路径）；缺省扫全仓。

退出码：0 通过 / 1 存在违规 / 2 参数错误。
"""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

_SCAN_ROOTS = ("backend", "scripts", "deploy/registry")
"""扫描面：后端源码与测试、脚本、清单（`engkit` 仓不在本仓）。

刻意不含 `engkit.toml` / 文档：规范文本里会出现该标记本身。
"""

_SKIP_DIRS = {".venv", ".cache", "__pycache__", "node_modules", ".git", "dist", "build"}
"""跳过目录（依赖外置、缓存、产物）。"""

_PATTERN = re.compile(r"#\s*pragma:\s*no\s*cover(?!\s*-\s*\S)")
"""命中「`pragma: no cover` 后没有 ` - 非空理由`」的写法（含 `no cover` 前有空格变体）。"""

_SELF = Path(__file__).resolve()
"""本文件自身（说明文本里含该标记，跳过）。"""

_LEGACY_EXEMPT = frozenset(  # bare-collections:allow（只读基线）
    frozenset(  # bare-collections:allow（只读基线，不参与业务集合语义）
        {
            "backend/libs/bms_core/src/bms_core/core/config.py:1458",
            "backend/libs/bms_core/src/bms_core/servicecall/http.py:165",
            "backend/libs/bms_core/src/bms_core/transfer/openpyxl_io.py:169",
            "backend/services/platform/src/bms_platform/domains/import_export/api/exports.py:217",
            "backend/services/platform/src/bms_platform/domains/import_export/api/imports.py:151",
            "backend/services/platform/tests/jobs/test_platform_job_bootstrap.py:150",
        }
    )
)
"""存量无理由豁免基线（2026-11-03 登记）：只减不增。

他人历史代码不在本任务范围，先登记基线让护栏可挂全量；这些文件被改动时按 §6 口径补理由后从本集合删除。
新增违规一律即时拦截（本集合不再扩容）。
"""


def _iter_python_files(
    root: Path,
) -> Sequence[Path]:  # bare-collections:allow（命令行参数）
    """列出扫描面内的 Python 文件。

    Args:
        root: 仓库根。

    Returns:
        list[Path]: 待扫描文件（绝对路径，稳定排序）。  # bare-collections:allow（命令行参数）
    """
    found = []  # bare-collections:allow（命令行参数）
    for relative in _SCAN_ROOTS:
        base = root / relative
        if not base.exists():
            continue
        if base.is_file():
            found.append(base)
            continue
        for path in base.rglob("*.py"):
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            found.append(path)
    return sorted(set(found))


def _files_from(root: Path, stream: TextIO) -> Sequence[Path]:  # bare-collections:allow（命令行参数）
    """按改动清单筛选待扫描文件。

    Args:
        root: 仓库根。
        stream: 清单来源（标准输入）。

    Returns:
        list[Path]: 清单命中的 Python 文件。  # bare-collections:allow（命令行参数）
    """
    selected = []  # bare-collections:allow（命令行参数）
    for line in stream:
        name = line.strip()
        if not name or not name.endswith(".py"):
            continue
        path = (root / name).resolve()
        if path.exists() and path != _SELF:
            selected.append(path)
    return sorted(set(selected))


def _check_file(path: Path, root: Path) -> Sequence[str]:  # bare-collections:allow（命令行参数）
    """检查单文件的 pragma 豁免理由。

    Args:
        path: 文件绝对路径。
        root: 仓库根（用于展示相对路径）。

    Returns:
        list[str]: 违规行（`相对路径:行号: 说明`）。  # bare-collections:allow（命令行参数）
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:  # pragma: no cover - 读失败即环境问题（权限 / 并发删除），不参与判定
        return [f"{path}: 读取失败（{error.__class__.__name__}）"]
    relative = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
    problems = []  # bare-collections:allow（命令行参数）
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        if _PATTERN.search(line):
            problems.append(
                f"{relative}:{number}: `# pragma: no cover` 缺理由（写成 `# pragma: no cover - 不可达原因`）"
            )
    return problems


def _parse_args(
    argv: Any,
) -> tuple[Path, str]:  # bare-collections:allow（命令行参数）
    """解析参数。

    Args:
        argv: 命令行参数（不含程序名）。

    Returns:
        tuple[Path, str]: （仓库根, `--files-from` 取值；空串表示全量）。  # bare-collections:allow（命令行参数）

    Raises:
        ValueError: 未知参数或缺少取值。
    """
    root = Path.cwd()
    files_from = ""
    index = 0
    while index < len(argv):
        item = argv[index]
        if item == "--files-from":
            if index + 1 >= len(argv):
                raise ValueError("--files-from 缺少取值")
            files_from = argv[index + 1]
            index += 2
            continue
        if item.startswith("-"):
            raise ValueError(f"未知参数：{item}")
        root = Path(item)
        index += 1
    return root.resolve(), files_from


def main(
    argv: Any = None,
) -> int:  # bare-collections:allow（命令行参数）
    """入口。

    Args:
        argv: 命令行参数（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码（0 通过 / 1 违规 / 2 参数错误）。
    """
    try:
        root, files_from = _parse_args(sys.argv[1:] if argv is None else argv)
    except ValueError as error:
        print(f"[pragma-reason] 参数错误：{error}", file=sys.stderr)
        return 2
    if files_from == "-":
        targets = _files_from(root, sys.stdin)
    elif files_from:
        listing = Path(files_from)
        if not listing.exists():
            print(f"[pragma-reason] 清单不存在：{listing}", file=sys.stderr)
            return 2
        with listing.open(encoding="utf-8") as stream:
            targets = _files_from(root, stream)
    else:
        targets = [path for path in _iter_python_files(root) if path != _SELF]
    problems = []  # bare-collections:allow（命令行参数）
    exempted = 0
    for path in targets:
        for problem in _check_file(path, root):
            head = problem.split(":", 2)
            key = f"{head[0]}:{head[1]}" if len(head) > 1 else problem
            if key in _LEGACY_EXEMPT:
                exempted += 1
                continue
            problems.append(problem)
    if problems:
        print(f"[pragma-reason] 不通过：{len(problems)} 项", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"[pragma-reason] 通过：{len(targets)} 个文件（豁免均带理由；存量基线 {exempted} 处待整改）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
