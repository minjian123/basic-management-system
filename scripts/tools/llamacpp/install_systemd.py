#!/usr/bin/env python3
"""在 mjpc 上以 root 执行一次（sudo bash install_systemd.sh）：
  1) 安装并启用 openssh-server（供 mjbk 远程启停模型 / 关机）
  2) ufw 放行 mjbk 的 22 / 8080 / 8082
  3) 把 qwen_serve.sh 同步到 llama.cpp 源码目录，并安装系统级 llamacpp-qwen / llamacpp-bge 服务
     （默认不自启，由 MIRIX 模型代理按需 start）

2026-10-16 起「Python 单一实现 + 薄包装」：逻辑只维护在本文件，Linux 入口
install_systemd.sh 仅转调本文件（历史完整 shell 实现见 git 历史）。
第 4 步同步两个文件：qwen_serve.sh 薄包装 + qwen_serve.py 单一实现（两者必须同目录
并存），以及档位配置模板 llamacpp-qwen.env.example（目标已存在时保留不动）。
单元文件 llamacpp-qwen.service 的 ExecStart 仍指向 qwen_serve.sh（包装名不变）。

用法: sudo bash scripts/tools/llamacpp/install_systemd.sh
环境变量: MJBK_IP(默认 192.168.0.107) LLAMA_DIR(默认 /home/minjian/develop/llama.cpp)
前置: Linux + root；apt 走系统已换的清华源（见《Ubuntu安装部署使用说明》，本脚本不配置源）。
退出码: 0 = 安装完成；1 = 非 root / 外部命令或文件操作失败；2 = 非 Linux 平台（mjpc 侧专用）
"""

import contextlib
import os
import shutil
import subprocess
import sys

PREFIX = "[install-systemd]"
DEFAULT_MJBK = "192.168.0.107"
DEFAULT_LLAMA_DIR = "/home/minjian/develop/llama.cpp"
UFW_TCP_PORTS = ("22", "8080", "8082")
SYSTEMD_UNIT_DIR = "/etc/systemd/system"
WRAPPER = "qwen_serve.sh"
IMPL = "qwen_serve.py"
ENV_EXAMPLE = "llamacpp-qwen.env.example"
ENV_TARGET = "llamacpp-qwen.env"
SERVICE_UNITS = ("llamacpp-qwen.service", "llamacpp-bge.service")


def configure_stdio():
    """输出统一 UTF-8（Windows / 管道重定向下同样稳妥）。"""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8")


def run(cmd, env=None, check=True, quiet_stderr=False):
    """执行外部命令：输出不捕获（apt / ufw / systemctl 实时回显）。

    check=True 对应原脚本的 `set -e`（失败即中止，退出码透传给调用者）；
    check=False 对应 `... || true`（如 `ufw reload 2>/dev/null || true`）。
    """
    try:
        return subprocess.run(
            list(cmd),
            env=env,
            check=check,
            stderr=subprocess.DEVNULL if quiet_stderr else None,
        )
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(f"{PREFIX} 命令失败（exit={exc.returncode}）：{' '.join(map(str, exc.cmd))}\n")
        raise SystemExit(exc.returncode if exc.returncode > 0 else 1) from None


def install_file(src, dst, mode):
    """等价 `install -m <mode> <src> <dst>`：存在即覆盖，并设置权限位。"""
    try:
        shutil.copyfile(src, dst)
        os.chmod(dst, mode)
    except OSError as exc:
        sys.stderr.write(f"{PREFIX} 安装文件失败（{src} -> {dst}）：{exc}\n")
        raise SystemExit(1) from None


def require_root(script_dir):
    """root 校验（对应原脚本 `id -u`），措辞与原脚本一致。"""
    if os.geteuid() == 0:
        return True
    sh_path = os.path.join(script_dir, "install_systemd.sh")
    shown = sh_path
    try:
        rel = os.path.relpath(sh_path)
        if not rel.startswith(".."):
            shown = rel  # 与历史 shell 版 `$0` 口径一致：仓内相对写法优先
    except ValueError:
        pass
    sys.stderr.write(f"请以 root 运行：sudo bash {shown}\n")
    return False


def main(argv):
    script_dir = os.path.dirname(os.path.realpath(os.fspath(__file__)))
    mjbk = os.environ.get("MJBK_IP") or DEFAULT_MJBK
    llama_dir = os.environ.get("LLAMA_DIR") or DEFAULT_LLAMA_DIR

    if not hasattr(os, "geteuid"):
        sys.stderr.write(f"{PREFIX} 本脚本仅支持 Linux（mjpc 侧安装脚本）。\n")
        return 2
    if not require_root(script_dir):
        return 1

    print("[1/5] 安装 openssh-server ...")
    run(["apt-get", "update", "-qq"])
    run(["apt-get", "install", "-y", "-q", "openssh-server"], env=dict(os.environ, DEBIAN_FRONTEND="noninteractive"))

    print("[2/5] 启用 ssh ...")
    run(["systemctl", "enable", "--now", "ssh"])

    print(f"[3/5] ufw 放行 mjbk（{mjbk}）的 22 / 8080 / 8082 ...")
    for port in UFW_TCP_PORTS:
        run(["ufw", "allow", "from", mjbk, "to", "any", "port", port, "proto", "tcp"])
    run(["ufw", "reload"], check=False, quiet_stderr=True)

    print(f"[4/5] 同步包装脚本与模型档位配置到 {llama_dir} ...")
    os.makedirs(llama_dir, exist_ok=True)
    install_file(os.path.join(script_dir, WRAPPER), os.path.join(llama_dir, WRAPPER), 0o755)
    install_file(os.path.join(script_dir, IMPL), os.path.join(llama_dir, IMPL), 0o755)
    env_target = os.path.join(llama_dir, ENV_TARGET)
    if not os.path.isfile(env_target):
        install_file(os.path.join(script_dir, ENV_EXAMPLE), env_target, 0o644)

    print("[5/5] 安装系统级服务单元 ...")
    for unit in SERVICE_UNITS:
        install_file(os.path.join(script_dir, unit), os.path.join(SYSTEMD_UNIT_DIR, unit), 0o644)
    run(["systemctl", "daemon-reload"])

    print()
    print("完成。服务默认不随开机自启，由 MIRIX 代理按需启动：")
    print("  sudo systemctl start llamacpp-qwen llamacpp-bge")
    print("  sudo systemctl status llamacpp-qwen llamacpp-bge")
    return 0


if __name__ == "__main__":
    configure_stdio()
    sys.exit(main(sys.argv))
