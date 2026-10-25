#!/usr/bin/env bash
# 在 mjpc 上以 root 执行一次 —— Linux 入口脚本（转调同名 .py 单一实现；逻辑见 install_systemd.py）
# 用法: sudo bash install_systemd.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$HERE/install_systemd.py" "$@"
