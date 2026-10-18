#!/bin/sh
# 生成 opencode Web 配对二维码：转调 Python 单一实现（同目录 配对二维码.py）——Linux / Windows 共用一份实现，本文件仅为瘦包装。
# 用法与口径见 配对二维码.py 头部注释。
set -eu
here="$(cd "$(dirname "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
    echo "[配对二维码] 未找到 python3，请先安装 Python 3。" >&2
    exit 2
fi
exec python3 "$here/配对二维码.py" "$@"
