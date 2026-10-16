#!/usr/bin/env python3
"""挂载 Ubuntu 数据盘进 WSL（只读）：Windows 下不进 Linux 系统也能读 Ubuntu 分区里的文件。

对象与口径（本机 mjpc 约定，可用参数覆盖）：
    磁盘 3 分区 2 = 双系统 Ubuntu 的 ext4 根分区（3.8 TB）。**只读挂载**（`--options ro`）是刻意
    选择：读文件无需写权限，可避免在 Windows 侧误写损坏双系统 Linux（还可能碰上未干净关机）。

挂载对象是物理盘，需管理员权限；挂载在 Windows 重启 / `wsl --shutdown` 后失效，需要时重跑本脚本
（桌面快捷方式「挂载 Ubuntu 盘」已勾「以管理员身份运行」）。

用法（管理员）：
    python3 scripts/tools/wsl/挂载Ubuntu盘.py                  # 挂载（已挂载则只校验并打印路径）
    python3 scripts/tools/wsl/挂载Ubuntu盘.py --unmount        # 卸载并分离物理盘
    python3 scripts/tools/wsl/挂载Ubuntu盘.py --disk 3 --partition 2 --distro Ubuntu-26.04
    （Windows 亦可经同目录 挂载Ubuntu盘.bat 双击运行）

挂载后访问路径：
    WSL 内：            /mnt/wsl/PHYSICALDRIVE3p2
    Windows 资源管理器：\\\\wsl.localhost\\Ubuntu-26.04\\mnt\\wsl\\PHYSICALDRIVE3p2

完整说明见 bms 文档《WSL 部署使用说明》（bms文档/资料/开发机/WSL部署使用说明.md）。
"""

import argparse
import contextlib
import ctypes
import os
import subprocess
import sys

PREFIX = "挂载Ubuntu盘"

DEFAULT_DISK = 3
DEFAULT_PARTITION = 2
DEFAULT_DISTRO = "Ubuntu-26.04"


def configure_stdio():
    """输出统一 UTF-8（Windows 管道 / 重定向下同样稳妥）。"""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):  # 输出编码尽力而为，不影响主流程
            stream.reconfigure(encoding="utf-8")


def is_admin():
    """当前进程是否具备管理员权限（`wsl --mount` 挂物理盘必需）。

    Returns:
        bool: 是否为管理员。
    """
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # 非 Windows 环境或无 shell32 时按非管理员处理
        return False


def run(cmd):
    """执行命令并按 UTF-8 取输出（`WSL_UTF8=1` 让 wsl.exe 用 UTF-8 输出，避免中文乱码）。

    Args:
        cmd: 命令与参数列表。

    Returns:
        subprocess.CompletedProcess: 执行结果。
    """
    env = dict(os.environ, WSL_UTF8="1")
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)


def merged_output(result):
    """合并 stdout / stderr 并去掉空行。"""
    return "\n".join(line for line in ((result.stdout or "") + (result.stderr or "")).splitlines() if line.strip())


def disk_path(disk):
    """物理盘设备路径（管理员下可直接访问）。"""
    return rf"\\.\PHYSICALDRIVE{disk}"


def mount_point(disk, partition):
    """`wsl --mount` 的挂载点（未改 automount.root 时的固定形态）。"""
    return f"/mnt/wsl/PHYSICALDRIVE{disk}p{partition}"


def distro_installed(name):
    """发行版是否已安装。"""
    result = run(["wsl", "--list", "--quiet"])
    if result.returncode != 0:
        return False
    return name in [line.strip() for line in (result.stdout or "").splitlines()]


def mount_state(distro, point):
    """读取挂载点当前状态。

    Args:
        distro: WSL 发行版名。
        point: WSL 内挂载点。

    Returns:
        tuple[str, str] | None: (来源设备, 挂载选项)；未挂载返回 None。
    """
    result = run(["wsl", "-d", distro, "-u", "root", "--", "findmnt", "-rno", "SOURCE,OPTIONS", point])
    text = (result.stdout or "").strip()
    if result.returncode != 0 or not text:
        return None
    source, _, options = text.partition(" ")
    return source.strip(), options.strip()


