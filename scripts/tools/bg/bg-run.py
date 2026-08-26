"""bg-run.py - 通用后台执行器：任何命令立即返回，状态与日志落盘，随时秒查

用法:
    python bg-run.py --name 下载依赖 --command "pnpm install" [--workdir D:\\AI\\xxx] [--timeout 60]
    python bg-status.py --name 下载依赖    查询
    python bg-stop.py --name 下载依赖      停止

Base 默认 %USERPROFILE%\\.bg，可 --base 覆盖（同一 Base 下按 name 区分任务）。
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

BASE_DEFAULT = Path(os.environ["USERPROFILE"]) / ".bg"


def main() -> int:
    parser = argparse.ArgumentParser(description="后台执行任意命令（立即返回）")
    parser.add_argument("--name", required=True, help="任务名（唯一标识）")
    parser.add_argument("--command", required=True, help="要执行的命令")
    parser.add_argument("--workdir", default=os.getcwd(), help="工作目录（默认当前目录）")
    parser.add_argument("--timeout", type=int, default=0, help="命令超时秒数（0=不限，默认 0）")
    parser.add_argument("--base", default=str(BASE_DEFAULT), help="状态目录（默认 %%USERPROFILE%%\\.bg）")
    args = parser.parse_args()

    base = Path(args.base)
    base.mkdir(parents=True, exist_ok=True)
    safe = args.name.replace("\\", "_").replace("/", "_").replace(":", "_").replace("*", "_").replace("?", "_").replace('"', "_").replace("<", "_").replace(">", "_").replace("|", "_")
    out_file = base / f"{safe}.out.log"
    err_file = base / f"{safe}.err.log"
    state_file = base / f"{safe}.json"
    for f in (out_file, err_file, state_file):
        try:
            f.unlink()
        except FileNotFoundError:
            pass

    stdout = open(out_file, "w", encoding="utf-8")
    stderr = open(err_file, "w", encoding="utf-8")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(
        ["pwsh", "-NoProfile", "-Command", args.command],
        cwd=args.workdir,
        stdout=stdout,
        stderr=stderr,
        creationflags=creationflags,
    )

    state = {
        "name": args.name,
        "pid": proc.pid,
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        "started_ts": time.time(),
        "command": args.command,
        "out": str(out_file),
    }
    state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    if args.timeout > 0:
        def _watch():
            deadline = time.time() + args.timeout
            while proc.poll() is None and time.time() < deadline:
                time.sleep(1)
            if proc.poll() is None:
                proc.kill()
                print(f"BG_TIMEOUT name={args.name} 超过 {args.timeout} 秒，已终止", flush=True)
        threading.Thread(target=_watch, daemon=True).start()

    stdout.close()
    stderr.close()
    print(f"BG_STARTED name={args.name} pid={proc.pid}", flush=True)
    print(f"状态查询: python {Path(__file__).resolve().parent / 'bg-status.py'} --name '{args.name}'", flush=True)
    print(f"日志: {out_file}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())