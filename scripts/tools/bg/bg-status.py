"""bg-status.py - 秒级查询后台任务状态（运行中/已结束 + 日志尾部）

用法:
    python bg-status.py --name 任务名
"""
import argparse
import ctypes
import json
import os
import sys
import time
from pathlib import Path

BASE_DEFAULT = Path(os.environ["USERPROFILE"]) / ".bg"

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def is_alive(pid: int) -> bool:
    """Windows 进程存活探测（OpenProcess，进程不存在返回 False）。"""
    handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="查询后台任务状态")
    parser.add_argument("--name", required=True, help="任务名")
    parser.add_argument("--base", default=str(BASE_DEFAULT), help="状态目录")
    args = parser.parse_args()

    base = Path(args.base)
    safe = args.name.replace("\\", "_").replace("/", "_").replace(":", "_").replace("*", "_").replace("?", "_").replace('"', "_").replace("<", "_").replace(">", "_").replace("|", "_")
    state_file = base / f"{safe}.json"
    out_file = base / f"{safe}.out.log"
    err_file = base / f"{safe}.err.log"

    if not state_file.exists():
        print(f"NOT_FOUND name={args.name} base={base}")
        return 1

    state = json.loads(state_file.read_text(encoding="utf-8"))
    if is_alive(state["pid"]):
        elapsed = int(time.time() - state["started_ts"]) if "started_ts" in state else 0
        print(f"RUNNING name={args.name} pid={state['pid']} 已运行 {elapsed} 秒")
        if out_file.exists():
            for line in out_file.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]:
                print(line)
    else:
        out_text = out_file.read_text(encoding="utf-8", errors="replace") if out_file.exists() else ""
        print(f"FINISHED name={args.name} 输出行数={len(out_text.splitlines())}")
        for line in out_text.splitlines()[-8:]:
            print(line)
        if err_file.exists() and err_file.stat().st_size > 0:
            print("--- stderr ---")
            for line in err_file.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]:
                print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())