#!/usr/bin/env python3
"""确保模块产物服务（5002）在跑：缺则后台拉起 frontend/scripts/serve-module-releases.mjs（幂等）。

背景：宿主按 `frontend/apps/desktop/public/modules.json` 加载**发布归档**，入口形如
`http://localhost:5002/<模块名>/<版本>/remoteEntry.js`；由 `serve-module-releases.mjs`
在 5002 托管 `frontend/releases/**`（带 CORS；`python3 -m http.server` 等裸静态服务因
缺 CORS 头会导致跨源 ESM 加载失败）。dev 类任务的 `dependsOn` 前置任务调本脚本——
等价旧版 `pgrep -f 'serve-module-releases.mjs' || nohup node ... &; sleep 1`，改为
「Python 单一实现、Linux / Windows 同口径」。

用法: python3 确保模块产物服务.py
（Linux 同名 .sh / Windows 同名 .bat 均为转调本文件的薄包装；逻辑只维护在这里。）
退出码: 0 = 服务已在跑或已拉起；1 = 拉起失败（node 缺失 / 进程立刻退出）
"""

import contextlib
import json
import os
import subprocess
import sys
import tempfile
import time

IS_WINDOWS = os.name == "nt"
PREFIX = "[模块产物]"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
ENTRY = os.path.join("frontend", "scripts", "serve-module-releases.mjs")
LOG_PATH = (
    os.path.join(tempfile.gettempdir(), "bms-serve-releases.log") if IS_WINDOWS else "/tmp/bms-serve-releases.log"
)


def configure_stdio():
    """输出统一 UTF-8（Windows 管道 / 重定向下同样稳妥）。"""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8")


def find_running_pids():
    """找已在本机运行的 serve-module-releases 进程（等价 pgrep -f；Windows 走 CIM）。"""
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                    "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'node*' } | "
                    "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return []
            data = json.loads(result.stdout)
        except Exception:
            return []
        if isinstance(data, dict):
            data = [data]
        pids = []
        for item in data:
            cmdline = item.get("CommandLine") or ""
            if "serve-module-releases.mjs" in cmdline:
                with contextlib.suppress(KeyError, TypeError, ValueError):
                    pids.append(int(item["ProcessId"]))
        return sorted(pids)

    pids = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as fh:
                cmdline = fh.read().replace(b"\x00", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        if "serve-module-releases.mjs" in cmdline:
            pids.append(int(entry))
    return sorted(pids)


def main(argv):
    configure_stdio()
    pids = find_running_pids()
    if pids:
        print(f"{PREFIX} 5002 发布存储服务已在跑（pid {' '.join(str(p) for p in pids)}），跳过")
        return 0

    creationflags = 0
    kwargs = {}
    if IS_WINDOWS:
        creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True  # nohup 等价
    try:
        with open(LOG_PATH, "wb") as logf:
            proc = subprocess.Popen(
                ["node", ENTRY],
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=logf,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
                **kwargs,
            )
    except OSError as exc:
        sys.stderr.write(f"{PREFIX} 无法启动 node（{exc}）：{ENTRY}\n")
        return 1

    time.sleep(1)
    if proc.poll() is not None:
        sys.stderr.write(f"{PREFIX} 拉起失败（exit={proc.returncode}）；日志：{LOG_PATH}\n")
        return 1
    print(f"{PREFIX} 已后台拉起 5002 发布存储服务（pid {proc.pid}，日志 {LOG_PATH}）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
