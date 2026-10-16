#!/usr/bin/env bash
# 确保模块产物服务（5002）在跑 —— Linux 入口脚本（转调同名 .py 单一实现；逻辑见 确保模块产物服务.py）
# 对应 Windows 入口 确保模块产物服务.bat
# 用法: ./确保模块产物服务.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$HERE/确保模块产物服务.py" "$@"
