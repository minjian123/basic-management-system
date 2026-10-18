#!/usr/bin/env python3
"""重命令跑一次（run-once）：同一命令在同一工作区状态下**短窗内只真跑一次**，重复调用回放上次结果。

解决的问题：预检 / 全量 pytest / 全仓 ruff / pyright 这类分钟级命令，第一次已拿到结论，
再为「从输出里挑几行报错」整轮重跑，是纯浪费。本脚本把它变成技术约束，而不是靠自觉。

判定口径：

1. **缓存键**＝「命令 + 工作目录 + 工作区指纹」的 SHA-256；工作区指纹＝`HEAD` 提交号 +
   所有已跟踪变更与未跟踪文件的内容哈希。**改一个源文件指纹即变**，不会拿旧结果掩盖新改动。
2. **窗口**（缺省 30 分钟）：窗口内命中 → 直接回放上次完整输出（含退出码）并标注「回放」；
   超出窗口 → 真跑并覆盖记录。
3. `--force`：忽略缓存真跑（改完代码想立刻重验时用）。

用法::

    python3 scripts/tools/preflight/run-once.py -- <命令...>
    python3 scripts/tools/preflight/run-once.py --force -- <命令...>
    python3 scripts/tools/preflight/run-once.py --window-seconds 600 -- <命令...>
    python3 scripts/tools/preflight/run-once.py --show -- <命令...>     # 只看缓存状态，不执行

示例::

    python3 scripts/tools/preflight/run-once.py -- python3 scripts/tools/preflight/check-preflight.py
    python3 scripts/tools/preflight/run-once.py -- uv run --directory backend pytest -q

退出码：真跑时透传命令退出码；回放时透传上次退出码；缓存命中但窗口已过则真跑。
"""

import hashlib
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
"""bms 仓库根（本脚本位于 `scripts/tools/preflight/`）。"""

_CACHE_DIR = _REPO_ROOT / ".cache" / "run-once"
"""缓存目录（`.gitignore` 已忽略 `.cache`）。"""

_DEFAULT_WINDOW_SECONDS = 1800
"""缺省窗口：30 分钟（覆盖一次连续作业周期）。"""

_MAX_OUTPUT_CHARS = 4_000_000
"""单流输出落盘上限（防异常命令把缓存撑爆；超出截断并标注）。"""


@dataclass
class RunRecord:
    """一次真跑的完整记录。

    Attributes:
        key: 缓存键（命令 + 工作目录 + 工作区指纹的摘要）。
        argv: 命令参数。
        cwd: 工作目录。
        fingerprint: 工作区指纹。
        started_at: 开始时间（Unix 秒）。
        duration_seconds: 耗时（秒）。
        exit_code: 退出码。
        stdout: 标准输出全文。
        stderr: 标准错误全文。
        truncated: 是否发生输出截断。
    """

    key: str
    argv: tuple[str, ...] = ()
    cwd: str = ""
    fingerprint: str = ""
    started_at: float = 0.0
    duration_seconds: float = 0.0
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    truncated: bool = False


def _git(*args: str) -> str:
    """在 bms 仓库根执行 git 命令并返回标准输出。

    Args:
        *args: git 子命令与参数。

    Returns:
        str: 标准输出（UTF-8，容错解码）。

    Raises:
        RuntimeError: git 不可用或命令失败（此时退化为「无指纹」，不阻断执行）。
    """
    try:
        completed = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as error:  # git 未安装
        raise RuntimeError(str(error)) from error
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"git {' '.join(args)} 失败")
    return completed.stdout


def _hash_file(path: Path) -> str:
    """计算文件内容摘要。

    Args:
        path: 文件路径。

    Returns:
        str: SHA-256 十六进制摘要；文件不可读时返回占位串（不阻断指纹计算）。
    """
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "<unreadable>"


def workspace_fingerprint() -> str:
    """计算工作区指纹：`HEAD` + 全部变更文件内容哈希。

    覆盖已跟踪的改动（含暂存与未暂存）与未跟踪文件；任一文件内容变化即指纹变化，
    因此「改了代码但没提交」不会命中旧缓存。

    Returns:
        str: 指纹（SHA-256 十六进制）；git 不可用时返回 `nogit`。
    """
    try:
        head = _git("rev-parse", "HEAD").strip()
        status = _git("status", "--porcelain", "-z", "--untracked-files=all")
    except RuntimeError:
        return "nogit"
    digest = hashlib.sha256(head.encode())
    entries = [entry for entry in status.split("\0") if entry]
    for entry in sorted(entries):
        # porcelain -z：`XY <path>`；重命名时随后还会跟一条原始路径条目，一并纳入即可。
        path = entry[3:] if len(entry) > 3 else entry
        digest.update(path.encode())
        digest.update(_hash_file(_REPO_ROOT / path).encode())
    return digest.hexdigest()


def cache_key(argv: tuple[str, ...], cwd: str, fingerprint: str) -> str:
    """计算缓存键。

    Args:
        argv: 命令参数。
        cwd: 工作目录。
        fingerprint: 工作区指纹。

    Returns:
        str: 缓存键（SHA-256 十六进制，前 32 位足够防碰撞）。
    """
    material = "\0".join([*argv, cwd, fingerprint])
    return hashlib.sha256(material.encode()).hexdigest()[:32]


