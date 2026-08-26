"""bg-wait.py - 等待指定后台任务到终态（带超时上限，防傻等）

用法:
    python bg-wait.py --name 任务名 [--timeout 600] [--interval 5] [--tail 8]

配合 bg-run.py 使用：发起任务后需要结果时调用本脚本阻塞等待，
到终态输出最终状态与日志尾部后退出；超时输出 BG_WAIT_TIMEOUT 并以码 2 退出。
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

BASE_DEFAULT = Path(os.environ["USERPROFILE"]) / ".bg"


def safe_name(name: str) -> str:
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, "_")
    return name


def main() -> int:
    parser = argparse.ArgumentParser(description="等待后台任务到终态（带超时）")
    parser.add_argument("--name", required=True, help="任务名")
    parser.add_argument("--timeout", type=int, default=600, help="等待上限秒数（默认 600）")
    parser.add_argument("--interval", type=int, default=5, help="轮询间隔秒数（默认 5）")
    parser.add_argument("--tail", type=int, default=8, help="终态时输出的日志尾部行数（默认 8）")
    parser.add_argument("--base", default=str(BASE_DEFAULT), help="状态目录")
    args = parser.parse_args()

    base = Path(args.base)
    sn = safe_name(args.name)
    state_file = base / f"{sn}.json"
    out_file = base / f"{sn}.out.log"
    err_file = base / f"{sn}.err.log"

    if not state_file.exists():
        print(f"NOT_FOUND name={args.name} base={base}")
        return 1

    state = json.loads(state_file.read_text(encoding="utf-8"))
    deadline = time.time() + args.timeout
    while True:
        # 终态判定：状态文件进程已退出（bg-status 同口径：pid 不存活即结束）
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, state["pid"])
        alive = bool(handle)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
        if not alive:
            break
        if time.time() >= deadline:
            print(f"BG_WAIT_TIMEOUT name={args.name} 等待超过 {args.timeout} 秒仍在运行，请稍后再查")
            return 2
        time.sleep(args.interval)

    out_text = out_file.read_text(encoding="utf-8", errors="replace") if out_file.exists() else ""
    elapsed = int(time.time() - state.get("started_ts", time.time()))
    print(f"FINISHED name={args.name} 耗时≈{elapsed} 秒 输出行数={len(out_text.splitlines())}")
    for line in out_text.splitlines()[-args.tail:]:
        print(line)
    if err_file.exists() and err_file.stat().st_size > 0:
        print("--- stderr ---")
        for line in err_file.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]:
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
