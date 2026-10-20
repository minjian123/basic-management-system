"""重命令「跑一次」护栏用例（Kiwi 2315）：`run-once.py` 的缓存键、窗口回放与 `--force` 口径。

锁定 `03_02` 期间确立的口径（见工作区 `AGENTS.md`「重命令不重跑」与
`scripts/tools/preflight/README.md`）：分钟级重命令在同一工作区状态下短窗内**只真跑一次**，
重复调用回放上次完整输出与退出码；**工作区指纹含文件内容哈希**，改一个源文件即失效，
不得拿旧结果掩盖新改动。
"""

import importlib.util
from pathlib import Path

import pytest

from bms_core.core.concurrent import ConcurrentStableList

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SCRIPT = _REPO_ROOT / "scripts" / "tools" / "preflight" / "run-once.py"
_spec = importlib.util.spec_from_file_location("run_once_guard", _SCRIPT)
assert _spec is not None and _spec.loader is not None
run_once = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_once)


@pytest.fixture(autouse=True)
def cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把缓存目录重定向到临时目录（不污染仓库 `.cache`）。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch 夹具。

    Returns:
        Path: 临时缓存目录。
    """
    target = tmp_path / "run-once"
    monkeypatch.setattr(run_once, "_CACHE_DIR", target)
    return target


def _argv(text: str = "hello") -> ConcurrentStableList[str]:
    """构造一个轻量命令（真跑耗时 < 0.1s）。

    Args:
        text: 打印内容。

    Returns:
        tuple[str, ...]: 命令参数。
    """
    return ConcurrentStableList((str(run_once.sys.executable), "-c", f"print({text!r})"))


@pytest.mark.kiwi_id(2315)
def test_cache_key_varies_with_command_and_fingerprint() -> None:
    """缓存键：命令 / 工作目录 / 指纹任一变化即不同（同输入稳定）。"""
    base = run_once.cache_key(("a", "b"), "cwd", "fp1")
    assert base == run_once.cache_key(("a", "b"), "cwd", "fp1")
    assert base != run_once.cache_key(("a", "c"), "cwd", "fp1")
    assert base != run_once.cache_key(("a", "b"), "cwd2", "fp1")
    assert base != run_once.cache_key(("a", "b"), "cwd", "fp2")
    assert len(base) == 32


@pytest.mark.kiwi_id(2315)
def test_workspace_fingerprint_tracks_file_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """工作区指纹：跟踪已跟踪文件的**内容**变化（不只看提交号）。"""
    first = run_once.workspace_fingerprint()
    assert first != "nogit"
    assert first == run_once.workspace_fingerprint()

    probe = _REPO_ROOT / "backend" / "services" / "platform" / "src" / "bms_platform" / "services" / "separation.py"
    original = probe.read_text(encoding="utf-8")
    try:
        probe.write_text(original + "\n# fingerprint probe\n", encoding="utf-8")
        assert run_once.workspace_fingerprint() != first
    finally:
        probe.write_text(original, encoding="utf-8")
    assert run_once.workspace_fingerprint() == first


@pytest.mark.kiwi_id(2315)
def test_run_records_then_replays_without_executing(capsys: pytest.CaptureFixture[str]) -> None:
    """首次真跑并落记录；同状态再调用回放（不执行子进程，退出码透传）。"""
    argv = _argv()
    assert run_once.run(argv, window_seconds=1800, force=False, show_only=False) == 0
    first = capsys.readouterr().out
    assert "hello" in first
    assert "已记录" in first

    assert run_once.run(argv, window_seconds=1800, force=False, show_only=False) == 0
    second = capsys.readouterr().out
    assert "回放上次结果" in second
    assert "hello" in second


@pytest.mark.kiwi_id(2315)
def test_run_force_and_expired_window_execute_again(capsys: pytest.CaptureFixture[str]) -> None:
    """`--force` 与窗口过期均重新执行（不静默回放）。"""
    argv = _argv("again")
    run_once.run(argv, window_seconds=1800, force=False, show_only=False)
    capsys.readouterr()

    assert run_once.run(argv, window_seconds=1800, force=True, show_only=False) == 0
    assert "--force 真跑" in capsys.readouterr().out

    assert run_once.run(argv, window_seconds=0, force=False, show_only=False) == 0
    assert "缓存已过期" in capsys.readouterr().out


@pytest.mark.kiwi_id(2315)
def test_run_propagates_exit_code_and_clips_output(capsys: pytest.CaptureFixture[str]) -> None:
    """退出码透传（失败也记录，回放时仍为失败码）；超长输出截断并标注。"""
    failing = (str(run_once.sys.executable), "-c", "raise SystemExit(3)")
    assert run_once.run(failing, window_seconds=1800, force=False, show_only=False) == 3
    capsys.readouterr()
    assert run_once.run(failing, window_seconds=1800, force=False, show_only=False) == 3
    assert "回放上次结果" in capsys.readouterr().out

    text, clipped = run_once._clip("x" * (run_once._MAX_OUTPUT_CHARS + 10))
    assert clipped is True
    assert text.endswith("已截断，详见缓存文件）\n")
    plain, not_clipped = run_once._clip("short")
    assert plain == "short"
    assert not_clipped is False


@pytest.mark.kiwi_id(2315)
def test_show_only_reports_state_without_running(capsys: pytest.CaptureFixture[str]) -> None:
    """`--show`：只报告缓存状态，不执行命令、不写记录。"""
    argv = _argv("never-printed")
    assert run_once.run(argv, window_seconds=1800, force=False, show_only=True) == 0
    assert "无缓存" in capsys.readouterr().out
    assert not run_once._CACHE_DIR.exists()

    run_once.run(argv, window_seconds=1800, force=False, show_only=False)
    capsys.readouterr()
    assert run_once.run(argv, window_seconds=1800, force=False, show_only=True) == 0
    shown = capsys.readouterr().out
    assert "缓存命中" in shown
    assert "有效" in shown


@pytest.mark.kiwi_id(2315)
def test_main_option_parsing(capsys: pytest.CaptureFixture[str]) -> None:
    """命令行：缺 `--` / 缺命令 / 未知选项均返回 2；`--help` 返回 0。"""
    assert run_once.main(()) == 2
    assert run_once.main(("--",)) == 2
    assert run_once.main(("--bogus", "--", *_argv())) == 2
    assert run_once.main(("--window-seconds",)) == 2
    assert run_once.main(("--help",)) == 0
    capsys.readouterr()

    assert run_once.main(("--window-seconds", "60", "--", *_argv("ok"))) == 0
    assert "ok" in capsys.readouterr().out
