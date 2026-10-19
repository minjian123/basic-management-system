"""统一输出断言与 CLI 调用（13_04）：capsys 读取 / 断言 + `run_cli` 入口。

- `stdout_text` / `stderr_text`：一次读取捕获（`readouterr` 会清空缓冲，重复调用请先取文本）；
- `assert_output`：包含 / 不包含断言，失败信息带实际输出尾部；
- `run_cli`：以当前解释器执行模块入口（`-m ops.xxx`）或脚本路径，返回 `CliResult`。
"""

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bms_core.core.concurrent import ConcurrentStableList

_TAIL_LINES = 20
"""失败信息里回显的输出行数（防止刷屏）。"""


@dataclass(frozen=True)
class CliResult:
    """CLI 执行结果。

    Attributes:
        exit_code: 退出码。
        stdout: 标准输出。
        stderr: 标准错误。
    """

    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        """是否成功（退出码为 0）。"""
        return self.exit_code == 0

    def tail(self, lines: int = _TAIL_LINES) -> str:
        """输出尾部（失败信息用）。

        Args:
            lines: 保留行数。

        Returns:
            str: 合并输出的末尾若干行。
        """
        merged = (self.stdout + self.stderr).splitlines()
        return "\n".join(merged[-lines:])


class _Captured:
    """捕获累积缓冲（`readouterr` 会清空，多次读取时按累积值返回）。"""

    def __init__(self) -> None:
        """初始化空缓冲。"""
        self.out = ""
        self.err = ""


def _read(capsys: Any) -> _Captured:
    """读取并累积捕获输出（同一次用例内多次调用不丢先前内容）。

    Args:
        capsys: pytest `capsys` 夹具。

    Returns:
        _Captured: 累积缓冲。
    """
    captured = getattr(capsys, "_bms_captured", None)
    if not isinstance(captured, _Captured):
        captured = _Captured()
        capsys._bms_captured = captured
    current = capsys.readouterr()
    captured.out += str(current.out)
    captured.err += str(current.err)
    return captured


def stdout_text(capsys: Any) -> str:
    """读取并返回标准输出（累积值）。

    Args:
        capsys: pytest `capsys` 夹具。

    Returns:
        str: 标准输出文本。
    """
    return _read(capsys).out


def stderr_text(capsys: Any) -> str:
    """读取并返回标准错误（累积值）。

    Args:
        capsys: pytest `capsys` 夹具。

    Returns:
        str: 标准错误文本。
    """
    return _read(capsys).err


def assert_output(
    capsys: Any,
    *,
    contains: str = "",
    not_contains: str = "",
) -> None:
    """断言捕获输出包含 / 不包含指定片段。

    Args:
        capsys: pytest `capsys` 夹具。
        contains: 必须包含的片段（空串不断言）。
        not_contains: 不得包含的片段（空串不断言）。

    Raises:
        AssertionError: 断言不通过（带实际输出尾部）。
    """
    text = stdout_text(capsys)
    problems: ConcurrentStableList[str] = ConcurrentStableList()
    if contains and contains not in text:
        problems.add(f"输出应包含 {contains!r}")
    if not_contains and not_contains in text:
        problems.add(f"输出不应包含 {not_contains!r}")
    if problems:
        tail = "\n".join(text.splitlines()[-_TAIL_LINES:])
        raise AssertionError("；".join(problems) + f"\n实际输出（尾 {_TAIL_LINES} 行）：\n{tail}")


def run_cli(*args: str, cwd: Path | None = None, timeout: float | None = 120.0) -> CliResult:
    """以当前解释器执行 CLI（`-m 模块` 或脚本路径）并捕获输出。

    Args:
        *args: 传给解释器的参数（如 `("-m", "ops.check_modules", "--offline")`）。
        cwd: 工作目录；`None` 取当前目录。
        timeout: 超时（秒）；`None` 不设限。

    Returns:
        CliResult: 退出码与输出。

    Raises:
        subprocess.TimeoutExpired: 超过 `timeout`。
    """
    completed = subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return CliResult(exit_code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)


def assert_exit(result: CliResult, expected: int = 0) -> None:
    """断言 CLI 退出码。

    Args:
        result: `run_cli` 返回值。
        expected: 期望退出码。

    Raises:
        AssertionError: 退出码不符（带输出尾部）。
    """
    if result.exit_code != expected:
        raise AssertionError(f"CLI 退出码期望 {expected}、实际 {result.exit_code}\n{result.tail()}")
