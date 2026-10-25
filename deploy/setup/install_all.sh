#!/bin/bash
# mjbk Ubuntu 22.04 Server 一键部署 —— bash 入口（用法：sudo bash install_all.sh；逻辑见同目录 install_all.py）
# 前置：Ubuntu 安装时勾选 OpenSSH，网络静态 IP（IP 与账号见《本地资源》）；执行前 export MJBK_IP=服务器IP
# 口径、分步流程与日志双写见 install_all.py 头部注释；历史完整 shell 实现见 git 历史（2026-10-16 起改瘦包装）。
set -eu
here="$(cd "$(dirname "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
    echo "[install-all] 未找到 python3，请先安装 Python 3（sudo apt-get install -y python3）。" >&2
    exit 2
fi
exec python3 "$here/install_all.py" "$@"
