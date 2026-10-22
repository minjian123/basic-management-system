#!/bin/sh
# WSL 内开发环境复刻：从只读挂载的双系统 Ubuntu 盘复制 bizs 工作区与依赖仓。
# 用法见 bms 文档《WSL 部署使用说明》「WSL 内开发环境」节；脚本本身说明见同名 .py。
#
# 用法：
#   wsl -d Ubuntu-26.04 -- bash <本脚本>            # 完整复刻
#   wsl -d Ubuntu-26.04 -- bash <本脚本> --skip-deps  # 只复制工作区
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$SCRIPT_DIR/部署WSL开发环境.py"

if [ ! -f "$PY" ]; then
    echo "[部署WSL开发环境] 找不到主脚本：$PY" >&2
    exit 1
fi

# 优先用系统 python3（脚本只用标准库）
exec python3 "$PY" "$@"
