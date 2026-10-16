#!/bin/sh
# 依赖外置：转调 Python 单一实现（同目录 外置依赖.py）——Linux / Windows 共用一份实现，本文件仅为瘦包装。
# 用法与口径见 外置依赖.py 头部注释；历史完整 shell 实现见 git 历史（2026-10-16 起改瘦包装）。
set -eu
here="$(cd "$(dirname "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
    echo "[外置依赖] 未找到 python3，请先安装 Python 3（见 uv 部署使用说明）。" >&2
    exit 2
fi
exec python3 "$here/外置依赖.py" "$@"
