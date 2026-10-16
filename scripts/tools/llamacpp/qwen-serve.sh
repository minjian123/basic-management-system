#!/usr/bin/env bash
# 前台常驻版 llama-server 包装（供 systemd --user 使用；不做 stop-others / nohup）
# —— Linux 入口脚本（转调同名 .py 单一实现；逻辑见 qwen_serve.py）
# 用法: ./qwen-serve.sh [ud|std|unc]     默认 std
# 环境变量: HOST(默认 0.0.0.0) PORT(默认 8080) MODEL_KEY(默认 std)
# 注意: install-systemd.py 会把本包装与 qwen_serve.py 一并拷到 llama.cpp 源码目录，两者须同目录并存
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$HERE/qwen_serve.py" "$@"
