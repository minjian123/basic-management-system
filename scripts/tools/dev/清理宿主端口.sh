#!/usr/bin/env bash
# 清理占用指定端口的本项目旧 dev server —— Linux 入口脚本（转调同名 .py 单一实现；逻辑见 清理宿主端口.py）
# 对应 Windows 入口 清理宿主端口.bat
# 用法: ./清理宿主端口.sh <端口> <本项目宿主目录绝对路径>
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$HERE/清理宿主端口.py" "$@"
