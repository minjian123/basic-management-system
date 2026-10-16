#!/usr/bin/env python3
r"""在 Ubuntu 侧安装「重启到 Windows」桌面快捷方式（单一实现；同名 .sh 为瘦包装）。

用法（在 Ubuntu 开发机 mjpc 上执行；**勿用 root/sudo 直接运行**，脚本内部按需 sudo）：
    bash scripts/tools/boot/安装-重启到Windows快捷方式.sh
    python3 scripts/tools/boot/安装-重启到Windows快捷方式.py    # 等价（包装只做转调）

作用：装好后桌面上出现「重启到 Windows」，双击（带确认框）即可设 UEFI
      BootNext 指向 Windows 并重启；只生效一次，之后回到默认顺序。

卸载：sudo rm -f /usr/local/bin/reboot-to-windows \
                 /etc/sudoers.d/reboot-to-windows \
                 ~/.local/share/applications/reboot-to-windows.desktop \
                 "$(xdg-user-dir DESKTOP)/reboot-to-windows.desktop"

安装流程（与原 shell 版逐项一致）：
  0. 检查：以 root 直接运行 → 中止；非 UEFI 启动（无 /sys/firmware/efi）→ 中止；
  1. 缺 efibootmgr 则 `sudo apt-get update -qq && sudo apt-get install -y efibootmgr`；
     随后打印 `efibootmgr` 全量输出（每行缩进两格），并从中识别 Windows 启动项编号：
     行首为 Boot+4 位十六进制、整行（小写后）含 windows 的首个命中项，取第一个字段
     第 5–8 个字符；识别不到回退 0000（口径与旧 awk 一致）；
  2. `sudo tee` 写 /usr/local/bin/reboot-to-windows 并 chmod 755；
  3. `sudo tee` 写 /etc/sudoers.d/reboot-to-windows（仅该命令免密）并 chmod 440，
     再用 `sudo visudo -c -f` 校验，失败即 `sudo rm -f` 回滚并以 1 退出；
  4. 免 sudo 写桌面项：~/.local/share/applications/reboot-to-windows.desktop
     → 拷到 `xdg-user-dir DESKTOP`（取不到回退 $HOME/桌面）→ chmod 755
     → 有 gio 则标 metadata::trusted（失败忽略）→ 有 desktop-file-validate 则校验
     （校验失败以该命令退出码退出，同旧 `set -e` 口径）。

生成物形态（2026-10-16 拍板：生成物也随口径转为 Python）：/usr/local/bin/reboot-to-windows
是**目标机上的系统文件**（由免密 sudo 规则按路径直接执行），内容为一段 Python 小程序
（zenity 确认框 → `efibootmgr -n` 设 BootNext → `systemctl reboot`），依赖目标机自带
python3（Ubuntu 系统内置）。行为与旧 shell 生成物逐项一致（含 zenity 取消 / 失败报错分支），
与文档《双系统引导部署使用说明》4.5 节的手动安装片段保持同步。机器侧若已装旧版生成物，
重跑本安装脚本即可更新。

历史：本脚本原为 shell 实现（安装-重启到Windows快捷方式.sh），2026-10-16 起改为
Python 单一实现 + 同名 .sh 薄包装；同日拍板生成物也转 Python。
"""

import contextlib
import os
import re
import shutil
import subprocess
import sys

# 安装产物路径（与文档《双系统引导部署使用说明》一致）。
HELPER_PATH = "/usr/local/bin/reboot-to-windows"
SUDOERS_PATH = "/etc/sudoers.d/reboot-to-windows"
DESKTOP_NAME = "reboot-to-windows.desktop"
# 未识别到 Windows 项时的回退编号（与旧 shell 版一致）。
FALLBACK_BOOT_NUM = "0000"

DESKTOP_ENTRY = f"""[Desktop Entry]
Type=Application
Name=重启到 Windows
Name[en]=Reboot to Windows
Comment=设置下次启动进入 Windows 并立即重启
Exec=sudo -n {HELPER_PATH}
Icon=system-reboot
Terminal=false
Categories=System;
"""


def configure_stdio():
    """输出统一 UTF-8（终端中文提示不受本机 locale 影响）。"""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8")


def sudo_tee(path, content):
    """以 root 身份写文件（等价旧用法 `echo 内容 | sudo tee 路径 >/dev/null`）。"""
    subprocess.run(
        ["sudo", "tee", path],
        input=content,
        encoding="utf-8",
        stdout=subprocess.DEVNULL,
        check=True,
    )


def identify_windows_boot_num(entries_text):
    """从 efibootmgr 输出识别 Windows 启动项编号（与旧 awk 逐字同口径，见模块注释）。"""
    for line in entries_text.splitlines():
        if not re.match(r"^Boot[0-9A-Fa-f]{4}", line):
            continue
        if "windows" not in line.lower():
            continue
        return re.split(r"[ *]+", line)[0][4:8]
    return ""


def desktop_dir():
    """桌面目录：`xdg-user-dir DESKTOP`；命令缺失或执行失败回退 $HOME/桌面。"""
    fallback = os.path.join(os.path.expanduser("~"), "桌面")
    if shutil.which("xdg-user-dir") is None:
        return fallback
    result = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, encoding="utf-8", errors="replace")
    value = result.stdout.strip()
    if result.returncode != 0 or not value:
        return fallback
    return value