def report_paths(distro, disk, partition, options=""):
    """打印挂载后的两端访问路径。"""
    point = mount_point(disk, partition)
    print(f"[{PREFIX}] 访问路径：")
    print(f"[{PREFIX}]   WSL 内            {point}{f'（{options}）' if options else ''}")
    print(f"[{PREFIX}]   Windows 资源管理器 \\\\wsl.localhost\\{distro}\\" + point.lstrip("/").replace("/", "\\"))


def unmount(disk):
    """卸载并分离物理盘。

    Args:
        disk: 物理盘号。

    Returns:
        int: 退出码。
    """
    result = run(["wsl", "--unmount", disk_path(disk)])
    print(f"[{PREFIX}] wsl --unmount {disk_path(disk)}")
    print(f"[{PREFIX}] {merged_output(result) or '（无输出）'}")
    if result.returncode != 0:
        print(f"[{PREFIX}] 卸载失败。")
        return 1
    print(f"[{PREFIX}] 已卸载并分离磁盘 {disk}。")
    return 0


def main(argv):
    parser = argparse.ArgumentParser(
        prog="挂载Ubuntu盘.py",
        description="把双系统 Ubuntu 的数据盘（默认磁盘 3 分区 2）以只读方式挂进 WSL。",
    )
    parser.add_argument("--disk", type=int, default=DEFAULT_DISK, help=f"物理盘号（默认 {DEFAULT_DISK}）")
    parser.add_argument("--partition", type=int, default=DEFAULT_PARTITION, help=f"分区号（默认 {DEFAULT_PARTITION}）")
    parser.add_argument("--distro", default=DEFAULT_DISTRO, help=f"WSL 发行版名（默认 {DEFAULT_DISTRO}）")
    parser.add_argument("--unmount", action="store_true", help="卸载并分离该物理盘")
    args = parser.parse_args(argv[1:])

    print(f"[{PREFIX}] 发行版={args.distro} 磁盘={args.disk} 分区={args.partition}")

    if not is_admin():
        print(f"[{PREFIX}] 需要管理员权限（挂物理盘）：请右键以管理员身份运行，或用桌面快捷方式「挂载 Ubuntu 盘」。")
        return 2

    if not distro_installed(args.distro):
        print(f"[{PREFIX}] 未找到 WSL 发行版 {args.distro}：先按《WSL 部署使用说明》「部署」节安装发行版。")
        return 2

    if args.unmount:
        return unmount(args.disk)

    point = mount_point(args.disk, args.partition)
    state = mount_state(args.distro, point)
    if state is not None:
        source, options = state
        print(f"[{PREFIX}] 已处于挂载状态：{source} -> {point}")
        if "ro" not in options.split(","):
            print(f"[{PREFIX}] 但挂载选项非只读（{options}），尝试改回只读……")
            fix = run(["wsl", "-d", args.distro, "-u", "root", "--", "mount", "-o", "remount,ro", point])
            if fix.returncode == 0:
                state = mount_state(args.distro, point)
                print(f"[{PREFIX}] 已改为只读：{state[1] if state else '（读取失败）'}")
            else:
                print(f"[{PREFIX}] 改只读失败：{merged_output(fix)}；建议先 --unmount 再重跑本脚本。")
        report_paths(args.distro, args.disk, args.partition, state[1] if state else "")
        return 0

    print(f"[{PREFIX}] 只读挂载：wsl --mount {disk_path(args.disk)} --partition {args.partition} --options ro")
    result = run(["wsl", "--mount", disk_path(args.disk), "--partition", str(args.partition), "--options", "ro"])
    print(f"[{PREFIX}] {merged_output(result) or '（无输出）'}")
    if result.returncode != 0:
        print(f"[{PREFIX}] 挂载失败，退出码 {result.returncode}。")
        return 1

    state = mount_state(args.distro, point)
    if state is None:
        print(f"[{PREFIX}] 命令返回成功，但 {point} 未读到挂载点，请检查。")
        return 1
    report_paths(args.distro, args.disk, args.partition, state[1])
    print(f"[{PREFIX}] 完成（Windows 重启 / wsl --shutdown 后需重跑本脚本）。")
    return 0


if __name__ == "__main__":
    configure_stdio()
    sys.exit(main(sys.argv))
