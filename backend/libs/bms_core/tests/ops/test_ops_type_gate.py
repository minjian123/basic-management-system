"""`ops` 类型门禁纳入（14_05 / Kiwi 2346）：`include` 已接线 + 当前零错 + 无滥用 ignore。

口径（14_05 详细设计 §4.3）：

- **已接线**：`backend/pyproject.toml` 的 `[tool.pyright].include` 含 `ops`（与 `libs` / `services` 同 strict），
  `ignore` 不得含 `ops`——只断言配置正确、代码有错时门禁仍红，故另跑一次 pyright 断言「当前零错」；
- **当前零错**：以子进程跑 `pyright ops`，退出码 0 且输出含 `0 errors`（复用同一份 `pyproject.toml` 配置）；
- **无滥用 ignore**：`backend/ops/**` 内 `# pyright: ignore` 必须逐条注明理由（本任务目标为 0 处）。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.migration import BACKEND_ROOT

_OPS_DIR = BACKEND_ROOT / "ops"
"""`ops` 脚本目录（运维通道：建库 / 建表 / 种子 / 校验 / 迁移）。"""

_PYPROJECT = BACKEND_ROOT / "pyproject.toml"
"""后端工作区根的 pyproject（`[tool.pyright]` 配置落点）。"""

_IGNORE_PATTERN = re.compile(r"#\s*pyright:\s*ignore(\[[^\]]*\])?\s*(?P<reason>.*)$")
"""`# pyright: ignore[规则]` 指令（捕获其后理由文本）。"""

_REASON_MIN_LENGTH = 4
"""理由文本最小字数（少于该长度视为「未注明理由」）。"""


def _pyright_config() -> ConcurrentStableDict[str, Any]:
    """读取 `[tool.pyright]` 配置段。

    Returns:
        ConcurrentStableDict[str, Any]: 配置映射（缺段时为空映射）。
    """
    parsed = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    tool = cast("Mapping[str, Any]", parsed.get("tool") or {})
    return ConcurrentStableDict(cast("Mapping[str, Any]", tool.get("pyright") or {}))


def _pyright_executable() -> str:
    """定位 `pyright` 可执行文件（优先当前解释器同目录，兜底 PATH）。

    Returns:
        str: 可执行文件路径。
    """
    name = "pyright.exe" if os.name == "nt" else "pyright"
    candidate = Path(sys.executable).with_name(name)
    if candidate.is_file():
        return str(candidate)
    located = shutil.which("pyright")
    assert located is not None, "未找到 pyright（开发依赖缺失，请先 uv sync）"
    return located


@pytest.mark.kiwi_id(2346)
def test_pyright_include_covers_ops() -> None:
    """`include` 含 `ops` 且 `ignore` 不含；严格模式与 `libs` / `services` 同口径（防回退）。"""
    config = _pyright_config()
    declared = ConcurrentStableList(str(item) for item in cast("list[Any]", config.get("include") or []))
    assert "ops" in declared
    assert {"libs", "services"} <= set(declared)
    assert config.get("typeCheckingMode") == "strict"
    ignored = ConcurrentStableList(str(item) for item in cast("list[Any]", config.get("ignore") or []))
    assert "ops" not in ignored


@pytest.mark.kiwi_id(2346)
def test_ops_pyright_reports_zero_errors() -> None:
    """`pyright ops` 子进程零错（配置已接线但代码有错时本用例即红）。"""
    completed = subprocess.run(
        [_pyright_executable(), "ops"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    assert completed.returncode == 0, output
    assert "0 errors" in output, output


def _ignore_reason(lines: ConcurrentStableList[str], index: int) -> str:
    """取某行的 ignore 指令理由：优先同行尾注，其次紧邻上一行注释。

    Args:
        lines: 文件行列表。
        index: ignore 指令所在行下标。

    Returns:
        str: 理由文本（无则空串）。
    """
    match = _IGNORE_PATTERN.search(lines[index])
    assert match is not None
    trailing = match.group("reason").strip().lstrip("#—-· ").strip()
    if trailing:
        return trailing
    previous = lines[index - 1].strip() if index > 0 else ""
    return previous.lstrip("#—-· ").strip() if previous.startswith("#") else ""


@pytest.mark.kiwi_id(2346)
def test_ops_has_no_unjustified_pyright_ignore() -> None:
    """`ops` 内 `# pyright: ignore` 逐条须注明理由（同行尾注或紧邻上一行注释）。"""
    problems: ConcurrentStableList[str] = ConcurrentStableList()
    for path in sorted(_OPS_DIR.rglob("*.py")):
        lines = ConcurrentStableList(path.read_text(encoding="utf-8").splitlines())
        for index, line in enumerate(lines):
            if _IGNORE_PATTERN.search(line) is None:
                continue
            if len(_ignore_reason(lines, index)) < _REASON_MIN_LENGTH:
                problems.add(f"{path.relative_to(BACKEND_ROOT).as_posix()}:{index + 1}")
    assert not problems, f"存在未注明理由的 pyright ignore：{', '.join(problems)}"
