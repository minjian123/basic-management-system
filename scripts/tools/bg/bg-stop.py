"""bg-stop.py - 停止后台任务

用法:
    python bg-stop.py --name 任务名
"""
import argparse
import json
import os
import signal
import sys
from pathlib import Path

BASE_DEFAULT = Path(os.environ.get("USERPROFILE") or os.environ.get("HOME", "/tmp")) / ".bg"


def main() -> int:
    parser = argparse.ArgumentParser(description="停止后台任务")
    parser.add_argument("--name", required=True, help="任务名")
    parser.add_argument("--base", default=str(BASE_DEFAULT), help="状态目录")
    args = parser.parse_args()

    base = Path(args.base)
    safe = args.name.replace("\\", "_").replace("/", "_").replace(":", "_").replace("*", "_").replace("?", "_").replace('"', "_").replace("<", "_").replace(">", "_").replace("|", "_")
    state_file = base / f"{safe}.json"

    if not state_file.exists():
        print(f"NOT_FOUND name={args.name} base={base}")
        return 1

    state = json.loads(state_file.read_text(encoding="utf-8"))
    try:
        os.kill(state["pid"], signal.SIGTERM)
        print(f"STOPPED name={args.name} pid={state['pid']}")
    except OSError:
        print(f"ALREADY_FINISHED name={args.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())