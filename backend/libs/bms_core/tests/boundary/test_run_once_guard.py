"""重命令包装护栏用例（Kiwi 2317）：缓存回放与 `--force` / `--show` 语义不变。

13_05 起缓存键、指纹与回放实现在 engkit（包内 `tests/test_runonce.py` 全覆盖），本仓只锁：
包装转发后同一命令在同一工作区状态下窗口内回放、`--force` 真跑、`--show` 只看状态。
"""

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SCRIPT = _REPO_ROOT / "scripts" / "tools" / "preflight" / "run-once.py"


def _run(cache_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """跑一次包装。

    Args:
        cache_dir: 缓存目录（放临时目录，避免污染仓库）。
        *args: 选项与命令。

    Returns:
        subprocess.CompletedProcess[str]: 执行结果。
    """
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--cache-dir", str(cache_dir), *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_replay_and_force(tmp_path: Path) -> None:
    """首次真跑、窗口内回放、`--force` 重跑。"""
    cache = tmp_path / "cache"
    command = [sys.executable, "-c", "print('once-marker')"]
    first = _run(cache, "--", *command)
    assert first.returncode == 0
    assert "已记录" in first.stdout
    second = _run(cache, "--", *command)
    assert second.returncode == 0
    assert "回放上次结果" in second.stdout
    assert "once-marker" in second.stdout
    forced = _run(cache, "--force", "--", *command)
    assert "真跑" in forced.stdout


def test_show_only(tmp_path: Path) -> None:
    """`--show` 只报告状态、不执行命令。"""
    cache = tmp_path / "cache"
    command = [sys.executable, "-c", "print('show-marker')"]
    empty = _run(cache, "--show", "--", *command)
    assert "无缓存" in empty.stdout
    _run(cache, "--", *command)
    state = _run(cache, "--show", "--", *command)
    assert "缓存命中" in state.stdout


def test_window_seconds_option(tmp_path: Path) -> None:
    """窗口参数被接受（0 秒即视为已过期）。"""
    cache = tmp_path / "cache"
    command = [sys.executable, "-c", "print('window')"]
    _run(cache, "--window-seconds", "0", "--", *command)
    again = _run(cache, "--window-seconds", "0", "--", *command)
    assert "缓存已过期" in again.stdout


def test_wrapper_forwards_to_engkit() -> None:
    """包装只转发到 engkit（不含缓存实现）。"""
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "engkit" in source
    assert "hashlib" not in source
    assert "fingerprint" not in source
