#!/usr/bin/env bash
# 开发环入口（Linux）：只跑本次 git 改动相关的测试
# 后端直接依赖选测 + 前端受影响包 + 改动文件 ruff；覆盖率与全仓静态留推送前预检
# 用法: ./测试改动内容.sh [--changed-from <ref>] [--no-lint] [--no-frontend] [--jobs auto|N|off]
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/../../.." || exit 1   # 跳到仓库根目录
exec python3 scripts/tools/preflight/测试改动内容.py "$@"
