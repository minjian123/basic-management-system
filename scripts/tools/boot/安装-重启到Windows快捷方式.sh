#!/usr/bin/env bash
# 在 Ubuntu 侧安装「重启到 Windows」桌面快捷方式 —— Linux 入口脚本
# （转调同名 .py 单一实现；逻辑、口径与部署说明见 安装-重启到Windows快捷方式.py）
# 用法: bash 安装-重启到Windows快捷方式.sh    （勿用 root/sudo 运行，脚本内部按需 sudo）
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
    echo "[安装-重启到Windows快捷方式] 未找到 python3，请先安装 Python 3。" >&2
    exit 2
fi
exec python3 "$HERE/安装-重启到Windows快捷方式.py" "$@"
