#!/usr/bin/env bash
# BMS 批量镜像拉取（断点续传 + 失败自动重试）—— Linux 入口脚本（转调同名 .py 单一实现；逻辑见 拉取镜像.py）
# 对应 Windows 入口 拉取镜像.bat
# 用法: ./拉取镜像.sh [选项] [镜像...]（选项与口径见 拉取镜像.py 头部注释，-h 查看帮助）
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$HERE/拉取镜像.py" "$@"
