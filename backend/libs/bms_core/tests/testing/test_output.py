"""测试公共基座：输出捕获与 CLI 调用（Kiwi 2317）。"""

import subprocess
import sys

import pytest

from bms_core.testing import CliResult, assert_exit, assert_output, run_cli, stderr_text, stdout_text


@pytest.mark.kiwi_id(2317)
def test_stdout_stderr_text(capsys: pytest.CaptureFixture[str]) -> None:
    """读取：stdout / stderr 分别返回（读取即清空）。"""
    print("out-line")
    print("err-line", file=sys.stderr)

    assert stdout_text(capsys).strip() == "out-line"
    assert stderr_text(capsys).strip() == "err-line"


@pytest.mark.kiwi_id(2317)
def test_assert_output_contains_and_not_contains(capsys: pytest.CaptureFixture[str]) -> None:
    """断言：包含 / 不包含；失败信息带实际输出尾部。"""
    print("ok-marker")
    assert_output(capsys, contains="ok-marker", not_contains="boom")

    print("boom")
    with pytest.raises(AssertionError) as exc:
        assert_output(capsys, not_contains="boom")
    assert "boom" in str(exc.value)


@pytest.mark.kiwi_id(2317)
def test_run_cli_and_assert_exit() -> None:
    """CLI：执行 `-c` 片段，返回退出码与输出；退出码断言失败时带输出。"""
    result = run_cli("-c", "print('cli-ok')")

    assert result.ok
    assert "cli-ok" in result.stdout

    failed = run_cli("-c", "raise SystemExit(3)")
    assert failed.exit_code == 3
    with pytest.raises(AssertionError):
        assert_exit(failed, 0)


@pytest.mark.kiwi_id(2317)
def test_cli_result_tail() -> None:
    """结果尾部：stdout / stderr 合并后取末尾行。"""
    result = CliResult(exit_code=1, stdout="a\nb\n", stderr="c\n")

    assert result.tail(2) == "b\nc"


@pytest.mark.kiwi_id(2317)
def test_assert_output_without_conditions(capsys: pytest.CaptureFixture[str]) -> None:
    """空条件：不读取即不报错（短路分支）。"""
    assert_output(capsys)


@pytest.mark.kiwi_id(2317)
def test_run_cli_timeout() -> None:
    """超时：到点抛 `TimeoutExpired`（防测试里挂死）。"""
    with pytest.raises(subprocess.TimeoutExpired):
        run_cli("-c", "import time; time.sleep(2)", timeout=0.05)


@pytest.mark.kiwi_id(2317)
def test_assert_exit_passes_on_match() -> None:
    """退出码断言：相符时不抛错。"""
    assert_exit(CliResult(exit_code=0, stdout="", stderr=""))


@pytest.mark.kiwi_id(2317)
def test_assert_output_missing_contains(capsys: pytest.CaptureFixture[str]) -> None:
    """失败：声明必须包含的片段不存在时给出实际输出尾部。"""
    print("actual")

    with pytest.raises(AssertionError) as exc:
        assert_output(capsys, contains="missing-marker")
    assert "missing-marker" in str(exc.value)
