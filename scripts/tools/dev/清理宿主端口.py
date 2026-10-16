#!/usr/bin/env python3
"""清理占用指定端口的**本项目**旧 dev server（仅限进程 cwd == 给定目录者；非本项目占用则中止，不误杀）。

背景：宿主 vite 配置为 `strictPort: true`（端口被占即启动失败、不会自动换端口），而 IDE 启动项
（「全套」等）重复启动时经常撞上上一次残留的 dev server，故启动前先自愈。

用法: python3 清理宿主端口.py <端口> <本项目宿主目录绝对路径>
（Linux 同名 .sh / Windows 同名 .bat 均为转调本文件的薄包装；逻辑只维护在这里。）
退出码: 0 = 端口已空闲（原本空闲，或已清理本项目旧进程）；1 = 被非本项目进程占用（未清理）；
        2 = 参数错误

平台口径：
- Linux：`ss -ltnp` 找监听 PID（无 ss 时回退 `netstat -ltnp`——Git Bash 等环境无 ss），
  `/proc/<pid>/cwd` 判定归属；
- Windows：`netstat -ano` 找监听 PID，读取目标进程 PEB 的 CurrentDirectory 判定归属
  （同用户进程可读；读不到时按「无法判定」处理，宁可不清理也不误杀）。

（挂法：现由 .vscode/tasks.json 的 `dev:清理宿主端口（5173）` 等前置任务以 dependsOn 方式调用；
历史备注：勿把它挂进「background 任务的 dependsOn」，「带 dependsOn 的 background 任务」会干扰
preLaunchTask 就绪判定——拆分独立任务后调用则无碍。）
"""

import contextlib
import os
import re
import signal
import subprocess
import sys
import time

IS_WINDOWS = os.name == "nt"
_PREFIX = "[dev-port]"


def configure_stdio():
    """输出统一 UTF-8（Windows 管道 / 重定向下同样稳妥）。"""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8")


def norm(path):
    """路径规范化（Windows 大小写不敏感、分隔符统一），用于比较。"""
    return os.path.normcase(os.path.normpath(os.path.abspath(os.fspath(path))))


def real_dir(path):
    """目录规范化：尽力解析（等价 shell 的 readlink -f，失败时按原样规范化）。"""
    try:
        return norm(os.path.realpath(path))
    except OSError:
        return norm(path)


# ---- 监听 PID 枚举 ----


def _port_pids_linux(port):
    """Linux：ss 优先（取 local address 列与 pid=）；ss 不存在时回退 netstat -ltnp。"""
    pids = set()
    for cmd in (["ss", "-ltnp"], ["netstat", "-ltnp"]):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        except FileNotFoundError, subprocess.TimeoutExpired:
            continue
        if result.returncode != 0:
            continue
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) < 4:
                continue
            if not fields[3].endswith(f":{port}"):
                continue
            for match in re.finditer(r"pid=(\d+)", line):
                pids.add(int(match.group(1)))
        if pids:
            break
    return sorted(pids)


def _port_pids_windows(port):
    """Windows：`netstat -ano` 解析 TCP LISTENING 行的 PID（末列）。"""
    pids = set()
    try:
        result = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, timeout=15)
    except FileNotFoundError, subprocess.TimeoutExpired:
        return []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[0].upper() != "TCP":
            continue
        if fields[3].upper() != "LISTENING":
            continue
        if not fields[1].endswith(f":{port}"):
            continue
        if fields[4].isdigit():
            pids.add(int(fields[4]))
    return sorted(pids)


def port_pids(port):
    return _port_pids_windows(port) if IS_WINDOWS else _port_pids_linux(port)


# ---- 进程 cwd 判定 ----


def _pid_cwd_linux(pid):
    try:
        return norm(os.readlink(f"/proc/{pid}/cwd"))
    except OSError:
        return ""