def render_helper(win_num):
    """生成 /usr/local/bin/reboot-to-windows 内容（Python 小程序，行为与旧 shell 生成物一致）。"""
    return f'''#!/usr/bin/env python3
"""设置 UEFI BootNext 指向 Windows({win_num})，然后重启（只生效一次）。"""
import shutil
import subprocess
import sys

WIN_NUM = "{win_num}"


def main():
    if shutil.which("zenity") is not None:
        question = subprocess.run(
            [
                "zenity",
                "--question",
                "--title=重启到 Windows",
                "--text=确定重启回 Windows 吗？\\\\n\\\\n请先保存所有未保存的工作。",
                "--ok-label=重启",
                "--cancel-label=取消",
            ]
        )
        if question.returncode != 0:
            return 0
    flag = subprocess.run(
        ["efibootmgr", "-n", WIN_NUM], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    if flag.returncode != 0:
        msg = "设置下次启动项失败（efibootmgr -n " + WIN_NUM + "）。"
        print(msg, file=sys.stderr)
        if shutil.which("zenity") is not None:
            subprocess.run(["zenity", "--error", "--title=重启到 Windows 失败", "--text=" + msg])
        return 1
    return subprocess.run(["systemctl", "reboot"]).returncode


if __name__ == "__main__":
    sys.exit(main())
'''


def main():
    # ---------- 0. 基本检查 ----------
    if getattr(os, "getuid", lambda: -1)() == 0:
        sys.stderr.write("请不要用 root 直接运行（脚本内部会按需 sudo）。\n")
        return 1

    if not os.path.isdir("/sys/firmware/efi"):
        sys.stderr.write("当前不是 UEFI 启动，本脚本不适用。\n")
        return 1

    print("== 重启到 Windows 快捷方式 安装程序 ==")
    print()

    # ---------- 1. 确定 Windows 的 UEFI 启动项编号 ----------
    if shutil.which("efibootmgr") is None:
        print("缺少 efibootmgr，正在安装...")
        subprocess.run(["sudo", "apt-get", "update", "-qq"], check=True)
        subprocess.run(["sudo", "apt-get", "install", "-y", "efibootmgr"], check=True)

    firmware = subprocess.run(
        ["efibootmgr"],
        stdout=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    print("当前固件启动项：")
    for line in firmware.stdout.splitlines():
        print(f"  {line}")
    print()

    # 优先匹配描述含 Windows 的项；否则退回 0000
    win_num = identify_windows_boot_num(firmware.stdout)
    if not win_num:
        win_num = FALLBACK_BOOT_NUM
        print("未从描述中识别到 Windows 项，回退使用 0000。")
    print(f"将使用 Windows 启动项编号：{win_num}")
    print(f"（若不对，安装后编辑 {HELPER_PATH} 里的编号）")
    print()

    # ---------- 2. 写入切换脚本 ----------
    sudo_tee(HELPER_PATH, render_helper(win_num))
    subprocess.run(["sudo", "chmod", "755", HELPER_PATH], check=True)
    print(f"已写入 {HELPER_PATH}")

    # ---------- 3. 免密规则（仅这一条命令免密） ----------
    user = os.environ.get("USER", "")
    sudo_tee(SUDOERS_PATH, f"{user} ALL=(root) NOPASSWD: {HELPER_PATH}\n")
    subprocess.run(["sudo", "chmod", "440", SUDOERS_PATH], check=True)
    check = subprocess.run(
        ["sudo", "visudo", "-c", "-f", SUDOERS_PATH],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if check.returncode == 0:
        print(f"已写入免密规则 {SUDOERS_PATH}")
    else:
        sys.stderr.write("免密规则语法校验失败，已回滚该文件。\n")
        subprocess.run(["sudo", "rm", "-f", SUDOERS_PATH], check=True)
        return 1

    # ---------- 4. 桌面项 ----------
    target_desktop = desktop_dir()
    app_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "applications")
    os.makedirs(app_dir, exist_ok=True)
    os.makedirs(target_desktop, exist_ok=True)

    app_file = os.path.join(app_dir, DESKTOP_NAME)
    with open(app_file, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(DESKTOP_ENTRY)
    desktop_file = os.path.join(target_desktop, DESKTOP_NAME)
    shutil.copyfile(app_file, desktop_file)
    os.chmod(desktop_file, 0o755)

    # GNOME 要求桌面图标标记 trusted，否则双击被拦
    if shutil.which("gio") is not None:
        subprocess.run(
            ["gio", "set", desktop_file, "metadata::trusted", "true"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    if shutil.which("desktop-file-validate") is not None:
        code = subprocess.run(["desktop-file-validate", app_file]).returncode
        if code != 0:
            return code
        print("desktop 文件语法校验通过")

    print()
    print("== 安装完成 ==")
    print(f"桌面图标：{desktop_file}")
    print(f"应用菜单：{app_file}")
    print()
    print("双击「重启到 Windows」即可（会弹确认框）。")
    return 0


if __name__ == "__main__":
    configure_stdio()
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        # 与旧 `set -e` 同口径：外部命令失败即中止，退出码沿用其状态码
        # （被信号终止的负值折算为 shell 的 128+N）。
        code = 128 - exc.returncode if exc.returncode < 0 else exc.returncode
        sys.stderr.write(f"[安装-重启到Windows快捷方式] 外部命令失败（退出码 {code}）：{' '.join(exc.cmd)}\n")
        sys.exit(code)
