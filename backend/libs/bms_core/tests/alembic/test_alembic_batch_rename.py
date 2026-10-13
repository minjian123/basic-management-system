"""Alembic 批处理「列改名」口径护栏：改名块必须 `recreate="always"` 或显式 `existing_type`。

MySQL 下 `batch_alter_table` 的 `recreate="auto"` 会走 `ALTER ... CHANGE`，而 MySQL 要求
`CHANGE/MODIFY` 必须带类型 ⇒ 只给 `new_column_name` 会报
`All MySQL CHANGE/MODIFY COLUMN operations require the existing type.`
（2026-10-13 真库实测：`platform:platform` 0010、`platform:tenant` 0011 / 0014 三处；
`identity:tenant` 0006 同源缺陷，一并修）。
"""

import re
from pathlib import Path

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db.migration import BACKEND_ROOT

_VERSIONS_DIR = BACKEND_ROOT / "alembic" / "versions"
"""迁移脚本根（各链子目录）。"""

_BATCH_CALL_RE = re.compile(r"^(\s*)with op\.batch_alter_table\((.*)$")
"""`with op.batch_alter_table(...)` 语句（分组：缩进 / 调用参数）。"""

_RENAME_MARKER = "new_column_name"
"""改名关键字（`batch.alter_column(..., new_column_name=...)`）。"""


def _indent_of(line: str) -> int:
    """取行首缩进宽度。

    Args:
        line: 文本行。

    Returns:
        int: 前导空格数。
    """
    return len(line) - len(line.lstrip())


def _batch_body(lines: ConcurrentStableList[str], start: int, indent: int) -> str:
    """取 `with` 语句的块体文本（缩进深于 `with` 行，至首个同级 / 更浅的实义行止）。

    Args:
        lines: 文件行列表。
        start: `with` 行下标。
        indent: `with` 行缩进宽度。

    Returns:
        str: 块体文本（无块体返回空串）。
    """
    body: ConcurrentStableList[str] = ConcurrentStableList()
    for follow in lines[start + 1 :]:
        if not follow.strip():
            continue
        if _indent_of(follow) <= indent:
            break
        body.add(follow)
    return "\n".join(body)


def _scan(path: Path) -> tuple[int, ConcurrentStableList[str]]:
    """扫描单个迁移文件：统计改名块数并收集违规项。

    Args:
        path: 迁移脚本路径。

    Returns:
        tuple[int, ConcurrentStableList[str]]: 改名块总数 + 违规描述（含行号）。
    """
    lines = ConcurrentStableList(path.read_text(encoding="utf-8").splitlines())
    problems: ConcurrentStableList[str] = ConcurrentStableList()
    renames = 0
    for index, line in enumerate(lines):
        match = _BATCH_CALL_RE.match(line)
        if match is None:
            continue
        indent = len(match.group(1))
        args = match.group(2)
        body = _batch_body(lines, index, indent)
        if _RENAME_MARKER not in body:
            continue
        renames += 1
        if "recreate=" in args or "existing_type=" in body:
            continue
        problems.add(f"{index + 1} 行：batch_alter_table({args.strip()}")
    return renames, problems


def test_batch_rename_declares_recreate_or_existing_type() -> None:
    """各迁移链的列改名块必须声明 `recreate="always"`（或显式 `existing_type`）以兼容 MySQL。"""
    problems: ConcurrentStableList[str] = ConcurrentStableList()
    renames = 0
    for path in sorted(_VERSIONS_DIR.rglob("*.py")):
        found, items = _scan(path)
        renames += found
        for item in items:
            problems.add(f"{path.relative_to(BACKEND_ROOT)}:{item}")
    # 非空断言：扫描面必须真的扫到改名块（否则本护栏形同虚设）
    assert renames > 0
    assert not problems, '列改名块缺 recreate="always" / existing_type：\n' + "\n".join(problems)


def test_scanner_flags_missing_recreate(tmp_path: Path) -> None:
    """扫描器自检：缺 `recreate` 的改名块被拦，带 `recreate=\"always\"` 或 `existing_type` 放行。"""
    bad = tmp_path / "bad.py"
    bad.write_text(
        "def upgrade() -> None:\n"
        "    with op.batch_alter_table('t') as batch:\n"
        "        batch.alter_column('a', new_column_name='b')\n",
        encoding="utf-8",
    )
    renames, problems = _scan(bad)
    assert renames == 1
    assert len(problems) == 1

    good = tmp_path / "good.py"
    good.write_text(
        "def upgrade() -> None:\n"
        "    with op.batch_alter_table('t', recreate='always') as batch:\n"
        "        batch.alter_column('a', new_column_name='b')\n"
        "    with op.batch_alter_table('t2') as batch:\n"
        "        batch.alter_column('c', new_column_name='d', existing_type=sa.String(length=64))\n",
        encoding="utf-8",
    )
    renames, problems = _scan(good)
    assert renames == 2
    assert not problems