def _pid_cwd_windows(pid):
    """读目标进程 PEB 内的 CurrentDirectory（64 位；同用户进程可读，失败返回空串）。

    路径：OpenProcess → NtQueryInformationProcess(ProcessBasicInformation) 取 PEB 基址 →
    读 PEB 偏移 0x20 的 RTL_USER_PROCESS_PARAMETERS 指针 → 读其偏移 0x38 的 CURDIR
    （UNICODE_STRING：Length@+0x00、Buffer@+0x08）→ ReadProcessMemory 读宽字符串。
    """
    try:
        import ctypes

        if ctypes.sizeof(ctypes.c_void_p) != 8:
            return ""  # 仅支持 64 位 Python / 64 位目标进程

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        PROCESS_VM_READ = 0x0010
        PROCESS_BASIC_INFORMATION_CLASS = 0

        class PROCESS_BASIC_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("Reserved1", ctypes.c_void_p),
                ("PebBaseAddress", ctypes.c_void_p),
                ("Reserved2", ctypes.c_void_p * 2),
                ("UniqueProcessId", ctypes.c_void_p),
                ("Reserved3", ctypes.c_void_p),
            ]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        ntdll = ctypes.WinDLL("ntdll", use_last_error=True)

        handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, False, pid)
        if not handle:
            return ""
        try:
            pbi = PROCESS_BASIC_INFORMATION()
            status = ntdll.NtQueryInformationProcess(
                handle, PROCESS_BASIC_INFORMATION_CLASS, ctypes.byref(pbi), ctypes.sizeof(pbi), None
            )
            if status != 0 or not pbi.PebBaseAddress:
                return ""

            def read_mem(address, size):
                buf = ctypes.create_string_buffer(size)
                read = ctypes.c_size_t(0)
                ok = k32.ReadProcessMemory(
                    handle,
                    ctypes.c_void_p(address),
                    buf,
                    ctypes.c_size_t(size),
                    ctypes.byref(read),
                )
                if not ok or read.value < size:
                    return None
                return buf.raw

            def read_ptr(address):
                raw = read_mem(address, 8)
                return int.from_bytes(raw, "little") if raw else 0

            params = read_ptr(pbi.PebBaseAddress + 0x20)
            if not params:
                return ""
            curdir = read_mem(params + 0x38, 16)
            if not curdir:
                return ""
            length = int.from_bytes(curdir[0:2], "little")
            buffer_ptr = int.from_bytes(curdir[8:16], "little")
            if not length or not buffer_ptr:
                return ""
            raw = read_mem(buffer_ptr, length)
            if not raw:
                return ""
            return norm(raw.decode("utf-16-le", errors="replace"))
        finally:
            k32.CloseHandle(handle)
    except Exception:
        return ""


def pid_cwd(pid):
    return _pid_cwd_windows(pid) if IS_WINDOWS else _pid_cwd_linux(pid)


# ---- 主流程 ----


def kill_pid(pid):
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except OSError:
        return False


def main(argv):
    configure_stdio()
    if len(argv) < 3:
        sys.stderr.write(
            f"用法: {os.path.basename(argv[0]) if argv else '清理宿主端口.py'} <端口> <本项目宿主目录绝对路径>\n"
        )
        return 2

    port_raw, dir_raw = argv[1], argv[2]
    if not port_raw.isdigit():
        sys.stderr.write(f"{_PREFIX} 端口参数非法: {port_raw}\n")
        return 2
    port = int(port_raw)
    target_dir = real_dir(dir_raw)

    rc = 0
    pids = port_pids(port)
    for pid in pids:
        cwd = pid_cwd(pid)
        if cwd and cwd == target_dir:
            print(f"{_PREFIX} 清理本项目旧 dev server：pid={pid} port={port} cwd={cwd}")
            kill_pid(pid)
        else:
            shown = cwd if cwd else "无法判定"
            sys.stderr.write(f"{_PREFIX} 端口 {port} 被非本项目进程占用：pid={pid} cwd={shown}，中止启动（不误杀）\n")
            rc = 1

    # 等端口释放（最多 10s），仅在本轮确有清理动作时等待
    if rc == 0 and pids:
        for _ in range(20):
            if not port_pids(port):
                break
            time.sleep(0.5)
        if not port_pids(port):
            print(f"{_PREFIX} 端口 {port} 已释放")

    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
