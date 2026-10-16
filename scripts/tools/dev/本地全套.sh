#!/usr/bin/env bash
# 本机裸跑「全套」后端 —— Linux 入口脚本（转调同名 .py 单一实现；逻辑见 本地全套.py）
# 对应 Windows 入口 本地全套.bat
# 用法: ./本地全套.sh <up|down|stop|status|seed|env|logs|unlock> [选项]（完整说明: ./本地全套.sh --help）
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$HERE/本地全套.py" "$@"