def _cache_path(key: str) -> Path:
    """取缓存文件路径。

    Args:
        key: 缓存键。

    Returns:
        Path: 缓存文件路径。
    """
    return _CACHE_DIR / f"{key}.json"


def load_record(key: str) -> RunRecord | None:
    """读取缓存记录。

    Args:
        key: 缓存键。

    Returns:
        RunRecord | None: 记录；不存在或损坏时为 None。
    """
    path = _cache_path(key)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return None
    try:
        return RunRecord(**payload)
    except TypeError:
        return None


def save_record(record: RunRecord) -> None:
    """写入缓存记录。

    Args:
        record: 运行记录。
    """
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(record.key).write_text(json.dumps(asdict(record), ensure_ascii=False, indent=2), encoding="utf-8")


def _clip(text: str) -> tuple[str, bool]:
    """按上限截断单流输出。

    Args:
        text: 原始输出。

    Returns:
        tuple[str, bool]: （截断后文本, 是否截断）。
    """
    if len(text) <= _MAX_OUTPUT_CHARS:
        return text, False
    return text[:_MAX_OUTPUT_CHARS] + "\n…（输出超出上限已截断，详见缓存文件）\n", True


def _emit(text: str) -> None:
    """安全打印（Windows 控制台编码兜底）。

    Args:
        text: 待打印文本。
    """
    if not text:
        return
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.flush()


def run(argv: tuple[str, ...], *, window_seconds: int, force: bool, show_only: bool) -> int:
    """执行或回放命令。

    Args:
        argv: 命令参数。
        window_seconds: 缓存窗口（秒）。
        force: 是否忽略缓存真跑。
        show_only: 是否只报告缓存状态而不执行。

    Returns:
        int: 退出码（回放时为上次退出码）。
    """
    cwd = str(Path.cwd())
    fingerprint = workspace_fingerprint()
    key = cache_key(argv, cwd, fingerprint)
    record = load_record(key)
    age = None if record is None else max(0.0, time.time() - record.started_at)
    fresh = record is not None and age is not None and age <= window_seconds

    if show_only:
        if record is None:
            _emit(f"[run-once] 无缓存：{key}（指纹 {fingerprint[:12]}）")
        else:
            _emit(
                f"[run-once] 缓存命中：{key}（{age:.0f}s 前，退出码 {record.exit_code}，"
                f"窗口 {window_seconds}s，{'有效' if fresh else '已过期'}）"
            )
        return 0

    if fresh and not force:
        _emit(
            f"[run-once] 回放上次结果（{age:.0f}s 前真跑，退出码 {record.exit_code}；"
            f"工作区指纹 {fingerprint[:12]} 未变。确需重跑加 --force）"
        )
        _emit(record.stdout)
        if record.stderr:
            _emit(record.stderr)
        if record.truncated:
            _emit("[run-once] 注意：上次输出曾截断。")
        return record.exit_code

    if record is not None and not force:
        _emit(f"[run-once] 缓存已过期（{age:.0f}s > {window_seconds}s），真跑：{' '.join(argv)}")
    elif force:
        _emit(f"[run-once] --force 真跑：{' '.join(argv)}")

    started_at = time.time()
    completed = subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    stdout, stdout_clipped = _clip(completed.stdout)
    stderr, stderr_clipped = _clip(completed.stderr)
    duration = time.time() - started_at
    save_record(
        RunRecord(
            key=key,
            argv=tuple(argv),
            cwd=cwd,
            fingerprint=fingerprint,
            started_at=started_at,
            duration_seconds=round(duration, 3),
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=stderr,
            truncated=stdout_clipped or stderr_clipped,
        )
    )
    _emit(stdout)
    if stderr:
        _emit(stderr)
    _emit(f"[run-once] 已记录（{duration:.1f}s，退出码 {completed.returncode}，键 {key}）")
    return completed.returncode


def _split_argv(args: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """分离本脚本参数与待执行命令。

    Args:
        args: 完整命令行参数（不含脚本名）。

    Returns:
        tuple[tuple[str, ...], tuple[str, ...]]: （本脚本参数, 待执行命令）；未给出 `--` 时全部参数归本脚本
        （便于 `--help` / 参数校验先行报错）。
    """
    if "--" not in args:
        return args, ()
    index = args.index("--")
    return args[:index], args[index + 1 :]


def main(args: tuple[str, ...]) -> int:
    """入口。

    Args:
        args: 命令行参数（不含脚本名）。

    Returns:
        int: 退出码。
    """
    own, argv = _split_argv(args)
    window_seconds = _DEFAULT_WINDOW_SECONDS
    force = False
    show_only = False
    index = 0
    while index < len(own):
        token = own[index]
        if token == "--force":
            force = True
        elif token == "--show":
            show_only = True
        elif token == "--window-seconds":
            index += 1
            if index >= len(own):
                print("[run-once] --window-seconds 缺少取值")
                return 2
            window_seconds = int(own[index])
        elif token in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            print(f"[run-once] 未知选项：{token}")
            return 2
        index += 1
    if not argv:
        print("[run-once] 缺少命令：用法 `run-once.py [选项] -- <命令...>`")
        return 2
    return run(argv, window_seconds=window_seconds, force=force, show_only=show_only)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main(tuple(sys.argv[1:])))
